from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError


class Anchor3D(BaseModel):
    """Strict 3D-anchor schema for tagging node output validation."""
    object: str = ""
    context_behavior: str = ""
    impact_pain: str = ""
    verbatim_quote: str = ""
    source_type: str = "youtube"

    @property
    def is_empty(self) -> bool:
        return not self.object and not self.impact_pain


@dataclass
class SovereigntyPlan:
    """Meta-Parser output: sovereign borders for the pipeline."""
    case_identity: str = ""
    domain_sovereignty: str = ""
    positive_anchors: list[str] = field(default_factory=list)
    negative_exclusion_wall: list[str] = field(default_factory=list)
    target_subreddits: list[str] = field(default_factory=list)
    target_channels: list[str] = field(default_factory=list)
    youtube_expectation_focus: str = ""
    reddit_reality_focus: str = ""


# ── Platform-agnostic search planning ─────────────────────────────────

@dataclass
class BrainPlan:
    """LLM output: autonomous routing decision."""
    domain: str                    # Tech_Deep_Dive | Business_Growth | General_Sentiment
    platforms: list[str]           # ["youtube"] | ["reddit"] | ["youtube", "reddit"]
    auto_objective: str            # Internal research objective
    noise_checklist: list[str]     # Things to filter out
    search_keywords: list[str]     # legacy: 2-3 keywords
    search_queries: list[str] = field(default_factory=list)  # 3 distinct queries for multi-angle coverage
    target_channels: list[str] = field(default_factory=list)
    target_subreddits: list[str] = field(default_factory=list)


@dataclass
class SearchQuery:
    """Reddit search query (existing, unchanged)."""
    subreddits: list[str]
    keywords: list[str]
    rationale: str
    content_focus: str = "both"
    sort: str = "top"
    time_filter: str = "month"
    limit: int = 10


# ── Content containers ────────────────────────────────────────────────

@dataclass
class ScrapedContent:
    """Reddit post (existing, unchanged)."""
    platform: str                  # "reddit"
    subreddit: str
    post_id: str
    title: str
    body: str
    url: str
    score: int
    num_comments: int
    created_utc: str
    comments: list[str] = field(default_factory=list)
    quality_score: float = 0.0
    weight: str = "medium"
    passed_filter: bool = True


@dataclass
class YouTubeVideo:
    """YouTube video with transcript and comments."""
    video_id: str
    title: str
    description: str
    channel_title: str
    transcript: str               # yt-dlp extracted (0 quota cost)
    comments: list[str] = field(default_factory=list)
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    url: str = ""
    tier: str = "tier_2"          # tier_1 | tier_2 | tier_3
    quality_score: float = 0.0
    weight: str = "medium"
    passed_filter: bool = True


# ── Extracted intelligence ────────────────────────────────────────────

@dataclass
class TaggedSignal:
    """Structured LLM output: tagged market intelligence from one content item."""
    features: list[str]           # [Feature Mentioned]
    user_types: list[str]         # [User Type]
    sentiment: str                # positive | negative | neutral
    use_case: str                 # [Use Case]
    verbatim_quote: str
    source_url: str
    source_type: str              # youtube | reddit
    timestamp: str = ""           # video timestamp or comment position


@dataclass
class Signal:
    """Legacy signal (kept for Reddit path compatibility)."""
    signal_type: str
    strength: str
    verbatim_quote: str
    interpretation: str
    source_url: str
    source_subreddit: str = ""
    weight: str = "medium"


@dataclass
class MacroContext:
    """Extracted macro-level industry landscape from long-form content."""
    is_macro: bool = False
    industry_consensus: str = ""
    competitive_landscape: str = ""
    market_trends: str = ""
    unresolved_tensions: str = ""
    evidence_summary: str = ""
    source_references: list[str] = field(default_factory=list)
    source_url: str = ""
    source_title: str = ""


# ── Output ────────────────────────────────────────────────────────────

@dataclass
class BusinessAction:
    action: str
    rationale: str
    expected_outcome: str
    timeline: str
    risk: str
    priority: int = 1


# ── Session management ────────────────────────────────────────────────

@dataclass
class StepState:
    name: str
    status: str = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Session:
    folder_path: str
    timestamp: str
    question: str = ""
    language: str = "en"
    brain_plan: dict | None = None
    queries: list = field(default_factory=list)
    scraped_items: list = field(default_factory=list)
    youtube_videos: list = field(default_factory=list)
    tagged_signals: list = field(default_factory=list)
    signals: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    actions: list = field(default_factory=list)
    steps: dict = field(default_factory=dict)
    resource_usage: dict = field(default_factory=dict)
