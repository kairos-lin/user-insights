"""System Sovereignty Initialization Layer — zero-history Meta-Parser.

Runs BEFORE any data fetching. Defines the problem's sovereign borders
to prevent Context Bleed and Semantic Hijacking.

Output: strict JSON with case_identity, domain_sovereignty,
positive_anchors, negative_exclusion_wall, asymmetry_mapping_strategy.
"""

import json
import re

from .api_client import APIClient
from .models import SovereigntyPlan

META_PARSER_SYSTEM = """You are a System Sovereignty Initialization node. Your purpose is to define the EXACT semantic boundaries for a market research query to prevent context bleed and semantic hijacking.

Given a raw query, you must output a strict JSON schema that will act as a runtime guardrail for the entire pipeline. Be specific and aggressive.

{
  "case_identity": "Clear definition of the core behavior, target audience, and research purpose",
  "domain_sovereignty": "Allowed boundaries — which domains/topics are strictly valid for this query",
  "positive_anchors": ["Core tech components, entities, or industry-specific slang to prioritize — max 5"],
  "negative_exclusion_wall": ["High-risk overlapping noise terms, adjacent-but-irrelevant topics, or competitor domains to AGGRESSIVELY block — max 5"],
  "target_subreddits": ["Exact Reddit subreddit names where this community LIVES — e.g., r/PPC, r/adops, r/simracing, r/StableDiffusion. DO NOT default to r/webdev or r/programming"],
  "target_channels": ["YouTube channel names or search modifiers relevant to this domain"],
  "asymmetry_mapping_strategy": {
    "youtube_expectation_focus": "Specific hype/cognitive angles to capture on YouTube",
    "reddit_reality_focus": "Specific operational friction/failure points to capture on Reddit"
  }
}

CRITICAL Rules:
- target_subreddits MUST be the EXACT Reddit communities where practitioners discuss this topic. If the topic is ad-tech, use r/PPC, r/adops, r/marketing. If hardware sim racing, use r/simracing, r/Fanatec. NEVER default to r/webdev or r/programming.
- negative_exclusion_wall MUST explicitly block adjacent-but-irrelevant domains (e.g., for ad-tech, block "web development" and "programming tutorials").
- positive_anchors MUST use the domain's actual terminology, not generic business words.
- This workflow serves PRODUCT and MARKET intelligence, not academic research. When the query mentions "products", "tools", or "commercial offerings", positive_anchors MUST prioritize commercial product names (e.g., Tripo, Meshy, Rodin) over research methods (e.g., NeRF, Gaussian Splatting). If you are uncertain about specific product names, include the general product category as an anchor for broader discovery.
- target_subreddits MUST balance TWO dimensions: (a) communities where USERS of the product/tool gather and discuss their experience (e.g., r/StableDiffusion, r/blender, r/gamedev), AND (b) communities focused on the product category itself (e.g., r/3Dmodeling, r/AI3D). Include at least one community from each dimension. Do NOT drop user/discussion communities in favor of only category communities.
- CRITICAL for AI-powered tools: the user discussion community is often an AI-generation subreddit (e.g., r/StableDiffusion for AI 3D tools, r/ClaudeAI for AI coding tools), NOT a traditional domain subreddit. ALWAYS include the relevant AI-generation community as one of the target_subreddits.

STICKY NOISE DETECTION — If the query is about creative AIGC WORKFLOW FRICTION (visual generation, content template automation, media asset production), you MUST include in negative_exclusion_wall:
- "monetization", "pricing models", "copyright", "licensing", "AI adoption sentiment", "agency business models", "is AI art real", "will AI replace artists"
- These are STICKY NOISE — adjacent but irrelevant to hands-on operational friction.
- Focus positive_anchors on: "ComfyUI", "control net", "prompt engineering fatigue", "node-wiring", "A1111", "inpainting", "img2img", "output consistency", "asset pipeline", "SDXL", "workflow automation".

Output ONLY the JSON object. No other text."""


def init_sovereignty(question: str, client: APIClient) -> SovereigntyPlan:
    """Zero-history Meta-Parser call. Runs before any data fetching."""
    raw = client.generate(
        system_prompt=META_PARSER_SYSTEM,
        user_message=f"Query: {question}\n\nOutput the sovereignty JSON.",
        max_tokens=1024,
        temperature=0.2,
    )
    data = _parse_sovereignty_json(raw)
    return SovereigntyPlan(
        case_identity=data.get("case_identity", ""),
        domain_sovereignty=data.get("domain_sovereignty", ""),
        positive_anchors=data.get("positive_anchors", []),
        negative_exclusion_wall=data.get("negative_exclusion_wall", []),
        target_subreddits=data.get("target_subreddits", []),
        target_channels=data.get("target_channels", []),
        youtube_expectation_focus=data.get("asymmetry_mapping_strategy", {}).get("youtube_expectation_focus", ""),
        reddit_reality_focus=data.get("asymmetry_mapping_strategy", {}).get("reddit_reality_focus", ""),
    )


def is_semantic_pollution(obj: str, sovereignty: SovereigntyPlan) -> bool:
    """Check if an extracted object is closer to exclusion wall than domain sovereignty.

    Simple heuristic: if the object contains any negative_exclusion_wall term
    and does NOT contain any positive_anchor term, flag as pollution.
    """
    obj_lower = obj.lower()
    pos_match = any(a.lower() in obj_lower for a in sovereignty.positive_anchors if a)
    neg_match = any(x.lower() in obj_lower for x in sovereignty.negative_exclusion_wall if x)
    return neg_match and not pos_match


SOVEREIGNTY_RECALIBRATE_SYSTEM = """You are a System Sovereignty recalibration node. The initial sovereignty plan was generated blindly (no data). Now you have real-world search results showing what terminology and communities ACTUALLY exist for this topic.

Review the original sovereignty plan and the discovered content. If the original plan is accurate, return it unchanged. If the content reveals important communities or terminology the original plan missed, EXPAND the plan conservatively.

Rules:
- You may ADD to positive_anchors and target_subreddits, but NEVER remove from the original.
- CRITICAL: Examine scout samples for clues about WHERE these discussions are happening. If the content references specific subreddits, or if the terminology clearly belongs to a community not in the original target_subreddits, ADD that community (e.g., if you see Stable Diffusion workflows discussed, add r/StableDiffusion; if AI tool comparisons appear, add r/AI3D or r/artificial).
- You may REMOVE from negative_exclusion_wall if a term was incorrectly blocked (false positive exclusion).
- You may ADD to negative_exclusion_wall if discovered content is clearly noise.
- The case_identity should be refined but not fundamentally changed.
- Prefer commercial product names over research methods in positive_anchors.

Original sovereignty:
{original_sovereignty}

Discovered organic terminology: {buzzwords}

Scout content samples:
{scout_samples}

Output the UPDATED sovereignty JSON with the same structure. Output ONLY JSON."""


def recalibrate_sovereignty(
    original: SovereigntyPlan,
    buzzwords: list[str],
    scout_samples: list[str],
    client,
) -> SovereigntyPlan | None:
    """Recalibrate sovereignty when scout content reveals missed communities/terms.

    Only called when divergence is detected. Returns None if recalibration
    fails, allowing the pipeline to fall back to original sovereignty.
    """
    if not buzzwords and not scout_samples:
        return None

    original_json = json.dumps({
        "case_identity": original.case_identity,
        "domain_sovereignty": original.domain_sovereignty,
        "positive_anchors": original.positive_anchors,
        "negative_exclusion_wall": original.negative_exclusion_wall,
        "target_subreddits": original.target_subreddits,
        "target_channels": original.target_channels,
        "asymmetry_mapping_strategy": {
            "youtube_expectation_focus": original.youtube_expectation_focus,
            "reddit_reality_focus": original.reddit_reality_focus,
        },
    }, indent=2)

    samples_text = "\n\n---\n\n".join(
        f"[Sample {i+1}] {s[:400]}" for i, s in enumerate(scout_samples[:8])
    )

    system = SOVEREIGNTY_RECALIBRATE_SYSTEM.format(
        original_sovereignty=original_json,
        buzzwords=", ".join(buzzwords) if buzzwords else "(none discovered)",
        scout_samples=samples_text,
    )

    try:
        raw = client.generate(
            system_prompt=system,
            user_message="Recalibrate the sovereignty plan based on the discovered content above.",
            max_tokens=1024,
            temperature=0.3,
        )
        data = _parse_sovereignty_json(raw)
        return SovereigntyPlan(
            case_identity=data.get("case_identity", original.case_identity),
            domain_sovereignty=data.get("domain_sovereignty", original.domain_sovereignty),
            positive_anchors=data.get("positive_anchors", original.positive_anchors),
            negative_exclusion_wall=data.get("negative_exclusion_wall", original.negative_exclusion_wall),
            target_subreddits=data.get("target_subreddits", original.target_subreddits),
            target_channels=data.get("target_channels", original.target_channels),
            youtube_expectation_focus=data.get("asymmetry_mapping_strategy", {}).get("youtube_expectation_focus", original.youtube_expectation_focus),
            reddit_reality_focus=data.get("asymmetry_mapping_strategy", {}).get("reddit_reality_focus", original.reddit_reality_focus),
        )
    except Exception:
        return None


def _parse_sovereignty_json(raw: str) -> dict:
    json_str = raw.strip()
    match = re.search(r"\{.*\}", json_str, re.DOTALL)
    if match:
        json_str = match.group(0)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return {
            "case_identity": "General market research",
            "domain_sovereignty": "All domains",
            "positive_anchors": [],
            "negative_exclusion_wall": [],
            "asymmetry_mapping_strategy": {"youtube_expectation_focus": "", "reddit_reality_focus": ""},
        }
