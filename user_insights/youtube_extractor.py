"""Phase 3: YouTube content processing — transcript + comment extraction.

Pipeline per video:
1. Format video context + comments via context_engine
2. LLM pass (low temp, JSON mode): Extract structured TaggedSignal
3. Returns list of TaggedSignal for stats aggregation
"""

import json
import re

from .api_client import APIClient
from .context_engine import format_for_youtube_extraction
from .models import TaggedSignal, YouTubeVideo
from .prompts import YOUTUBE_TAG_CLI_SYSTEM, YOUTUBE_TAG_USER


def tag_youtube_content(
    videos: list[YouTubeVideo],
    auto_objective: str,
    noise_checklist: list[str],
    client: APIClient,
    max_items: int = 10,
) -> list[TaggedSignal]:
    """Process each YouTubeVideo through LLM for structured tagging.

    Sorted by weight (high first), capped at max_items.
    Each video gets one LLM call for both transcript and comments.
    """
    weight_order = {"high": 0, "medium": 1, "low": 2}
    sorted_videos = sorted(videos, key=lambda x: weight_order.get(x.weight, 1))
    to_process = sorted_videos[:max_items]

    noise_str = "\n".join(f"- {n}" for n in noise_checklist) if noise_checklist else "Filter out spam and irrelevant content."
    system = YOUTUBE_TAG_CLI_SYSTEM.format(
        noise_checklist=noise_str,
        auto_objective=auto_objective,
    )

    results: list[TaggedSignal] = []
    for v in to_process:
        if not v.passed_filter:
            continue

        formatted = format_for_youtube_extraction(v)
        user_msg = YOUTUBE_TAG_USER.format(formatted_content=formatted)

        try:
            raw = client.generate(
                system_prompt=system,
                user_message=user_msg,
                max_tokens=1024,
                temperature=0.3,
            )
            tagged = _parse_tagged_signal(raw, v)
            if tagged and tagged.features:  # Only include if features found
                results.append(tagged)
        except Exception:
            continue

    return results


def _parse_tagged_signal(raw: str, video: YouTubeVideo) -> TaggedSignal | None:
    json_str = raw.strip()
    match = re.search(r"\{.*\}", json_str, re.DOTALL)
    if match:
        json_str = match.group(0)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return None

    return TaggedSignal(
        features=data.get("features", []),
        user_types=data.get("user_types", []),
        sentiment=data.get("sentiment", "neutral"),
        use_case=data.get("use_case", ""),
        verbatim_quote=data.get("verbatim_quote", ""),
        source_url=video.url,
        source_type="youtube",
        timestamp=data.get("timestamp", ""),
    )
