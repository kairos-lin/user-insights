"""Context engineering: formats scraped content for optimal LLM consumption.

Three responsibilities:
1. Format raw Reddit data into structured LLM input (body/comments separation)
2. Truncate intelligently when content exceeds context budget
3. Annotate with metadata for accurate attribution
"""

import re

MAX_BODY_CHARS = 4000       # post body cap
MAX_COMMENT_CHARS = 500     # per-comment cap
MAX_COMMENTS = 20           # top N comments to include
MAX_TOTAL_WORDS = 6000      # overall content cap before aggressive truncation


def format_for_extraction(item, question: str) -> str:
    """Format a ScrapedContent item for the signal extraction LLM call.

    Returns a string with body and comments clearly separated, metadata
    annotated, and weight label prepended for LLM attention guidance.
    """
    weight_note = _weight_instruction(item.weight)

    body = _clean_text(item.body)
    body = _truncate_body(body)

    comments = item.comments[:MAX_COMMENTS]
    formatted_comments = []
    for i, c in enumerate(comments):
        cleaned = _clean_text(c)
        if len(cleaned) > MAX_COMMENT_CHARS:
            cleaned = cleaned[:MAX_COMMENT_CHARS] + "..."
        formatted_comments.append(f"[{i+1}] {cleaned}")

    comment_block = "\n\n".join(formatted_comments) if formatted_comments else "(no comments)"

    total_words = len(body.split()) + len(comment_block.split())
    if total_words > MAX_TOTAL_WORDS:
        body = _truncate_body_aggressive(body)
        # Reduce comments too
        reduced = formatted_comments[:10]
        comment_block = "\n\n".join(reduced) if reduced else "(no comments)"

    return f"""## ORIGINAL QUESTION
{question}

{weight_note}
## POST — r/{item.subreddit} | score: {item.score} | comments: {item.num_comments} | quality: {item.quality_score:.2f}
Title: {item.title}
{body}

## TOP COMMENTS (by score)
{comment_block}"""


def format_for_synthesis(signals: list, question: str) -> str:
    """Format all signals for the final synthesis LLM call."""
    if not signals:
        return f"## ORIGINAL QUESTION\n{question}\n\n## SIGNALS\n(No signals extracted — the scraped content did not yield relevant market intelligence.)"

    by_type: dict[str, list] = {}
    for s in signals:
        by_type.setdefault(s.signal_type, []).append(s)

    blocks = [f"## ORIGINAL QUESTION\n{question}\n\n## EXTRACTED SIGNALS ({len(signals)} total)\n"]
    for sig_type, items in sorted(by_type.items()):
        blocks.append(f"### {sig_type.replace('_', ' ').title()} ({len(items)})")
        for s in items:
            blocks.append(
                f"- **Strength**: {s.strength} | **Source**: r/{s.source_subreddit}\n"
                f"  **Quote**: \"{s.verbatim_quote}\"\n"
                f"  **Interpretation**: {s.interpretation}"
            )
        blocks.append("")

    return "\n".join(blocks)


def format_for_youtube_extraction(video) -> str:
    """Format a YouTubeVideo for the structured tagging LLM call.

    Body/transcript and comments clearly separated for differentiated analysis.
    """
    if hasattr(video, "transcript"):
        transcript = video.transcript or "(no transcript available)"
        description = video.description or ""
        title = video.title
        comments = video.comments or []
        channel = video.channel_title
        views = video.view_count
    else:
        transcript = video.get("transcript", "") or "(no transcript available)"
        description = video.get("description", "") or ""
        title = video.get("title", "")
        comments = video.get("comments", []) or []
        channel = video.get("channel_title", "")
        views = video.get("view_count", 0)

    # Truncate transcript
    if len(transcript) > 4000:
        transcript = transcript[:4000] + "\n\n[...truncated...]"

    # Format comments
    comment_lines = []
    for i, c in enumerate(comments[:20]):
        cleaned = _clean_text(str(c))
        if len(cleaned) > 300:
            cleaned = cleaned[:300] + "..."
        comment_lines.append(f"[{i+1}] {cleaned}")
    comment_block = "\n\n".join(comment_lines) if comment_lines else "(no comments)"

    return f"""## VIDEO — {channel} | views: {views:,}
Title: {title}
Description: {description[:500]}

## TRANSCRIPT
{transcript}

## TOP COMMENTS (by relevance)
{comment_block}"""


def format_for_youtube_synthesis(tagged_signals: list, stats: dict, question: str) -> str:
    """Format tagged signals and pulse stats for the final synthesis call."""
    lines = [f"## ORIGINAL QUESTION\n{question}\n"]

    # Quantitative pulse
    lines.append("## Quantitative Pulse (computed by Python — use these exact numbers)")
    from .stats_aggregator import format_pulse_markdown
    lines.append(format_pulse_markdown(stats))

    # Tagged signals detail
    lines.append(f"\n## Tagged Signals ({len(tagged_signals)} total)\n")
    for i, ts in enumerate(tagged_signals):
        feats = _get_field(ts, "features", [])
        uts = _get_field(ts, "user_types", [])
        sent = _get_field(ts, "sentiment", "neutral")
        uc = _get_field(ts, "use_case", "")
        quote = _get_field(ts, "verbatim_quote", "")
        src = _get_field(ts, "source_url", "")
        src_type = _get_field(ts, "source_type", "")

        lines.append(f"### Signal {i+1}: {', '.join(feats) if feats else 'General'}")
        lines.append(f"- **Features**: {', '.join(feats) if feats else 'N/A'}")
        lines.append(f"- **User Types**: {', '.join(uts) if uts else 'N/A'}")
        lines.append(f"- **Sentiment**: {sent}")
        lines.append(f"- **Use Case**: {uc}")
        lines.append(f"- **Quote**: > {quote}")
        lines.append(f"- **Source**: [{src_type}] {src}")
        lines.append("")

    return "\n".join(lines)


def _get_field(obj, key, default):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _weight_instruction(weight: str) -> str:
    if weight == "high":
        return "[WEIGHT: HIGH — analyze thoroughly]"
    elif weight == "low":
        return "[WEIGHT: LOW — skim, only extract if signal is clearly present]"
    return "[WEIGHT: MEDIUM — standard analysis]"


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    # Collapse excessive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _truncate_body(body: str) -> str:
    if len(body) <= MAX_BODY_CHARS:
        return body
    return body[:MAX_BODY_CHARS] + "\n\n[...truncated...]"


def _truncate_body_aggressive(body: str) -> str:
    limit = MAX_BODY_CHARS // 2
    if len(body) <= limit:
        return body
    return body[:limit] + "\n\n[...truncated for length...]"
