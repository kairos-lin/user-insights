"""Step 1: Decompose user question into Reddit search queries."""

import json
import re

from .api_client import APIClient
from .models import SearchQuery
from .prompts import DECOMPOSE_SYSTEM, DECOMPOSE_USER


def decompose_question(question: str, client: APIClient) -> list[SearchQuery]:
    """Break a user question into concrete Reddit search queries."""
    user_msg = DECOMPOSE_USER.format(question=question)
    raw = client.generate(
        system_prompt=DECOMPOSE_SYSTEM,
        user_message=user_msg,
        max_tokens=2048,
        temperature=0.3,
    )
    return _parse_queries(raw)


def detect_language(question: str) -> str:
    """Simple detection: if significant Chinese characters present, treat as zh."""
    chinese_chars = sum(1 for c in question if "一" <= c <= "鿿")
    return "zh" if chinese_chars > 3 else "en"


def _parse_queries(raw: str) -> list[SearchQuery]:
    # Extract JSON array from possibly noisy LLM output
    json_str = raw.strip()
    # Try to find JSON array if wrapped in markdown or text
    match = re.search(r"\[.*\]", json_str, re.DOTALL)
    if match:
        json_str = match.group(0)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Fallback: try to extract individual objects
        objects = re.findall(r"\{[^}]+\}", json_str, re.DOTALL)
        data = []
        for obj_str in objects:
            try:
                data.append(json.loads(obj_str))
            except json.JSONDecodeError:
                continue
        if not data:
            return [_fallback_query()]

    queries = []
    for item in data:
        try:
            queries.append(SearchQuery(
                subreddits=item.get("subreddits", ["all"]),
                keywords=item.get("keywords", []),
                rationale=item.get("rationale", ""),
                content_focus=item.get("content_focus", "both"),
                sort=item.get("sort", "relevance"),
                time_filter=item.get("time_filter", "year"),
                limit=10,
            ))
        except Exception:
            continue

    return queries if queries else [_fallback_query()]


def _fallback_query() -> SearchQuery:
    return SearchQuery(
        subreddits=["all"],
        keywords=[],
        rationale="Fallback: broad search",
        content_focus="both",
        sort="relevance",
        time_filter="year",
    )
