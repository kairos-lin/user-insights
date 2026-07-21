"""Synthesis: generate unified market intelligence report.

Supports the new unified report format:
  # EXECUTIVE BRIEF
  ## 1. Quantitative Market Pulse
  ## 2. Deep-Dive Narrative Detection
  ## 3. Drill-down Proof (Verbatim Anchors)
  ## 4. Strategic Business Actions
"""

import json
import re

from .api_client import APIClient
from .context_engine import format_for_synthesis
from .models import BusinessAction, Signal
from .stats_aggregator import format_unified_stats_markdown


UNIFIED_REPORT_SYSTEM = """You are a strategic market advisor. Synthesize cross-platform signals into an intelligence report. Platform asymmetry is a FEATURE — YouTube reveals buyer expectations and macro trends; Reddit reveals practitioner friction and operational reality.

Write in {language}. Be evidence-based. Be concise.

AIGC WORKFLOW FRICTION FILTER — If the query is about creative AIGC workflows, AGGRESSIVELY drop: monetization, pricing models, copyright, licensing, "how to charge for AI work", AI adoption sentiment, "is AI art real" debates, agency business models, general coding tools (Cursor, Copilot). Focus EXCLUSIVELY on hands-on operational friction: ComfyUI node-wiring, prompt engineering fatigue, control-net failures, asset inconsistency, output slop cleanup, SDXL/checkpoint issues, rendering pipeline breakage, inpainting failures.

SEMANTIC BRIDGING RULES (apply before writing):
1. IF (object distance is close AND impact_pain matches) AND (context_behavior is identical) → MANDATORILY merge into a single "Cross-Platform Validated Narrative", even if literal keywords differ.
2. IF (context_behavior is different, e.g., YouTube="Hobbyist Coding Acceleration" vs Reddit="Enterprise Technical Debt") → MANDATORILY segregate into distinct single-platform observations. DO NOT force-merge.
3. Platform asymmetry is insight: YouTube shows what buyers EXPECT; Reddit shows what practitioners actually EXPERIENCE.

The report MUST follow this structure exactly. DO NOT skip or reorder any section:

## Detailed Analysis

### 1. Market Landscape & Industry Context
(Use the macro landscape data if provided. If none, synthesize a brief landscape from the signal data.)
- **Industry Consensus**: What practitioners broadly agree on.
- **Competitive Landscape**: Key players and their positioning.
- **Market Trends**: Observable directional shifts.
- **Unresolved Tensions**: Open debates or contradictions.

### 2. Quantitative Market Pulse
(Use ONLY the Python-computed statistics provided below. Quote percentages precisely from the data.)
- **Overall Sentiment Distribution:** (from provided stats — state exact percentages)
- **Platform Voice Share:** "We analyzed X signals from Reddit and Y signals from YouTube (from a total dataset of Z records)."
- **Top 5 Emerging Tags/Themes:** Ranked globally from provided stats.

### 3. Expectation vs. Operational Reality Matrix

#### YouTube Domain (Perceived Value & Buyer Expectations)
Target audience: Buyers, Explorers, Decision-makers.
- What promises are being made? What is the "dream" being sold?
- Map 2-3 specific Expectation Signals with verbatim quotes.

#### Reddit Domain (Operational Reality & Practitioner Friction)
Target audience: Practitioners, Skeptics, Engineers.
- Production bottlenecks, edge-case failures, and real-world limitations.
- Map 2-3 specific Reality Signals with verbatim quotes.

#### Divergence Analysis
- Where does YouTube hype diverge from Reddit reality?
- What emerging consensus exists across BOTH platforms?

### 4. Strategic Recommendations
Prioritized list. Each recommendation must have: suggestion, rationale, risk.
Do NOT include timeline or expected_outcome fields.

## Evidence & Methodology

### Verbatim Source Table
| Platform | Source/Author | Verbatim Quote | object | context_behavior | impact_pain | URL |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
(Fill with real signals. At least 2 Reddit + 2 YouTube. Preserve EXACT verbatim quotes.)

Output ONLY the sections above (Detailed Analysis + Evidence & Methodology). The report header and Executive Answer are generated separately. Do NOT repeat them."""


def synthesize(
    signals: list[Signal],
    question: str,
    language: str,
    client: APIClient,
) -> tuple[str, list[BusinessAction]]:
    """Legacy path: Reddit-only signals. Kept for backward compatibility."""
    formatted = format_for_synthesis(signals, question)
    system = UNIFIED_REPORT_SYSTEM.format(
        language=_lang_name(language), question=question
    )
    raw = client.generate(
        system_prompt=system,
        user_message=formatted,
        max_tokens=8192,
        temperature=0.7,
    )
    actions = _extract_actions(raw)
    return raw, actions


def synthesize_unified(
    reddit_signals: list[Signal],
    tagged_signals: list,
    stats: dict,
    question: str,
    language: str,
    client: APIClient,
    unified_records: list | None = None,
    macro_contexts: list | None = None,
) -> tuple[str, list[BusinessAction]]:
    """Two-phase synthesis: Executive Answer → Detailed Analysis + Evidence.

    Phase 1: Executive Answer — plain-language summary for PM/Founder (60s read).
    Phase 2: Detailed Analysis + Evidence — structured deep-dive with verbatim proof.
    Execution Manifest is generated in Python (non-optional, appended to Evidence).
    """
    manifest = stats.get("manifest", {})
    lang_name = _lang_name(language)

    # ── Report Header ──────────────────────────────────────────────────
    report = _build_report_header(question, stats, manifest)

    # ── Execution Manifest (Python, auditable pipeline trail) ──────────
    report += _build_execution_manifest(manifest, stats, tagged_signals)

    # ── Phase 1: Executive Answer ──────────────────────────────────────
    from .prompts import EXECUTIVE_ANSWER_SYSTEM
    exec_payload = _build_executive_payload(
        tagged_signals, stats, macro_contexts, question
    )
    exec_system = EXECUTIVE_ANSWER_SYSTEM.format(language=lang_name)
    executive_answer = client.generate(
        system_prompt=exec_system,
        user_message=exec_payload,
        max_tokens=1024,
        temperature=0.6,
    )
    report += "\n## Executive Answer\n\n" + executive_answer.strip() + "\n"

    # ── Phase 2: Detailed Analysis + Evidence ──────────────────────────
    data_payload = _build_llm_data_payload(
        reddit_signals, tagged_signals, stats, unified_records, question, macro_contexts
    )

    system = UNIFIED_REPORT_SYSTEM.format(
        language=lang_name, question=question
    )

    raw = client.generate(
        system_prompt=system,
        user_message=data_payload,
        max_tokens=8192,
        temperature=0.7,
    )

    actions = _extract_actions(raw)
    report += "\n---\n\n" + raw

    return report, actions


def _build_executive_payload(
    tagged_signals: list,
    stats: dict,
    macro_contexts: list | None,
    question: str,
) -> str:
    """Build a concise data payload for the Executive Answer LLM call."""
    parts = [f"# Research Question\n{question}\n"]

    # Key stats
    pvs = stats.get("platform_voice_share", {})
    reddit_n = pvs.get("Reddit", {}).get("count", 0)
    yt_n = pvs.get("YouTube", {}).get("count", 0)
    total_signals = stats.get("total_signals", len(tagged_signals))
    total_records = stats.get("total_records", 0)

    parts.append(f"## Key Numbers\n"
                 f"- {total_signals} signals extracted from {total_records} records\n"
                 f"- Reddit: {reddit_n} signals | YouTube: {yt_n} signals\n"
                 f"- Sentiment: {_fmt_pct(stats, 'neutral')}% neutral, "
                 f"{_fmt_pct(stats, 'negative')}% negative, "
                 f"{_fmt_pct(stats, 'positive')}% positive\n")

    # Top tags
    manifest = stats.get("manifest", {})
    top_5 = manifest.get("top_5_keywords_tags", [])
    if top_5:
        tag_str = ", ".join(f"{t.get('name', '')} ({t.get('count', 0)})" for t in top_5[:5])
        parts.append(f"- Top signals: {tag_str}\n")

    # Signal diversity
    div = stats.get("signal_diversity", {})
    if div:
        parts.append(f"- Signal diversity: {div.get('diversity_score', 'N/A')} "
                     f"({div.get('unique_features', 0)} unique features, "
                     f"{div.get('unique_sources', 0)} unique sources)\n")

    # Macro context summary
    if macro_contexts:
        parts.append("## Market Landscape Context\n")
        for mc in macro_contexts:
            parts.append(f"- Consensus: {mc.get('industry_consensus', '')}")
            parts.append(f"- Trends: {mc.get('market_trends', '')}")
            parts.append(f"- Tensions: {mc.get('unresolved_tensions', '')}")
            parts.append(f"- Summary: {mc.get('evidence_summary', '')}\n")

    # Signal highlights (top 8 most substantive)
    parts.append("## Key Signal Highlights\n")
    count = 0
    for ts in tagged_signals[:15]:
        features = ts.get("features", []) if isinstance(ts, dict) else getattr(ts, "features", [])
        sentiment = ts.get("sentiment", "") if isinstance(ts, dict) else getattr(ts, "sentiment", "")
        use_case = ts.get("use_case", "") if isinstance(ts, dict) else getattr(ts, "use_case", "")
        verbatim = ts.get("verbatim_quote", "") if isinstance(ts, dict) else getattr(ts, "verbatim_quote", "")
        if verbatim and len(verbatim) > 20:
            parts.append(f"- [{sentiment}] {verbatim[:200]}")
            count += 1
            if count >= 8:
                break

    return "\n".join(parts)


def _fmt_pct(stats: dict, key: str) -> str:
    sent = stats.get("sentiment_distribution", {})
    pct = sent.get(key, 0)
    if isinstance(pct, (int, float)):
        return str(round(pct, 1))
    return str(pct)


def _build_report_header(question: str, stats: dict, manifest: dict) -> str:
    """Generate the mandatory report header + brief."""
    elapsed = stats.get("elapsed_seconds", 0)
    signals = manifest.get("signals_total", stats.get("total_signals", 0))
    lines = [
        "# Market Intelligence Report",
        f"**Query**: {question}",
        f"**Elapsed**: {elapsed}s | **Signals Analyzed**: {signals}",
        "",
    ]
    return "\n".join(lines)


def _build_execution_manifest(manifest: dict, stats: dict, tagged_signals: list) -> str:
    """Build the mandatory Execution Manifest section from Python-computed data."""
    targets = manifest.get("target_subreddits", [])
    target_str = ", ".join(f"r/{s}" for s in targets) if targets else "none"

    yt_anchors = manifest.get("youtube_anchors", [])
    yt_str = ", ".join(f'"{a}"' for a in yt_anchors) if yt_anchors else "none"

    exclusion = manifest.get("exclusion_wall", [])
    exclusion_str = ", ".join(exclusion) if exclusion else "none (no active exclusion wall)"

    top_5 = manifest.get("top_5_keywords_tags", [])
    if top_5:
        top_parts = []
        for item in top_5:
            t = item.get("type", "")
            n = item.get("name", "")
            c = item.get("count", 0)
            top_parts.append(f"{n} ({c})")
        top_str = ", ".join(top_parts)
    else:
        top_str = "none (insufficient data)"

    low_n = manifest.get("is_low_n", False)
    low_n_note = "\n* **(LOW-N Alpha Signals — treat each signal as high-value)**" if low_n else ""

    lines = [
        "## Execution Manifest",
        f"* **Target Subreddits Reached**: {target_str}",
        f"* **YouTube Anchors Used**: {yt_str}",
        f"* **Active Exclusion Wall**: {exclusion_str}",
        f"* **Top 5 Discovered Keywords/Tags/Subreddits**: {top_str}",
        f"* **Total Records Processed**: {manifest.get('total_records', stats.get('total_records', 0))}{low_n_note}",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def _build_llm_data_payload(
    reddit_signals: list,
    tagged_signals: list,
    stats: dict,
    unified_records: list | None,
    question: str,
    macro_contexts: list | None = None,
) -> str:
    """Build the structured data payload for LLM synthesis (Detailed Analysis + Evidence)."""
    parts = []

    # Header context
    parts.append(f"# RESEARCH CONTEXT\nQuery: {question}\n")

    # Macro landscape data for Section 1
    if macro_contexts:
        parts.append("## MACRO LANDSCAPE DATA (use for Market Landscape section)\n")
        for i, mc in enumerate(macro_contexts):
            parts.append(f"### Source {i+1}: {mc.get('source_title', 'Unknown')}")
            parts.append(f"- Industry Consensus: {mc.get('industry_consensus', 'N/A')}")
            parts.append(f"- Competitive Landscape: {mc.get('competitive_landscape', 'N/A')}")
            parts.append(f"- Market Trends: {mc.get('market_trends', 'N/A')}")
            parts.append(f"- Unresolved Tensions: {mc.get('unresolved_tensions', 'N/A')}")
            parts.append(f"- Evidence: {mc.get('evidence_summary', 'N/A')}")
            refs = mc.get('source_references', [])
            if refs:
                parts.append(f"- Source References: {'; '.join(refs[:3])}")
            parts.append(f"- URL: {mc.get('source_url', 'N/A')}")
            parts.append("")
    else:
        parts.append("## MACRO LANDSCAPE DATA\n_No macro-level landscape content identified. Synthesize a brief landscape from the signal data below._\n")

    # Cross-platform summary
    xp = stats.get("cross_platform_ratio", {})
    parts.append(f"## DATA SUMMARY\n")
    parts.append(f"- Total records analyzed: {stats.get('total_records', 0)}")
    parts.append(f"- Reddit records: {xp.get('reddit_records', 0)} | YouTube records: {xp.get('youtube_records', 0)}")
    parts.append(f"- Total signals extracted: {stats.get('total_signals', 0)}")
    parts.append(f"- Cross-platform validated: {stats.get('cross_platform_validated', 0)}")
    parts.append(f"- Anecdotal/single-platform only: {stats.get('anecdotal_only', 0)}")
    parts.append("")

    # Quantitative Pulse (Python-computed — LLM must use these exact numbers)
    parts.append("## QUANTITATIVE PULSE DATA (use these exact numbers)\n")
    parts.append(format_unified_stats_markdown(stats))

    # Platform voice share
    pvs = stats.get("platform_voice_share", {})
    reddit_count = pvs.get("Reddit", {}).get("count", 0)
    yt_count = pvs.get("YouTube", {}).get("count", 0)
    parts.append(f"\nPlatform voice share: {reddit_count} Reddit signals + {yt_count} YouTube signals.\n")

    # Reddit signals
    parts.append(f"\n## REDDIT SIGNALS ({len(reddit_signals)} total)\n")
    by_type: dict[str, list] = {}
    for s in reddit_signals:
        by_type.setdefault(s.signal_type, []).append(s)
    for sig_type, items in sorted(by_type.items()):
        parts.append(f"### {sig_type.replace('_', ' ').title()} ({len(items)})")
        for s in items:
            parts.append(
                f"- **{s.strength}** | r/{s.source_subreddit}\n"
                f"  Quote: \"{s.verbatim_quote}\"\n"
                f"  Interpretation: {s.interpretation}"
            )
        parts.append("")

    # YouTube tagged signals
    parts.append(f"\n## YOUTUBE TAGGED SIGNALS ({len(tagged_signals)} total)\n")
    for i, ts in enumerate(tagged_signals):
        feats = _get(ts, "features", [])
        sent = _get(ts, "sentiment", "neutral")
        uc = _get(ts, "use_case", "")
        quote = _get(ts, "verbatim_quote", "")
        src = _get(ts, "source_url", "")
        src_type = _get(ts, "source_type", "youtube")
        parts.append(f"### {src_type.upper()}-{i+1}: {', '.join(feats) if feats else 'General'}")
        parts.append(f"- Features: {', '.join(feats) if feats else 'N/A'}")
        parts.append(f"- Sentiment: {sent} | Use Case: {uc}")
        parts.append(f"- Quote: > {quote}")
        parts.append(f"- Source: {src}")
        parts.append("")

    # Unified records sample
    if unified_records:
        parts.append(f"\n## UNIFIED DATASET SAMPLES ({len(unified_records)} total records)\n")
        for r in unified_records[:15]:
            parts.append(
                f"- [{r.get('source', '')}] {r.get('author_name', '')}: "
                f"{r.get('text', '')[:200]}..."
            )
        parts.append("")

    parts.append("\n---\n")
    parts.append("Generate sections 1-4 of the report using the data above. "
                 "Use EXACT numbers from QUANTITATIVE PULSE DATA. "
                 "Follow the report template exactly.")

    return "\n".join(parts)


def _extract_actions(raw: str) -> list[BusinessAction]:
    """Parse structured actions from the report."""
    match = re.search(r"```json\s*(\[.*?\])\s*```", raw, re.DOTALL)
    if not match:
        match = re.search(r'\[.*?"action".*?\]', raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0) if not match.lastindex else match.group(1))
            actions = []
            for a in data:
                if isinstance(a, dict):
                    actions.append(BusinessAction(
                        action=a.get("action", ""),
                        rationale=a.get("rationale", ""),
                        expected_outcome="",
                        timeline="",
                        risk=a.get("risk", ""),
                        priority=a.get("priority", 1),
                    ))
            return actions
        except (json.JSONDecodeError, IndexError):
            pass

    actions = []
    section_match = re.search(
        r"### 4\. Strategic Recommendations\s*\n(.*?)(?=\n#|\Z)", raw, re.DOTALL
    )
    if section_match:
        items = re.findall(
            r"(?:^|\n)\d+\.\s*\*\*(.+?)\*\*(.*?)(?=\n\d+\.|\Z)",
            section_match.group(1), re.DOTALL,
        )
        for i, (action_title, details) in enumerate(items):
            actions.append(BusinessAction(
                action=action_title.strip(),
                rationale=details.strip()[:200],
                expected_outcome="",
                timeline="",
                risk="",
                priority=i + 1,
            ))
    return actions


def _lang_name(code: str) -> str:
    return "Chinese" if code == "zh" else "English"


def _get(obj, key, default):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
