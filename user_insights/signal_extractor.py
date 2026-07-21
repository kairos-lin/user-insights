"""Step 3: Extract market signals from scraped content, per-item."""

import json
import re

from .api_client import APIClient
from .context_engine import format_for_extraction
from .models import ScrapedContent, Signal
from .prompts import EXTRACT_SYSTEM, EXTRACT_USER
from .quality_engine import self_gating_reddit


def extract_signals(
    items: list[ScrapedContent],
    question: str,
    language: str,
    client: APIClient,
    max_items: int = 20,
) -> list[Signal]:
    """Process each ScrapedContent item individually through the LLM.

    Per-item processing prevents context dilution and ensures accurate
    verbatim quote attribution. The LLM self-gates: irrelevant items
    return empty signals.

    Items are sorted by quality weight (high first) and capped at max_items
    to keep runtime practical. Typical: 10-20 items for a research session.
    """
    # Prioritize high-weight items, cap for runtime
    weight_order = {"high": 0, "medium": 1, "low": 2}
    sorted_items = sorted(items, key=lambda x: weight_order.get(x.weight, 1))
    items_to_process = sorted_items[:max_items]

    all_signals: list[Signal] = []
    gating = self_gating_reddit()  # Use Reddit-permissive filter
    system = EXTRACT_SYSTEM.format(self_gating=gating, language=_lang_name(language))

    for i, item in enumerate(items_to_process):
        if not item.passed_filter:
            continue

        formatted = format_for_extraction(item, question)
        user_msg = EXTRACT_USER.format(formatted_content=formatted)

        try:
            raw = client.generate(
                system_prompt=system,
                user_message=user_msg,
                max_tokens=2048,
                temperature=0.5,
            )
            signals = _parse_signals(raw, item)
            all_signals.extend(signals)
        except Exception as e:
            print(f"  [warn] Signal extraction failed for r/{item.subreddit} post {item.post_id}: {e}")
            continue

    return all_signals


def _parse_signals(raw: str, source: ScrapedContent) -> list[Signal]:
    json_str = raw.strip()
    match = re.search(r"\[.*\]", json_str, re.DOTALL)
    if match:
        json_str = match.group(0)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    signals = []
    for s in data:
        if not isinstance(s, dict):
            continue
        signals.append(Signal(
            signal_type=s.get("signal_type", "trend_observation"),
            strength=s.get("strength", "moderate"),
            verbatim_quote=s.get("verbatim_quote", ""),
            interpretation=s.get("interpretation", ""),
            source_url=source.url,
            source_subreddit=source.subreddit,
            weight=source.weight,
        ))

    return signals


def _lang_name(code: str) -> str:
    return "Chinese" if code == "zh" else "English"
