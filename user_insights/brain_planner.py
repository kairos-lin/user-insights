"""Stateless Objective Brain Planner — no predefined biases.

Phase 1: Wide-net scout fetcher grabs titles + body snippets (first 300 chars).
Phase 2: Objective decoder LLM extracts organic terminology WITHOUT examples.
"""

import json
import os
import re

from .api_client import APIClient
from .models import BrainPlan
from .prompts import BRAIN_PLANNER_SYSTEM, BRAIN_PLANNER_USER


def load_source_bias() -> dict:
    path = os.path.join(os.path.dirname(__file__), "..", "config", "source_bias.json")
    path = os.path.normpath(path)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def route_query(question: str, client: APIClient) -> tuple[BrainPlan, list[str]]:
    """Stateless brain planner. Returns (plan, baseline_keywords)."""
    bias = load_source_bias()

    user_msg = BRAIN_PLANNER_USER.format(question=question)
    raw = client.generate(
        system_prompt=BRAIN_PLANNER_SYSTEM,
        user_message=user_msg,
        max_tokens=1024,
        temperature=0.3,
    )

    plan_dict = _parse_brain_plan(raw)
    domain = plan_dict.get("domain", "General_Sentiment")
    domain_config = bias.get(domain, {})

    search_queries = plan_dict.get("search_queries", [])
    if not search_queries:
        search_queries = plan_dict.get("search_keywords", [])
    baseline_keywords = plan_dict.get("baseline_keywords", [])
    if not baseline_keywords:
        baseline_keywords = plan_dict.get("search_keywords", [])[:2]
    if not baseline_keywords:
        # Extract key terms from the question as fallback
        words = [w for w in question.split() if len(w) > 3 and w.lower() not in ("what", "that", "this", "with", "from", "they", "their", "them", "about", "which", "there", "these", "those")]
        baseline_keywords = [" ".join(words[:3])] if words else ["AI tools"]

    plan = BrainPlan(
        domain=domain,
        platforms=plan_dict.get("platforms", ["youtube", "reddit"]),
        auto_objective=plan_dict.get("auto_objective", ""),
        noise_checklist=plan_dict.get("noise_checklist", []),
        search_keywords=plan_dict.get("search_keywords", []),
        search_queries=search_queries[:4],
        target_channels=domain_config.get("youtube_channels", []),
        target_subreddits=domain_config.get("reddit_subs", []),
    )

    return plan, baseline_keywords


# ── Objective Scout ──────────────────────────────────────────────────────

SCOUT_SYSTEM = """You are an objective linguistic analyst. Analyze these raw search results from social media platforms.

What specific terminology, tool names, or descriptive phrases is this community ACTUALLY using in the text?

Extract 2-3 organic, highly specific query strings (e.g., a recurring frustration, a specific software combo, or a niche technical term) that appear naturally in these texts.

DO NOT invent terms. ONLY extract phrases that visibly appear in the provided text. If none found, output [].

Output ONLY a JSON array of strings. No other text."""


def scout_organic_terms(samples: list[str], client: APIClient) -> list[str]:
    """Objective decoder: extract organic terms from body text samples.

    NO predefined examples — prevents hallucination.
    Samples include YouTube descriptions and Reddit post bodies (first 300 chars).
    """
    if not samples or len(samples) < 2:
        return []

    samples_text = "\n\n---\n\n".join(
        f"[Sample {i+1}]\n{s[:600]}" for i, s in enumerate(samples[:10])
    )

    try:
        raw = client.generate(
            system_prompt=SCOUT_SYSTEM,
            user_message=samples_text,
            max_tokens=128,
            temperature=0.3,
        )
        terms = _parse_json_array(raw)
        discovered = [t.strip() for t in terms if isinstance(t, str) and 3 < len(t.strip()) < 80]
        return discovered[:3]
    except Exception:
        return []


# ── Helpers ───────────────────────────────────────────────────────────────

def _parse_brain_plan(raw: str) -> dict:
    json_str = raw.strip()
    match = re.search(r"\{.*\}", json_str, re.DOTALL)
    if match:
        json_str = match.group(0)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return {
            "domain": "General_Sentiment",
            "platforms": ["youtube", "reddit"],
            "auto_objective": "Understand general market sentiment",
            "noise_checklist": ["spam"],
            "search_queries": [],
            "baseline_keywords": [],
        }


def _parse_json_array(raw: str) -> list:
    raw = raw.strip()
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        raw = match.group(0)
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []
