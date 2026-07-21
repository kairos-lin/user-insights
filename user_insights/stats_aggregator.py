"""Cross-platform statistical aggregation. Pure Python, no LLM.

Takes normalized unified records + tagged signals and computes:
- Overall sentiment distribution
- Platform voice share (Reddit % vs YouTube %)
- Top emerging tags/themes ranked globally
- Cross-tabulation across platforms and user types
"""

from collections import Counter, defaultdict


def compute_unified_stats(tagged_signals: list, unified_records: list) -> dict:
    """Compute cross-platform statistics from tagged signals and unified records.

    Args:
        tagged_signals: list of TaggedSignal objects or dicts
        unified_records: list of normalized records from data_normalizer

    Returns dict ready for report formatting.
    """
    total = len(tagged_signals)

    # ── Platform voice share ─────────────────────────────────────────
    platform_counts = Counter()
    platform_features = defaultdict(Counter)
    for ts in tagged_signals:
        src = _get(ts, "source_type", "unknown")
        platform = "YouTube" if src == "youtube" else "Reddit"
        platform_counts[platform] += 1
        for f in _get(ts, "features", []):
            platform_features[platform][f] += 1

    # ── Overall features (term-aligned) ──────────────────────────────
    from .term_mapper import normalize_features
    all_features = Counter()
    for ts in tagged_signals:
        features = _get(ts, "features", [])
        normalized = normalize_features(features)
        for f in normalized:
            all_features[f] += 1

    # ── Sentiment distribution ───────────────────────────────────────
    sentiments = Counter()
    platform_sentiment = defaultdict(Counter)
    for ts in tagged_signals:
        sent = _get(ts, "sentiment", "neutral")
        sentiments[sent] += 1
        src = _get(ts, "source_type", "unknown")
        platform = "YouTube" if src == "youtube" else "Reddit"
        platform_sentiment[platform][sent] += 1

    # ── User type breakdown ──────────────────────────────────────────
    user_types = Counter()
    for ts in tagged_signals:
        for ut in _get(ts, "user_types", []):
            user_types[ut] += 1

    # ── Unified record stats ─────────────────────────────────────────
    reddit_records = sum(1 for r in unified_records if r.get("source") == "Reddit")
    youtube_records = sum(1 for r in unified_records if r.get("source") == "YouTube")

    # ── Cross-tabulation: platform × feature ─────────────────────────
    cross_tabs = {}
    for platform, features in platform_features.items():
        cross_tabs[platform] = dict(features.most_common(10))

    # ── Dynamic Statistical Gates (Phase 4) ─────────────────────────
    MACRO_THRESHOLD_PCT = 3.0      # ≥3% of total pool → Dominant Narrative
    SPROUTING_MIN_MENTIONS = 2     # ≥2 mentions → Emerging Theme
    macro_threshold_count = max(2, int(total * MACRO_THRESHOLD_PCT / 100))

    qualified_features = [
        (f, c) for f, c in all_features.most_common() if c >= macro_threshold_count
    ]
    sprouting_features = [
        (f, c) for f, c in all_features.most_common()
        if SPROUTING_MIN_MENTIONS <= c < macro_threshold_count
    ]
    disqualified_features = [
        (f, c) for f, c in all_features.most_common() if c < SPROUTING_MIN_MENTIONS
    ]

    return {
        "total_signals": total,
        "total_records": len(unified_records),
        "reddit_records": reddit_records,
        "youtube_records": youtube_records,
        "macro_threshold_pct": MACRO_THRESHOLD_PCT,
        "macro_threshold_count": macro_threshold_count,
        "sprouting_min_mentions": SPROUTING_MIN_MENTIONS,
        "qualified_features_count": len(qualified_features),
        "sprouting_features_count": len(sprouting_features),
        "platform_voice_share": {
            platform: {
                "count": platform_counts.get(platform, 0),
                "pct": round(platform_counts.get(platform, 0) / max(total, 1) * 100, 1),
            }
            for platform in ["Reddit", "YouTube"]
        },
        "sentiment_overall": {k: round(v / max(total, 1) * 100, 1) for k, v in sentiments.most_common()},
        "sentiment_by_platform": {
            p: {k: round(v / max(sum(sent_counts.values()), 1) * 100, 1) for k, v in sent_counts.items()}
            for p, sent_counts in platform_sentiment.items()
        },
        "top_features": qualified_features[:5],  # ≥macro threshold (Dominant Narratives)
        "sprouting_features": sprouting_features[:5],  # ≥2 but <threshold (Emerging Themes)
        "top_features_all": all_features.most_common(10),
        "disqualified_features": disqualified_features[:5],
        "user_types": user_types.most_common(10),
        "cross_tabs": cross_tabs,
    }


def format_unified_stats_markdown(stats: dict) -> str:
    """Format unified stats as markdown for the synthesis report."""
    if stats.get("total_signals", 0) == 0:
        return "_No cross-platform quantitative data available._"

    lines = []

    # Sentiment
    lines.append("### Overall Sentiment Distribution")
    for sent, pct in stats.get("sentiment_overall", {}).items():
        lines.append(f"- **{sent}**: {pct}%")
    lines.append("")

    # Platform voice share
    lines.append("### Platform Voice Share")
    pvs = stats.get("platform_voice_share", {})
    for platform, info in pvs.items():
        lines.append(f"- **{platform}**: {info.get('count', 0)} signals ({info.get('pct', 0)}%)")
    lines.append(f"- **Total records analyzed**: {stats.get('total_records', 0)} (Reddit: {stats.get('reddit_records', 0)}, YouTube: {stats.get('youtube_records', 0)})")
    lines.append("")

    # Top features
    lines.append("### Top 5 Emerging Tags/Themes (Cross-Platform)")
    for i, (feat, count) in enumerate(stats.get("top_features", [])[:5]):
        pct = round(count / max(stats.get("total_signals", 1), 1) * 100, 1)
        lines.append(f"{i+1}. **{feat}**: {count} mentions ({pct}%)")
    lines.append("")

    # Cross-tabulation
    if stats.get("cross_tabs"):
        lines.append("### Platform × Feature Cross-Tabulation")
        for platform, features in stats["cross_tabs"].items():
            feat_str = ", ".join(f"{f} ({c})" for f, c in list(features.items())[:5])
            lines.append(f"- **{platform}**: {feat_str}")
        lines.append("")

    # User types
    lines.append("### User Type Breakdown")
    for ut, count in stats.get("user_types", []):
        pct = round(count / max(stats.get("total_signals", 1), 1) * 100, 1)
        lines.append(f"- **{ut}**: {count} ({pct}%)")
    lines.append("")

    return "\n".join(lines)


# Keep legacy function for backward compatibility
def compute_pulse(tagged_signals: list) -> dict:
    """Legacy: compute pulse from tagged signals (single-platform)."""
    return compute_unified_stats(tagged_signals, [])


def format_pulse_markdown(stats: dict) -> str:
    """Legacy: format pulse as markdown."""
    return format_unified_stats_markdown(stats)


def _get(obj, key, default):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
