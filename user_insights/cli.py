"""Harness: Click CLI + platform-routing pipeline.

Flow:
1. Brain Planner → domain, platforms, keywords, objectives
2. ── YouTube path ── search → details → transcript → comments → tag → stats
3. ── Reddit path ── decompose → scrape → quality → extract
4. Unified Synthesis → quantitative pulse + narrative + verbatim anchors
"""

import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .agent_ops import AgentOps
from .api_client import APIClient
from .brain_planner import route_query
from .config import (
    get_api_key,
    get_model,
    get_output_base,
    get_reddit_credentials,
    get_youtube_api_key,
    load_config,
    save_config,
)
from .quality_engine import (
    assess_quality,
    assess_youtube_quality,
    classify_youtube_tier,
    get_youtube_tier_weight,
)
from .reddit_scraper import RedditScraper
from .scraper.youtube import QuotaExceededError, YouTubeScraper
from .session_persist import save_report, save_scraped, save_signals, save_youtube_data
from .signal_extractor import extract_signals
from .stats_aggregator import compute_pulse
from .synthesizer import synthesize, synthesize_unified
from .task_decomposer import decompose_question, detect_language
from .youtube_extractor import tag_youtube_content

console = Console()


@click.group()
def main():
    """User Insights — YouTube + Reddit user intelligence workflow."""


@main.command()
@click.option("-q", "--question", default=None, help="Research question (non-interactive mode)")
@click.option("--youtube-only", is_flag=True, help="YouTube only, skip Reddit")
@click.option("--reddit-only", is_flag=True, help="Reddit only, skip YouTube")
def run(question: str | None, youtube_only: bool = False, reddit_only: bool = False):
    """Run the market sensing workflow end-to-end."""
    # ── Setup ──────────────────────────────────────────────────────────
    try:
        api_key = get_api_key()
    except Exception as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    client = APIClient(api_key, model=get_model())
    ops = AgentOps(get_output_base())

    # Get question
    if not question:
        console.print(Panel.fit(
            "[bold]User Insights[/bold] — YouTube + Reddit user intelligence",
            border_style="blue",
        ))
        question = click.prompt("\nWhat would you like to research?", type=str).strip()
        if not question:
            console.print("[red]Question required.[/red]")
            sys.exit(1)

    language = detect_language(question)
    ops.create_session(question, language)

    # ── Step 0: Brain Planner (Autonomous Routing) ─────────────────────
    _print_step(0, "Brain Planner — analyzing query and routing...")
    ops.start_step("brain_planner")

    try:
        plan, baseline_keywords = route_query(question, client)
        if not plan.search_keywords:
            plan.search_keywords = (
                plan.search_queries[:] if plan.search_queries else baseline_keywords
            )
        ops.track_llm_call()
    except Exception as e:
        ops.fail_step("brain_planner", str(e))
        console.print(f"[red]Brain Planner failed: {e}[/red]")
        sys.exit(1)

    ops.finish_step("brain_planner", {"domain": plan.domain, "platforms": plan.platforms})
    ops.session.brain_plan = {
        "domain": plan.domain,
        "platforms": plan.platforms,
        "auto_objective": plan.auto_objective,
        "noise_checklist": plan.noise_checklist,
        "search_keywords": plan.search_keywords,
        "target_channels": plan.target_channels,
        "target_subreddits": plan.target_subreddits,
    }
    ops.checkpoint()

    console.print(f"  Domain: [bold]{plan.domain}[/bold]")
    console.print(f"  Platforms: {plan.platforms}")
    console.print(f"  Objective: {plan.auto_objective}")
    console.print(f"  Noise filters: {plan.noise_checklist}")
    console.print(f"  Keywords: {plan.search_keywords}\n")

    # Determine which platforms to run
    run_youtube = "youtube" in plan.platforms and not reddit_only
    run_reddit = "reddit" in plan.platforms and not youtube_only
    if youtube_only:
        run_youtube = True
        run_reddit = False
    if reddit_only:
        run_reddit = True
        run_youtube = False

    reddit_signals = []
    tagged_signals = []
    stats = {}

    # ── YouTube Path ───────────────────────────────────────────────────
    if run_youtube:
        try:
            yt_api_key = get_youtube_api_key()
        except Exception:
            console.print("[yellow]YouTube API key not set (YOUTUBE_API_KEY env). Skipping YouTube.[/yellow]")
            run_youtube = False

    if run_youtube:
        tagged_signals = _run_youtube_path(ops, plan, question, language, client, yt_api_key)
        stats = ops.session.stats

    # ── Reddit Path ────────────────────────────────────────────────────
    if run_reddit:
        reddit_signals = _run_reddit_path(ops, plan, question, language, client)

    # Merge Reddit counts into the pulse stats (YouTube-only by default)
    total = len(tagged_signals) + len(reddit_signals)
    stats["total_signals"] = total
    stats["total_records"] = len(ops.session.scraped_items) + len(ops.session.youtube_videos)
    stats["reddit_records"] = len(ops.session.scraped_items)
    pvs = stats.setdefault("platform_voice_share", {})
    pvs["Reddit"] = {
        "count": len(reddit_signals),
        "pct": round(len(reddit_signals) / max(total, 1) * 100, 1),
    }
    pvs["YouTube"] = {
        "count": len(tagged_signals),
        "pct": round(len(tagged_signals) / max(total, 1) * 100, 1),
    }

    # ── Unified Synthesis ──────────────────────────────────────────────
    _print_step(4, "Generating user intelligence report...")
    ops.start_step("synthesize")

    try:
        if tagged_signals or reddit_signals:
            report, actions = synthesize_unified(
                reddit_signals=reddit_signals,
                tagged_signals=tagged_signals,
                stats=stats,
                question=question,
                language=language,
                client=client,
            )
        else:
            report = "## No signals extracted.\n\nNo relevant user intelligence was found across YouTube or Reddit for this query."
            actions = []
        ops.track_llm_call()
    except Exception as e:
        ops.fail_step("synthesize", str(e))
        console.print(f"[red]Synthesis failed: {e}[/red]")
        sys.exit(1)

    ops.session.actions = [vars(a) for a in actions]
    ops.finish_step("synthesize", {"action_count": len(actions)})
    ops.checkpoint()
    save_report(ops.session, report, actions)

    # ── Output ─────────────────────────────────────────────────────────
    console.print(Panel(report[:3000], title="Market Intelligence Report", border_style="green"))
    if len(report) > 3000:
        console.print(f"[dim]...report truncated ({len(report)} chars total). See full report at {ops.session.folder_path}/final_report.md[/dim]")
    console.print(f"\n[dim]Session saved: {ops.session.folder_path}[/dim]")
    console.print(f"[dim]{ops.summary()}[/dim]")


# ── YouTube Path ────────────────────────────────────────────────────────

def _run_youtube_path(ops: AgentOps, plan, question: str, language: str, client: APIClient, api_key: str):
    """Execute the full YouTube scraping and tagging pipeline."""
    import os as _os
    proxy = _os.environ.get("HTTPS_PROXY") or _os.environ.get("https_proxy") or _os.environ.get("HTTP_PROXY") or _os.environ.get("http_proxy")
    scraper = YouTubeScraper(api_key, proxy=proxy)

    # Search
    _print_step(1, "YouTube — searching videos...")
    ops.start_step("youtube_search")
    try:
        video_ids: list[str] = []
        for kw in (plan.search_keywords or [""])[:4]:
            video_ids.extend(scraper.search_videos([kw], max_results=5))
        video_ids = list(dict.fromkeys(video_ids))
        ops.finish_step("youtube_search", {"video_ids": len(video_ids)})
        console.print(f"  Found {len(video_ids)} videos")
    except QuotaExceededError as e:
        ops.fail_step("youtube_search", str(e))
        console.print(f"[yellow]YouTube quota exceeded: {e}. Saving partial results.[/yellow]")
        return []
    except Exception as e:
        ops.fail_step("youtube_search", str(e))
        console.print(f"[red]YouTube search failed: {e}[/red]")
        return []

    if not video_ids:
        console.print("  [yellow]No videos found.[/yellow]")
        return []

    # Video details
    _print_step(1, "YouTube — fetching video details...")
    ops.start_step("youtube_details")
    try:
        details = scraper.get_video_details(video_ids)
        ops.finish_step("youtube_details", {"fetched": len(details)})
        console.print(f"  Fetched details for {len(details)} videos")
    except QuotaExceededError as e:
        ops.fail_step("youtube_details", str(e))
        console.print(f"[yellow]Quota exceeded: {e}[/yellow]")
        return []
    except Exception as e:
        ops.fail_step("youtube_details", str(e))
        console.print(f"[red]Video details failed: {e}[/red]")
        return []

    # Build YouTubeVideo objects with transcripts and comments
    _print_step(2, "YouTube — extracting transcripts + comments...")
    ops.start_step("youtube_extract")
    videos = []
    for d in details:
        vid = d["id"]
        title = d.get("snippet", {}).get("title", "")
        description = d.get("snippet", {}).get("description", "")
        channel = d.get("snippet", {}).get("channelTitle", "")
        stats_data = d.get("statistics", {})

        from .models import YouTubeVideo

        # Transcript (free, 0 quota)
        transcript = scraper.get_transcript(vid)

        # Comments (1 unit per video)
        comments = scraper.get_comments(vid, max_results=20)

        tier = classify_youtube_tier(channel)
        tier_w = get_youtube_tier_weight(tier)

        video = YouTubeVideo(
            video_id=vid,
            title=title,
            description=description,
            channel_title=channel,
            transcript=transcript,
            comments=comments,
            view_count=int(stats_data.get("viewCount", 0)),
            like_count=int(stats_data.get("likeCount", 0)),
            comment_count=int(stats_data.get("commentCount", 0)),
            url=f"https://www.youtube.com/watch?v={vid}",
            tier=tier,
        )
        videos.append(video)
        console.print(f"  [{tier}] {channel}: {title[:60]}... (transcript: {len(transcript)} chars, comments: {len(comments)})")

    ops.finish_step("youtube_extract", {"videos": len(videos), "quota_used": scraper.quota_used})
    ops.checkpoint()

    # Quality assessment
    assessed = assess_youtube_quality(videos)
    ops.session.youtube_videos = [vars(v) for v in assessed]
    save_youtube_data(ops.session, assessed)
    console.print(f"  Quality: {len(assessed)} videos passed filter")

    # Structured tagging
    _print_step(3, "YouTube — tagging content with LLM...")
    ops.start_step("youtube_tag")
    try:
        tagged = tag_youtube_content(
            assessed,
            plan.auto_objective,
            plan.noise_checklist,
            client,
            max_items=10,
        )
        for _ in range(min(len(assessed), 10)):
            ops.track_llm_call()
    except Exception as e:
        ops.fail_step("youtube_tag", str(e))
        console.print(f"[red]Tagging failed: {e}[/red]")
        tagged = []

    ops.finish_step("youtube_tag", {"tagged_signals": len(tagged)})
    ops.session.tagged_signals = [vars(t) for t in tagged]
    console.print(f"  Extracted {len(tagged)} tagged signals")

    # Stats aggregation (pure Python, no LLM)
    stats = compute_pulse(tagged)
    ops.session.stats = stats
    ops.checkpoint()
    console.print(f"  Stats: {stats.get('total', 0)} items, sentiment={stats.get('sentiment_pct', {})}")
    return tagged


# ── Reddit Path ─────────────────────────────────────────────────────────

def _run_reddit_path(ops: AgentOps, plan, question: str, language: str, client: APIClient):
    """Execute the full Reddit scraping and signal extraction pipeline."""
    creds = get_reddit_credentials()
    reddit = RedditScraper(**creds)

    # Decompose
    _print_step(1, "Reddit — decomposing question...")
    ops.start_step("decompose")
    try:
        queries = decompose_question(question, client)
        ops.track_llm_call()
    except Exception as e:
        ops.fail_step("decompose", str(e))
        console.print(f"[red]Decomposition failed: {e}[/red]")
        return []

    ops.finish_step("decompose", {"query_count": len(queries)})
    ops.session.queries = [vars(q) for q in queries]
    ops.checkpoint()

    # Inject Brain Planner's target subreddits into queries
    if plan.target_subreddits and queries:
        for q in queries:
            if not q.subreddits or q.subreddits == ["all"]:
                q.subreddits = plan.target_subreddits[:3]

    _display_queries(queries)

    # Scrape
    _print_step(2, "Reddit — scraping posts...")
    ops.start_step("scrape")
    try:
        raw_items = reddit.execute_queries(queries)
        ops.track_reddit_call()
    except Exception as e:
        ops.fail_step("scrape", str(e))
        console.print(f"[red]Reddit scraping failed: {e}[/red]")
        return []

    if not raw_items:
        console.print("  [yellow]No Reddit results found.[/yellow]")
        ops.finish_step("scrape", {"fetched": 0, "passed_quality": 0})
        return []

    assessed = assess_quality(raw_items)
    ops.finish_step("scrape", {"fetched": len(raw_items), "passed_quality": len(assessed)})
    ops.session.scraped_items = [vars(a) for a in assessed]
    ops.checkpoint()
    save_scraped(ops.session, raw_items)
    console.print(f"  Fetched: {len(raw_items)} posts | Passed quality: {len(assessed)}")

    # Extract signals
    _print_step(3, "Reddit — extracting signals...")
    ops.start_step("extract")
    try:
        signals = extract_signals(assessed, question, language, client, max_items=15)
    except Exception as e:
        ops.fail_step("extract", str(e))
        console.print(f"[red]Signal extraction failed: {e}[/red]")
        signals = []

    ops.session.signals = [vars(s) for s in signals]
    ops.finish_step("extract", {"signal_count": len(signals)})
    ops.checkpoint()
    save_signals(ops.session, signals)
    _display_signals(signals)
    return signals


# ── Other Commands ──────────────────────────────────────────────────────

@main.command()
@click.argument("path")
def resume(path: str):
    """Resume a session from a checkpoint folder."""
    ops = AgentOps(get_output_base())
    step_idx = ops.resume_from(path)
    if step_idx is None:
        console.print(f"[red]No checkpoint found in {path}[/red]")
        sys.exit(1)
    console.print(f"[dim]Resuming from step index {step_idx}...[/dim]")
    for name, step in ops.session.steps.items():
        icon = "[green]done[/green]" if step.status == "done" else "[yellow]pending[/yellow]"
        console.print(f"  {icon} {name}")


@main.command()
def config():
    """Configure API keys and settings."""
    console.print("[bold]User Insights Configuration[/bold]\n")
    current = load_config()
    provider = click.prompt(
        "LLM provider",
        type=click.Choice(["anthropic", "openai_compatible"]),
        default=current.get("provider", "anthropic"),
    )
    save_config("provider", provider)
    env_var = "ANTHROPIC_API_KEY" if provider == "anthropic" else "DEEPSEEK_API_KEY"
    key = click.prompt(f"API key (leave blank to use {env_var})", default="", show_default=False)
    if key:
        save_config("api_key", key)
    if provider == "openai_compatible":
        base = click.prompt("Base URL", default=current.get("base_url", "https://api.deepseek.com"))
        save_config("base_url", base)
    model = click.prompt("Model", default=current.get("model", "claude-sonnet-4-20250514"))
    save_config("model", model)
    output = click.prompt("Output directory", default=current.get("output_dir", "user-insights-output"))
    save_config("output_dir", output)
    console.print("[green]Configuration saved.[/green]")
    console.print("[dim]YouTube API key must be set via YOUTUBE_API_KEY environment variable.[/dim]")


@main.command(name="list")
def list_sessions_cmd():
    """List past sessions."""
    ops = AgentOps(get_output_base())
    sessions = ops.list_sessions()
    if not sessions:
        console.print("[dim]No sessions found.[/dim]")
        return
    table = Table(title="Past Sessions")
    table.add_column("Timestamp", style="dim")
    table.add_column("Question")
    table.add_column("Steps Done", justify="center")
    for s in sessions[:20]:
        table.add_row(s["timestamp"], s["question"], str(s["steps_done"]))
    console.print(table)


# ── CLI Helpers ───────────────────────────────────────────────────────────

def _print_step(n: int, description: str):
    console.print(f"\n[bold cyan]Step {n}[/bold cyan]: {description}")


def _display_queries(queries):
    console.print(f"  [dim]Generated {len(queries)} search queries:[/dim]")
    for i, q in enumerate(queries):
        subs = ", ".join(f"r/{s}" for s in q.subreddits[:3])
        kws = ", ".join(f'"{k}"' for k in q.keywords[:3])
        console.print(f"  [{i+1}] {subs} | {kws}")


def _display_signals(signals):
    if not signals:
        console.print("  [yellow]No signals extracted.[/yellow]")
        return
    by_type: dict[str, int] = {}
    for s in signals:
        by_type[s.signal_type] = by_type.get(s.signal_type, 0) + 1
    console.print(f"  [dim]Extracted {len(signals)} signals:[/dim]")
    for stype, count in sorted(by_type.items(), key=lambda x: -x[1]):
        console.print(f"    {stype}: {count}")
