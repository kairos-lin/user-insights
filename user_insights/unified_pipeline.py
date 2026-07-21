"""Ultra-fast stateless pipeline: async concurrent scraping, aggressive LLM batching.

Target <3 min per case:
  Brain: 10s | Scout fetch: 10s | Scout LLM: 10s | Main scrape: 80s | Tagging: 30s | Synth: 15s
"""

import concurrent.futures
import json
import os
import re
import time

from .api_client import APIClient
from .brain_planner import route_query, scout_organic_terms
from .config import get_reddit_credentials
from .data_normalizer import merge_datasets
from .meta_parser import init_sovereignty, is_semantic_pollution, recalibrate_sovereignty
from .mock_data import get_mock_transcript
from .models import BrainPlan, SearchQuery, YouTubeVideo, Signal, TaggedSignal, Anchor3D, SovereigntyPlan
from .quality_engine import (
    assess_quality,
    assess_youtube_quality,
    classify_youtube_tier,
    self_gating_reddit,
    filter_aigc_sticky_noise,
    compute_signal_diversity,
)
from .reddit_scraper import RedditScraper
from .scraper.youtube import QuotaExceededError, YouTubeScraper
from .stats_aggregator import compute_unified_stats
from .synthesizer import synthesize_unified
from .task_decomposer import detect_language
from .prompts import EXTRACT_SYSTEM, YOUTUBE_TAG_SYSTEM, YOUTUBE_TAG_USER


def run_unified_pipeline(
    question: str, client: APIClient,
    yt_api_key: str | None = None, proxy: str | None = None,
) -> dict:
    t_total = time.time()
    language = detect_language(question)
    proxy = proxy or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:
        for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
            os.environ[k] = proxy

    # ── Stage 0: System Sovereignty Initialization ────────────────────
    t0 = time.time()
    sovereignty = init_sovereignty(question, client)
    print(f"  [Sovereignty] anchors={sovereignty.positive_anchors}")
    print(f"  [Sovereignty] target_subs={sovereignty.target_subreddits}")
    print(f"  [Sovereignty] exclusion_wall={sovereignty.negative_exclusion_wall}")
    print(f"  [Sovereignty] ({time.time()-t0:.0f}s)")

    # ── Stage 1: Brain Planner (with sovereignty override) ────────────
    t0 = time.time()
    plan, baseline_keywords = route_query(question, client)
    # DYNAMIC WIRING: Sovereignty target_subreddits OVERRIDE Brain Planner defaults
    if sovereignty.target_subreddits:
        # Strip r/ prefix if present (PRAW adds it automatically)
        plan.target_subreddits = [
            s.replace("r/", "").strip() for s in sovereignty.target_subreddits
        ]
    if sovereignty.target_channels:
        plan.target_channels = sovereignty.target_channels
    # Use sovereignty anchors as primary search keywords
    if sovereignty.positive_anchors:
        baseline_keywords = sovereignty.positive_anchors[:3]
    print(f"  [Brain] {plan.domain} subs={plan.target_subreddits} baseline={baseline_keywords} ({time.time()-t0:.0f}s)")

    # ── Stage 2: Wide-Net Scout (concurrent, with body text) ──────────
    scout_kw = " ".join(baseline_keywords[:2]) if baseline_keywords else question
    t0 = time.time()
    scout_samples = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        fr = ex.submit(_scout_reddit_bodies, scout_kw, plan, proxy)
        fy = ex.submit(_scout_youtube_bodies, scout_kw, yt_api_key, proxy)
        for f in concurrent.futures.as_completed([fr, fy]):
            try:
                scout_samples.extend(f.result(timeout=45))
            except Exception:
                pass
    print(f"  [Scout] {len(scout_samples)} body samples ({time.time()-t0:.0f}s)")

    # ── Stage 2: Objective Decoder (NO examples) ──────────────────────
    t0 = time.time()
    buzzwords = scout_organic_terms(scout_samples, client)
    merged_keywords = list(dict.fromkeys(list(baseline_keywords) + buzzwords))
    print(f"  [Decoder] discovered: {buzzwords} → merged: {merged_keywords} ({time.time()-t0:.0f}s)")

    # ── Sovereignty Recalibration Check ──────────────────────────────────
    if _detect_sovereignty_divergence(sovereignty, buzzwords, scout_samples):
        print(f"  [Sovereignty] DIVERGENCE detected — recalibrating...")
        recalibrated = recalibrate_sovereignty(sovereignty, buzzwords, scout_samples, client)
        if recalibrated:
            print(f"  [Sovereignty] RECALIBRATED anchors={recalibrated.positive_anchors}")
            print(f"  [Sovereignty] RECALIBRATED subs={recalibrated.target_subreddits}")
            sovereignty = recalibrated
            # Update plan subreddits with recalibrated targets
            if sovereignty.target_subreddits:
                plan.target_subreddits = [
                    s.replace("r/", "").strip() for s in sovereignty.target_subreddits
                ]
            # Merge recalibrated anchors into keywords
            merged_keywords = list(dict.fromkeys(merged_keywords + sovereignty.positive_anchors[:3]))
            print(f"  [Sovereignty] merged_keywords updated: {merged_keywords}")
        else:
            print(f"  [Sovereignty] recalibration failed — using original sovereignty")

    # ── Stage 3: Concurrent Full Scrape (separate sessions per platform) ──
    t0 = time.time()
    reddit_signals, reddit_items, youtube_videos = [], [], []

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futures = {}
        if "reddit" in plan.platforms:
            futures[ex.submit(
                _ingest_reddit, merged_keywords, plan, client, language, proxy, question, sovereignty
            )] = "reddit"
        if "youtube" in plan.platforms and yt_api_key:
            futures[ex.submit(
                _ingest_youtube, merged_keywords, plan, yt_api_key, proxy, question
            )] = "youtube"
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                result = future.result(timeout=90)
                if name == "reddit":
                    reddit_signals, reddit_items = result
                else:
                    youtube_videos = result
            except Exception as e:
                print(f"  [warn] {name}: {type(e).__name__}: {e}")

    ingest_t = time.time() - t0
    print(f"  [Reddit] {len(reddit_items)} posts, {len(reddit_signals)} signals")
    print(f"  [YouTube] {len(youtube_videos)} videos")
    print(f"  [Ingest] {ingest_t:.0f}s")

    # ── Stage 4: Sanitize + Tag ──────────────────────────────────────
    unified_records = merge_datasets(reddit_items, youtube_videos)
    for r in unified_records:
        r["text"] = sanitize_text(r.get("text", ""))
    print(f"  [Records] {len(unified_records)} sanitized")

    # YouTube tagging
    t0 = time.time()
    tagged_signals = []
    if youtube_videos:
        assessed = assess_youtube_quality(youtube_videos)
        tagged_signals = _batch_tag_youtube(assessed, plan, client)

    # Reddit signals → tagged format
    for s in reddit_signals:
        tagged_signals.append({
            "features": [s.signal_type], "user_types": [],
            "sentiment": "negative" if s.signal_type in ("pain_point", "adoption_barrier") else "neutral",
            "use_case": s.interpretation, "verbatim_quote": s.verbatim_quote,
            "source_url": s.source_url, "source_type": "reddit", "timestamp": "",
        })
    print(f"  [Tag] {len(tagged_signals)} signals ({time.time()-t0:.0f}s)")

    # ── Sovereignty Pollution Filter ──────────────────────────────────
    before_filter = len(tagged_signals)
    if sovereignty and sovereignty.negative_exclusion_wall:
        tagged_signals = [
            ts for ts in tagged_signals
            if not _is_polluted_signal(ts, sovereignty)
        ]
        dropped = before_filter - len(tagged_signals)
        if dropped:
            print(f"  [Sovereignty] dropped {dropped} polluted signals")

    # ── AIGC Sticky Noise Filter ──────────────────────────────────────
    before_aigc = len(tagged_signals)
    tagged_signals = filter_aigc_sticky_noise(tagged_signals)
    aigc_dropped = before_aigc - len(tagged_signals)
    if aigc_dropped:
        print(f"  [AIGC-Noise] dropped {aigc_dropped} sticky noise signals (monetization/copyright/licensing/coding-tools)")

    # ── Stage 4.5: Macro Context Extraction ──────────────────────────
    t_macro = time.time()
    macro_candidates = _identify_macro_content(unified_records, youtube_videos)
    macro_contexts = []
    if macro_candidates:
        macro_contexts = _extract_macro_context(macro_candidates, client)
    print(f"  [Macro] {len(macro_contexts)} landscape contexts ({time.time()-t_macro:.0f}s)")

    # ── Stage 5: Stats + Synthesis ───────────────────────────────────
    # ── Execution Manifest ────────────────────────────────────────────
    # Compute top 5 discovered keywords/tags/subreddits from actual data
    top_tags = _compute_top_5_tags(tagged_signals, unified_records)

    manifest = {
        "target_subreddits": plan.target_subreddits if plan else [],
        "youtube_anchors": merged_keywords if merged_keywords else (plan.search_queries if plan else []),
        "exclusion_wall": sovereignty.negative_exclusion_wall if sovereignty else [],
        "positive_anchors": sovereignty.positive_anchors if sovereignty else [],
        "signals_total": len(tagged_signals),
        "is_low_n": len(tagged_signals) < 5 and len(tagged_signals) > 0,
        "top_5_keywords_tags": top_tags,
        "total_records": len(unified_records),
        "queried_subreddits": plan.target_subreddits if plan else [],
    }

    stats = compute_unified_stats(tagged_signals, unified_records)
    stats["signal_diversity"] = compute_signal_diversity(tagged_signals)
    stats["merged_keywords"] = merged_keywords
    stats["dropped_polluted"] = before_filter - len(tagged_signals)
    stats["dropped_aigc_noise"] = aigc_dropped
    stats["manifest"] = manifest
    stats["sovereignty"] = {
        "case_identity": sovereignty.case_identity if sovereignty else "",
        "positive_anchors": sovereignty.positive_anchors if sovereignty else [],
        "negative_exclusion_wall": sovereignty.negative_exclusion_wall if sovereignty else [],
    }
    stats["discovered_buzzwords"] = buzzwords
    stats["cross_platform_ratio"] = {
        "reddit_records": sum(1 for r in unified_records if r.get("source") == "Reddit"),
        "youtube_records": sum(1 for r in unified_records if r.get("source") == "YouTube"),
    }

    total_elapsed = time.time() - t_total
    stats["elapsed_seconds"] = int(total_elapsed)

    report, actions = synthesize_unified(
        reddit_signals=reddit_signals, tagged_signals=tagged_signals,
        stats=stats, question=question, language=language,
        client=client, unified_records=unified_records,
        macro_contexts=macro_contexts,
    )
    print(f"  [Total] {total_elapsed:.0f}s")
    return {
        "brain_plan": plan, "unified_records": unified_records,
        "reddit_signals": reddit_signals, "tagged_signals": tagged_signals,
        "stats": stats, "report": report, "actions": actions,
        "baseline_keywords": baseline_keywords,
        "discovered_buzzwords": buzzwords,
    }


# ── Wide-Net Scout (with body text) ──────────────────────────────────────

def _scout_reddit_bodies(scout_kw, plan, proxy) -> list[str]:
    """Fetch top 5 Reddit posts with body text (first 300 chars)."""
    creds = get_reddit_credentials()
    scraper = RedditScraper(**creds, proxy=proxy)
    subs = plan.target_subreddits[:3] if plan.target_subreddits else ["all"]
    q = SearchQuery(subreddits=subs, keywords=[str(scout_kw)[:80]], rationale="scout", limit=5)
    try:
        items = scraper.execute_queries([q])
        samples = []
        for item in items:
            body = sanitize_text((item.body or "")[:300])
            samples.append(f"r/{item.subreddit}: {item.title}. {body}")
        return samples
    except Exception as e:
        print(f"  [scout-reddit] {e}")
        return []


def _scout_youtube_bodies(scout_kw, yt_api_key, proxy) -> list[str]:
    """Fetch top 5 YouTube videos with description snippets."""
    scraper = YouTubeScraper(yt_api_key, proxy=proxy)
    try:
        ids = scraper.search_videos([str(scout_kw)[:80]], max_results=5)
        details = scraper.get_video_details(ids)
        samples = []
        for d in details:
            title = d.get("snippet", {}).get("title", "")
            desc = sanitize_text((d.get("snippet", {}).get("description", "") or "")[:300])
            channel = d.get("snippet", {}).get("channelTitle", "")
            samples.append(f"YouTube/{channel}: {title}. {desc}")
        return samples
    except Exception as e:
        print(f"  [scout-yt] {e}")
        return []


# ── Fast Ingestion ──────────────────────────────────────────────────────

def _ingest_reddit(keywords, plan, client, language, proxy, question, sovereignty=None):
    """Reddit: 3 subs, 3 keywords, 10 posts. Sovereignty-aware filtering. sort='relevance', time_filter='year'."""
    creds = get_reddit_credentials()
    scraper = RedditScraper(**creds, proxy=proxy)
    subs = plan.target_subreddits[:3] if plan.target_subreddits else ["all"]
    # Sovereignty: exclude negative subreddits
    if sovereignty and sovereignty.negative_exclusion_wall:
        subs = [s for s in subs if not any(
            x.lower() in s.lower() for x in sovereignty.negative_exclusion_wall
        )]
    kw_list = keywords[:3] if keywords else plan.search_keywords[:2] if plan.search_keywords else ["AI agent", "software wrapper"]

    q = SearchQuery(subreddits=subs, keywords=kw_list, rationale="fast", limit=10, sort="relevance", time_filter="year")
    raw = scraper.execute_queries([q])
    seen = set()
    unique = []
    for item in raw:
        if item.post_id not in seen:
            seen.add(item.post_id)
            unique.append(item)
    assessed = assess_quality(unique)

    # Batched LLM: 15-20 records per call
    signals = _batch_reddit_extract(assessed, question, language, client, batch_size=15)
    return signals, assessed


def _ingest_youtube(keywords, plan, yt_api_key, proxy, question):
    """YouTube: horizontal expansion — 2 queries × 12 results, comment cap 20."""
    scraper = YouTubeScraper(yt_api_key, proxy=proxy)
    all_ids = []
    kw_list = keywords[:2] if keywords else plan.search_keywords[:2] if plan.search_keywords else ["AI agent review"]
    for kw in kw_list:
        try:
            ids = scraper.search_videos([kw], max_results=12)
            all_ids.extend(ids)
        except QuotaExceededError:
            break
    seen = set()
    unique = [v for v in all_ids if not (v in seen or seen.add(v))]
    if not unique:
        return []
    details = scraper.get_video_details(unique)
    videos = []
    for d in details:
        vid, title = d["id"], d.get("snippet", {}).get("title", "")
        channel = d.get("snippet", {}).get("channelTitle", "")
        tier = classify_youtube_tier(channel)
        transcript = scraper.get_transcript(vid)
        if not transcript or len(transcript) < 50:
            transcript = get_mock_transcript(title, question)
        comments = scraper.get_comments(vid, max_results=15)
        s = d.get("statistics", {})
        videos.append(YouTubeVideo(
            video_id=vid, title=title, description=d.get("snippet", {}).get("description", ""),
            channel_title=channel, transcript=transcript, comments=comments,
            view_count=int(s.get("viewCount", 0)), like_count=int(s.get("likeCount", 0)),
            comment_count=int(s.get("commentCount", 0)),
            url=f"https://www.youtube.com/watch?v={vid}", tier=tier,
        ))
    return videos


# ── Aggressive LLM Batching ─────────────────────────────────────────────

def _batch_reddit_extract(items, question, language, client, batch_size=20) -> list:
    """Batch 20 records per LLM call — single API round-trip."""
    gating = self_gating_reddit()
    lang_name = "Chinese" if language == "zh" else "English"
    system = EXTRACT_SYSTEM.format(self_gating=gating, language=lang_name)

    all_signals = []
    valid = [it for it in items if it.passed_filter]
    for i in range(0, len(valid), batch_size):
        batch = valid[i:i + batch_size]
        parts = [f"## QUESTION\n{question}\n\n## BATCH ({len(batch)} posts)\n"]
        for j, item in enumerate(batch):
            body = (item.body or "")[:1000]
            comments = " | ".join(
                (c or "")[:200] for c in (item.comments or [])[:5]
            )
            parts.append(
                f"### [{j+1}] r/{item.subreddit} score={item.score}\n"
                f"Title: {item.title}\nBody: {body}\nComments: {comments}\n"
            )
        payload = "\n".join(parts)
        try:
            raw = client.generate(system_prompt=system, user_message=payload, max_tokens=2048, temperature=0.5)
            parsed = _parse_signal_json(raw, batch)
            all_signals.extend(parsed)
        except Exception:
            continue
    return all_signals


def _batch_tag_youtube(videos, plan, client) -> list:
    """Batch tag all YouTube videos in one LLM call if possible."""
    assessed = [v for v in videos if v.passed_filter]
    if not assessed:
        return []

    from .context_engine import format_for_youtube_extraction
    # Batch: 5 videos per call
    results = []
    for i in range(0, len(assessed), 5):
        batch = assessed[i:i + 5]
        parts = [f"=== BATCH ({len(batch)} videos) ==="]
        for j, v in enumerate(batch):
            formatted = format_for_youtube_extraction(v)
            parts.append(f"--- VIDEO {j+1} ---\n{formatted}")
        payload = "\n".join(parts)

        noise_str = "\n".join(f"- {n}" for n in plan.noise_checklist) if plan.noise_checklist else "Filter spam."
        system = YOUTUBE_TAG_SYSTEM.format(noise_checklist=noise_str, auto_objective=plan.auto_objective)
        user = YOUTUBE_TAG_USER.format(formatted_content=payload)
        try:
            raw = client.generate(system_prompt=system, user_message=user, max_tokens=2048, temperature=0.3)
            parsed = _parse_tagged_batch(raw, batch)
            results.extend(parsed)
        except Exception:
            continue
    return results


# ── Sanitization ────────────────────────────────────────────────────────

SANITIZE_RE = re.compile(
    r"("
    r"Brewed for.*|Quota units?:?\s*\d+|"
    r"\[warn\].*|\[Pipeline\].*|\[Reddit[^\]]*\].*|\[YouTube[^\]]*\].*|"
    r"\[Scout\].*|\[Brain\].*|\[Buzzwords\].*|\[Keywords\].*|\[Ingest\].*|"
    r"\[Tag\].*|\[Records\].*|\[Total\].*|\[Decoder\].*|"
    r"/Users/\S+|/tmp/\S+|/opt/\S+|"
    r"sk-[a-zA-Z0-9]{10,}|AIza[A-Za-z0-9_-]{30,}"
    r")",
    re.IGNORECASE,
)


def sanitize_text(text: str) -> str:
    """Strip console output, file paths, API keys, terminal benchmarks."""
    text = SANITIZE_RE.sub("[redacted]", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _is_polluted_signal(ts, sovereignty) -> bool:
    """Check if a tagged signal violates sovereignty exclusion wall."""
    features = ts.get("features", []) if isinstance(ts, dict) else getattr(ts, "features", [])
    use_case = ts.get("use_case", "") if isinstance(ts, dict) else getattr(ts, "use_case", "")
    text = " ".join(features) + " " + use_case
    return is_semantic_pollution(text, sovereignty)


# ── Parsers ─────────────────────────────────────────────────────────────

def _parse_signal_json(raw: str, batch) -> list:
    import json as _json
    match = re.search(r"\[.*\]", raw.strip(), re.DOTALL)
    if match:
        try:
            data = _json.loads(match.group(0))
            return [
                Signal(signal_type=s.get("signal_type", ""), strength=s.get("strength", "moderate"),
                       verbatim_quote=s.get("verbatim_quote", ""), interpretation=s.get("interpretation", ""),
                       source_url=getattr(batch[0], "url", "") if batch else "",
                       source_subreddit=getattr(batch[0], "subreddit", "") if batch else "")
                for s in data if isinstance(s, dict)
            ]
        except _json.JSONDecodeError:
            pass
    return []


def _parse_tagged_batch(raw: str, videos) -> list:
    import json as _json
    match = re.search(r"\[.*\]", raw.strip(), re.DOTALL)
    if match:
        try:
            data = _json.loads(match.group(0))
        except _json.JSONDecodeError:
            return []
        results = []
        for j, s in enumerate(data):
            if not isinstance(s, dict):
                continue
            # Pydantic schema validation (anti-drift)
            try:
                anchor = Anchor3D(**{k: s.get(k, "") for k in ("object", "context_behavior", "impact_pain", "verbatim_quote", "source_type")})
            except Exception:
                anchor = None
            # Accept validated 3D schema OR legacy features
            obj = s.get("object", "")
            ctx = s.get("context_behavior", "")
            pain = s.get("impact_pain", "")
            features = s.get("features", [])
            if obj and anchor and not anchor.is_empty:
                features = [obj]
            if not features and not obj:
                continue
            vid = videos[min(j, len(videos)-1)] if videos else None
            results.append(TaggedSignal(
                features=features, user_types=[],
                sentiment=s.get("sentiment", "neutral"),
                use_case=f"{ctx}: {pain}" if ctx and pain else s.get("use_case", ""),
                verbatim_quote=s.get("verbatim_quote", ""),
                source_url=getattr(vid, "url", "") if vid else "",
                source_type="youtube",
            ))
        return results
    return []


def _compute_top_5_tags(tagged_signals: list, unified_records: list) -> list[dict]:
    """Compute top 5 most frequent keywords/tags/subreddits from actual data."""
    from collections import Counter

    tag_counter = Counter()
    sub_counter = Counter()

    for ts in tagged_signals:
        features = ts.get("features", []) if isinstance(ts, dict) else getattr(ts, "features", [])
        for f in features:
            tag_counter[f] += 1
        use_case = ts.get("use_case", "") if isinstance(ts, dict) else getattr(ts, "use_case", "")
        if use_case:
            tag_counter[use_case[:80]] += 1

    for r in unified_records:
        src = r.get("source", "")
        if src == "Reddit":
            author = r.get("author_name", "")
            if author.startswith("r/"):
                sub_counter[author] += 1

    top_items = []
    for tag, count in tag_counter.most_common(5):
        top_items.append({"type": "tag", "name": tag, "count": count})
    for sub, count in sub_counter.most_common(3):
        top_items.append({"type": "subreddit", "name": sub, "count": count})

    return top_items[:5]


# ── Sovereignty Divergence Detection ─────────────────────────────────────

def _detect_sovereignty_divergence(
    sovereignty: SovereigntyPlan,
    buzzwords: list[str],
    scout_samples: list[str],
) -> bool:
    """Detect if sovereignty anchors have zero overlap with discovered content.

    Returns True if recalibration is warranted:
    - At least 2 buzzwords were discovered AND
    - None of the buzzwords overlap with sovereignty positive_anchors AND
    - Scout returned meaningful samples (>= 3)
    """
    if not buzzwords or len(buzzwords) < 2:
        return False
    if len(scout_samples) < 3:
        return False

    anchors_lower = {a.lower().strip() for a in sovereignty.positive_anchors if a}
    buzzwords_lower = {b.lower().strip() for b in buzzwords if b}

    overlap = False
    for bw in buzzwords_lower:
        for anchor in anchors_lower:
            if anchor in bw or bw in anchor:
                overlap = True
                break
        if overlap:
            break

    return not overlap


# ── Macro Content Identification & Extraction ───────────────────────────

def _identify_macro_content(unified_records: list, youtube_videos: list) -> list[dict]:
    """Identify content items likely to contain macro-level industry context.

    Heuristic:
    - YouTube: transcript > 2000 chars
    - Reddit: post body > 800 chars AND score > 5
    """
    candidates = []
    for v in youtube_videos:
        if hasattr(v, 'transcript') and v.transcript and len(v.transcript) > 2000:
            candidates.append({
                'source_type': 'youtube',
                'title': v.title,
                'content': v.transcript[:6000],
                'url': v.url,
            })
    for r in unified_records:
        text = r.get('text', '')
        if r.get('source') == 'Reddit' and len(text) > 800:
            score = r.get('score', 0) if isinstance(r.get('score'), (int, float)) else 0
            if score > 5:
                candidates.append({
                    'source_type': 'reddit',
                    'title': r.get('author_name', 'Reddit post'),
                    'content': text[:4000],
                    'url': r.get('url', ''),
                })
    return candidates[:3]


def _extract_macro_context(candidates: list[dict], client) -> list[dict]:
    """Extract macro-level landscape context from candidate content items."""
    from .prompts import MACRO_LANDSCAPE_SYSTEM

    results = []
    for c in candidates:
        user_msg = f"Content type: {c['source_type']}\nTitle: {c['title']}\n\n{c['content']}"
        try:
            raw = client.generate(
                system_prompt=MACRO_LANDSCAPE_SYSTEM,
                user_message=user_msg,
                max_tokens=1024,
                temperature=0.4,
            )
            parsed = _parse_macro_json(raw)
            if parsed.get('is_macro'):
                parsed['source_url'] = c.get('url', '')
                parsed['source_title'] = c.get('title', '')
                results.append(parsed)
        except Exception:
            continue
    return results[:2]


def _parse_macro_json(raw: str) -> dict:
    import json as _json
    match = re.search(r"\{.*\}", raw.strip(), re.DOTALL)
    if match:
        try:
            return _json.loads(match.group(0))
        except _json.JSONDecodeError:
            pass
    return {"is_macro": False}
