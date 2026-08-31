"""Regression tests for pipeline bugs fixed 2026-08-28. No network access.

1. cli.py `list` command shadowing the builtin (ghost CLI invocations)
2. route_query tuple unpack in cli.run + search_queries fallback
3. YouTube per-query search with dedupe
4. Reddit subreddit "r/" prefix normalization
"""

from user_insights import cli
from user_insights.models import BrainPlan, SearchQuery, YouTubeVideo
from user_insights.reddit_scraper import RedditScraper


class FakeSession:
    folder_path = "/tmp/ui_fake_session"
    steps = {}
    tagged_signals = []
    signals = []
    stats = {}
    actions = []
    scraped_items = []
    youtube_videos = []

    def __init__(self):
        self.brain_plan = None


class FakeOps:
    def __init__(self):
        self.session = FakeSession()

    def create_session(self, question, language):
        return self.session

    def start_step(self, name, metadata=None):
        pass

    def finish_step(self, name, metadata=None):
        pass

    def fail_step(self, name, error):
        pass

    def checkpoint(self):
        pass

    def track_llm_call(self, tokens_used=0):
        pass

    def track_reddit_call(self):
        pass

    def summary(self):
        return "fake"


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass


def _brain_plan(platforms=None, search_keywords=None, search_queries=None):
    return BrainPlan(
        domain="Tech_Deep_Dive",
        platforms=platforms or [],
        auto_objective="test",
        noise_checklist=[],
        search_keywords=search_keywords or [],
        search_queries=search_queries or [],
    )


# ── 1. builtin `list` must not be shadowed by a CLI command ──────────────

def test_cli_module_does_not_shadow_builtin_list():
    assert not hasattr(cli, "list")
    assert cli.main.commands["list"].callback.__name__ == "list_sessions_cmd"


# ── 2. cli.run unpacks route_query tuple and applies query fallback ──────

def test_run_unpacks_tuple_and_falls_back_to_search_queries(monkeypatch):
    ops = FakeOps()
    monkeypatch.setattr(cli, "get_api_key", lambda: "test-key")
    monkeypatch.setattr(cli, "APIClient", FakeClient)
    monkeypatch.setattr(cli, "AgentOps", lambda base: ops)
    monkeypatch.setattr(cli, "save_report", lambda *a, **k: None)
    monkeypatch.setattr(
        cli, "route_query",
        lambda question, client: (_brain_plan(search_queries=["q1", "q2"]), ["baseline"]),
    )

    cli.run.callback("test question", False, False)

    assert ops.session.brain_plan["search_keywords"] == ["q1", "q2"]


# ── 3. YouTube path searches each keyword separately and dedupes ─────────

class FakeYouTubeScraper:
    quota_used = 0

    def __init__(self, api_key, proxy=None):
        self.search_calls = []
        self.details_received = None

    def search_videos(self, keywords, max_results=5):
        self.search_calls.append(list(keywords))
        n = len(self.search_calls)
        if n == 1:
            return ["a", "b"]
        if n == 2:
            return ["b", "c"]
        return []

    def get_video_details(self, video_ids):
        self.details_received = list(video_ids)
        return []


def test_youtube_path_searches_each_keyword_and_dedupes(monkeypatch):
    fake = FakeYouTubeScraper("k")
    ops = FakeOps()
    monkeypatch.setattr(cli, "YouTubeScraper", lambda api_key, proxy=None: fake)
    monkeypatch.setattr(cli, "assess_youtube_quality", lambda videos: videos)
    monkeypatch.setattr(cli, "save_youtube_data", lambda *a, **k: None)
    monkeypatch.setattr(cli, "tag_youtube_content", lambda *a, **k: [])
    monkeypatch.setattr(cli, "compute_pulse", lambda tagged: {})

    plan = _brain_plan(search_keywords=["q1", "q2", "q3", "q4"])
    cli._run_youtube_path(ops, plan, "q", "en", FakeClient(), "k")

    assert fake.search_calls == [["q1"], ["q2"], ["q3"], ["q4"]]
    assert fake.details_received == ["a", "b", "c"]


# ── 4. Reddit search strips r/ prefix at the scraper boundary ────────────

class FakeRedditClient:
    def __init__(self):
        self.called_name = None

    def subreddit(self, name):
        self.called_name = name
        return self

    def search(self, *args, **kwargs):
        return []


def test_reddit_search_strips_r_prefix(monkeypatch):
    monkeypatch.setattr("user_insights.reddit_scraper.praw.Reddit", lambda **kw: None)
    scraper = RedditScraper("id", "secret", "user-agent")
    fake = FakeRedditClient()
    scraper.reddit = fake
    q = SearchQuery(subreddits=[], keywords=[], rationale="t")

    scraper._search("r/aivideo", "kw", q)
    assert fake.called_name == "aivideo"

    scraper._search("  r/StableDiffusion  ", "kw", q)
    assert fake.called_name == "StableDiffusion"

    scraper._search("plainname", "kw", q)
    assert fake.called_name == "plainname"


# ── 5. YouTube tag prompt schema must match the parser ─────────────────

def test_youtube_tag_prompt_matches_parser_schema():
    from user_insights.prompts import YOUTUBE_TAG_CLI_SYSTEM
    from user_insights.youtube_extractor import _parse_tagged_signal

    for field in ("features", "user_types", "sentiment", "use_case", "verbatim_quote"):
        assert field in YOUTUBE_TAG_CLI_SYSTEM, f"CLI tag prompt missing field: {field}"

    video = YouTubeVideo(
        video_id="v",
        title="t",
        description="",
        channel_title="c",
        transcript="",
        url="https://youtube.com/watch?v=v",
    )
    raw = (
        '{"features": ["motion quality"], "user_types": ["creator"], '
        '"sentiment": "negative", "use_case": "testing", '
        '"verbatim_quote": "it lags", "timestamp": "1:00"}'
    )
    sig = _parse_tagged_signal(raw, video)
    assert sig is not None
    assert sig.features == ["motion quality"]


# ── 6. Executive Answer payload must include Reddit signals ──────────────

def test_executive_payload_includes_reddit_signals():
    from user_insights.models import Signal
    from user_insights.synthesizer import _build_executive_payload

    reddit = [
        Signal(
            signal_type="pricing_sentiment",
            strength="strong",
            verbatim_quote="credits run out too fast for the price",
            interpretation="users feel credit pricing is unfair",
            source_url="https://reddit.com/r/x/1",
            source_subreddit="aivideo",
        )
    ]
    payload = _build_executive_payload(reddit, [], {}, None, "test question")
    assert "Top Reddit Signals (1 total)" in payload
    assert "credits run out too fast for the price" in payload


# ── 7. API client retries transient connection errors ───────────────────

def test_api_client_retries_connection_errors(monkeypatch):
    from types import SimpleNamespace

    from user_insights.api_client import APIClient

    monkeypatch.setattr("user_insights.api_client.time.sleep", lambda s: None)
    client = APIClient("test-key")

    calls = {"n": 0}

    class FakeCompletions:
        def create(self, **kwargs):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("Connection error: server unreachable")
            msg = SimpleNamespace(content="ok", reasoning_content=None)
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    class FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    client.client = FakeClient()
    assert client.generate(system_prompt="s", user_message="u") == "ok"
    assert calls["n"] == 3
