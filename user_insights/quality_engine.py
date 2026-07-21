"""Quality engine: autonomous data quality assessment.

Two layers:
1. Heuristic layer (zero token cost) — filters, scores, weights content pre-LLM
2. Self-gating instruction — LLM decides per-item whether to extract signals

Pipeline: raw content → heuristic filter → quality_score → weight tier → LLM self-gating

Supports both Reddit (ScrapedContent) and YouTube (YouTubeVideo) content types.
"""

import json
import os

from .models import ScrapedContent

# Pre-defined authority weights for market-research-relevant subreddits.
# Unknown subreddits default to 0.5 (neutral).
SUB_REDDIT_AUTHORITY = {
    # Entrepreneurship / startups
    "startups": 0.90, "entrepreneur": 0.85, "smallbusiness": 0.80,
    "sideproject": 0.80, "indiehackers": 0.85, "SaaS": 0.90,
    "growthmarketing": 0.85, "marketing": 0.80, "SEO": 0.75,
    # Tech / product
    "technology": 0.75, "programming": 0.70, "webdev": 0.70,
    "MachineLearning": 0.80, "datascience": 0.75, "artificial": 0.80,
    "ProductManagement": 0.85, "UXDesign": 0.75, "userexperience": 0.75,
    # Productivity / tools
    "productivity": 0.70, "Notion": 0.90, "Figma": 0.90,
    "slack": 0.85, "airtable": 0.85, "clickup": 0.85,
    "obsidian": 0.85, "logseq": 0.85, "notionapp": 0.85,
    # General discussion (useful for broad sentiment)
    "AskReddit": 0.50, "changemyview": 0.65, "TrueReddit": 0.70,
    "DepthHub": 0.75, "Freetalk": 0.40,
}

# ── Reddit-Friendly Thresholds (Phase 3) ──────────────────────────
# Reddit's informal culture: short witty complaints, sarcasm, slang,
# personal anecdotes are HIGH-SIGNAL. Only filter truly empty/spam.
REDDIT_MIN_BODY_LENGTH = 10      # chars — very permissive for short complaints
REDDIT_MIN_COMMENT_LENGTH = 15   # chars — keep one-liners like "vibe coding is trash"
REDDIT_MIN_ENGAGEMENT = 0        # keep even 0-score posts if body exists
REDDIT_MAX_URL_DENSITY = 10      # more lenient for resource-sharing posts

# YouTube thresholds (stricter)
YOUTUBE_MIN_BODY_LENGTH = 50
YOUTUBE_MIN_SCORE_OR_COMMENTS = 2
YOUTUBE_MAX_URL_DENSITY = 5

# Legacy thresholds (used by Reddit path via assess_quality)
MIN_BODY_LENGTH = REDDIT_MIN_BODY_LENGTH
MIN_SCORE_OR_COMMENTS = REDDIT_MIN_ENGAGEMENT
MAX_URL_DENSITY = REDDIT_MAX_URL_DENSITY


def assess_quality(items: list[ScrapedContent]) -> list[ScrapedContent]:
    """Run heuristic quality assessment on scraped items.

    Filters out noise, computes quality scores, assigns weight tiers.
    Returns only items that pass the heuristic filter, sorted by quality.
    """
    passed = []
    for item in items:
        if not _passes_heuristic_filter(item):
            item.passed_filter = False
            continue
        item.quality_score = _compute_score(item)
        item.passed_filter = True
        passed.append(item)

    if not passed:
        return []

    # Assign weight tiers: top third = high, bottom third = low
    passed.sort(key=lambda x: x.quality_score, reverse=True)
    n = len(passed)
    for i, item in enumerate(passed):
        if i < n / 3:
            item.weight = "high"
        elif i < 2 * n / 3:
            item.weight = "medium"
        else:
            item.weight = "low"

    return passed


def _passes_heuristic_filter(item: ScrapedContent) -> bool:
    body = item.body.strip()

    # Removed or deleted
    if body in ("[removed]", "[deleted]", ""):
        return False

    # Too short (link posts with no text)
    if len(body) < MIN_BODY_LENGTH:
        return False

    # No engagement at all
    if item.score < MIN_SCORE_OR_COMMENTS and item.num_comments == 0:
        return False

    # URL spam detection
    url_count = body.count("http://") + body.count("https://")
    if url_count > MAX_URL_DENSITY and len(body) < 500:
        return False

    return True


def _compute_score(item: ScrapedContent) -> float:
    """Compute quality score 0.0–1.0 from engagement and content signals."""
    body = item.body
    subreddit = item.subreddit.lower().lstrip("r/")

    score_component = min(item.score / 100.0, 1.0)           # community validation
    comment_component = min(item.num_comments / 30.0, 1.0)    # discussion depth
    body_component = min(len(body) / 2000.0, 1.0)             # content depth
    authority_component = SUB_REDDIT_AUTHORITY.get(subreddit, 0.5)  # domain relevance

    return (
        0.30 * score_component
        + 0.20 * comment_component
        + 0.30 * body_component
        + 0.20 * authority_component
    )


def self_gating_instruction() -> str:
    """Legacy: generic self-gating."""
    return (
        "If this content is off-topic, irrelevant to the question, purely promotional, "
        "or contains no substantive market intelligence, return an empty list: []. "
        "Do not force signals from noise. Quality over quantity."
    )


def self_gating_reddit() -> str:
    """Reddit-specific self-gating: keep informal, sarcasm, slang, anecdotes.

    ONLY filter: automated bot sticky comments, [deleted]/[removed] posts,
    hardware setup noise that is completely off-topic.
    """
    return (
        "REDDIT-SPECIFIC FILTER RULES:\n"
        "- DO keep: sarcasm, short witty complaints, developer slang (e.g. 'vibe coding', 'ai slop', 'wrapper'), informal personal anecdotes.\n"
        "- Treat informal personal anecdotes as HIGH-SIGNAL evidence — they reveal authentic user sentiment.\n"
        "- ONLY drop: completely irrelevant automated bot sticky comments, [deleted]/[removed] posts, or hardware setup noise unrelated to the question.\n"
        "- If in doubt, KEEP the signal. Over-filtering is worse than under-filtering for Reddit.\n"
        "- If content is clearly off-topic, return []."
    )


def self_gating_youtube() -> str:
    """YouTube-specific self-gating: strict on spam, promos, empty praise."""
    return (
        "YOUTUBE-SPECIFIC FILTER RULES:\n"
        "- Strictly remove: affiliate links, channel self-promotions ('subscribe to my channel', 'check out my video'), generic appreciation spam ('Great video!', 'Thanks for sharing!').\n"
        "- Keep: technical critiques, feature comparisons, migration stories, detailed user experiences.\n"
        "- If content is purely promotional or contains no substantive market intelligence, return []."
    )


# ── YouTube Tier Weights (Phase 3) ───────────────────────────────────

def _load_tier_config() -> dict:
    path = os.path.join(os.path.dirname(__file__), "..", "config", "source_bias.json")
    path = os.path.normpath(path)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def classify_youtube_tier(channel_title: str) -> str:
    """Classify a YouTube channel into tier_1, tier_2, or tier_3.

    tier_1 (weight 1.5): Independent bloggers, <500k subs, high signal
    tier_2 (weight 1.0): End-users, review channels, unknown channels
    tier_3 (weight 0.2): Brand media, sponsored, corporate channels
    """
    cfg = _load_tier_config()
    overrides = cfg.get("tier_overrides", {})
    blacklist = cfg.get("blacklist", {})

    if channel_title in blacklist:
        return "tier_3"
    if channel_title in overrides:
        return overrides[channel_title]
    # Heuristic: brand/corporate channels often have short, capitalized names
    # or names containing "Official", "TV", "Channel"
    lower = channel_title.lower()
    corporate_markers = ["official", " inc", " llc", " corp", "channel", "tv", "media", "news"]
    if any(m in lower for m in corporate_markers):
        return "tier_3"
    return "tier_2"


def get_youtube_tier_weight(tier: str) -> float:
    cfg = _load_tier_config()
    weights = cfg.get("tier_weights", {"tier_1": 1.5, "tier_2": 1.0, "tier_3": 0.2})
    return weights.get(tier, 1.0)


def assess_youtube_quality(videos: list) -> list:
    """Run quality assessment on YouTubeVideo items.

    Filters noise, computes quality scores from view/like/comment metrics,
    assigns weight tiers based on channel classification.
    """
    from .models import YouTubeVideo as YTV

    passed = []
    for v in videos:
        if isinstance(v, YTV):
            body = v.transcript or v.description
        else:
            body = v.get("transcript", "") or v.get("description", "")

        # Basic heuristic filter
        if not body or len(body) < 50:
            if isinstance(v, YTV):
                v.passed_filter = False
            continue

        # Compute quality score from engagement
        if isinstance(v, YTV):
            score = _compute_youtube_score(v.view_count, v.like_count, v.comment_count)
            v.quality_score = score
            v.passed_filter = True
        else:
            v["quality_score"] = _compute_youtube_score(
                v.get("view_count", 0), v.get("like_count", 0), v.get("comment_count", 0)
            )
            v["passed_filter"] = True

        passed.append(v)

    if not passed:
        return []

    # Sort and assign weight tiers
    def get_score(x):
        if isinstance(x, YTV):
            return x.quality_score
        return x.get("quality_score", 0.0)

    passed.sort(key=get_score, reverse=True)
    n = len(passed)
    for i, item in enumerate(passed):
        weight = "medium"
        if i < n / 3:
            weight = "high"
        elif i >= 2 * n / 3:
            weight = "low"
        if isinstance(item, YTV):
            item.weight = weight
        else:
            item["weight"] = weight

    return passed


def _compute_youtube_score(views: int, likes: int, comments: int) -> float:
    view_score = min(views / 100000.0, 1.0)   # 100K views = max
    like_score = min(likes / 5000.0, 1.0)      # 5K likes = max
    comment_score = min(comments / 200.0, 1.0)  # 200 comments = max
    return 0.3 * view_score + 0.3 * like_score + 0.4 * comment_score


# ── AIGC Sticky Noise Filter ───────────────────────────────────────────

AIGC_STICKY_NOISE = [
    "monetization", "pricing model", "copyright", "licensing",
    "ai adoption sentiment", "agency business model", "how to charge",
    "is ai art real", "will ai replace artists", "ai vs human",
    "subscription pricing", "saas pricing", "freemium",
    "how to make money", "passive income", "side hustle",
    "legal implications", "intellectual property",
    "cursor ai", "copilot", "github copilot", "v0 dev", "bolt.new",
    "coding assistant", "code generation", "developer tool",
]


def is_aigc_sticky_noise(text: str) -> bool:
    """Check if text contains AIGC sticky noise terms that must be filtered.

    Returns True if the text is about monetization, copyright, licensing,
    general AI adoption sentiment, or coding tools — NOT hands-on creative
    workflow friction.
    """
    lower = text.lower()
    for term in AIGC_STICKY_NOISE:
        if term.lower() in lower:
            return True
    return False


def filter_aigc_sticky_noise(signals: list) -> list:
    """Remove signals that match AIGC sticky noise terms. Keeps only
    hands-on operational friction signals (ComfyUI, prompt engineering,
    control-net, node-wiring, asset consistency, output slop)."""
    aigc_focus_terms = [
        "comfyui", "comfy ui", "automatic1111", "a1111", "controlnet", "control net",
        "prompt engineer", "node wir", "node-wir", "inpaint", "img2img",
        "workflow", "pipeline", "render", "asset", "output", "slop",
        "sdxl", "stable diffusion", "midjourney", "dalle", "dall-e",
        "lora", "checkpoint", "vae", "upscal", "denois",
        "layer", "seed", "batch", "consistent",
    ]
    filtered = []
    for s in signals:
        features = s.get("features", []) if isinstance(s, dict) else getattr(s, "features", [])
        use_case = s.get("use_case", "") if isinstance(s, dict) else getattr(s, "use_case", "")
        text = " ".join(features) + " " + use_case

        if is_aigc_sticky_noise(text):
            # Only drop if it does NOT also contain workflow friction terms
            lower = text.lower()
            if not any(t in lower for t in aigc_focus_terms):
                continue
        filtered.append(s)
    return filtered


def compute_signal_diversity(tagged_signals: list) -> dict:
    """Measure how diverse the extracted signals are.

    Low diversity + low count = possible sovereignty bias failure.
    Used as a post-hoc diagnostic, not a pipeline gate.
    """
    if not tagged_signals:
        return {"unique_features": 0, "unique_sources": 0, "diversity_score": 0.0}

    all_features = set()
    all_sources = set()
    for ts in tagged_signals:
        feats = ts.get("features", []) if isinstance(ts, dict) else getattr(ts, "features", [])
        src_url = ts.get("source_url", "") if isinstance(ts, dict) else getattr(ts, "source_url", "")
        for f in feats:
            all_features.add(f.lower())
        all_sources.add(src_url)

    unique_features = len(all_features)
    unique_sources = len(all_sources)
    total = len(tagged_signals)

    feature_ratio = unique_features / max(total, 1)
    source_ratio = unique_sources / max(total, 1)
    diversity_score = round(feature_ratio * 0.6 + source_ratio * 0.4, 2)

    return {
        "unique_features": unique_features,
        "unique_sources": unique_sources,
        "total_signals": total,
        "diversity_score": diversity_score,
    }
