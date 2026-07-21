"""Session data persistence — saves intermediate results to disk.

Separate from agent_ops.py (which manages session lifecycle and checkpoints).
This module handles data file I/O for scraped content, signals, and reports.
"""

import json
import os

from .models import BusinessAction, ScrapedContent, Session, Signal


def save_scraped(session: Session, items: list[ScrapedContent]) -> None:
    """Save scraped content to files under scraped_data/{subreddit}/."""
    folder = os.path.join(session.folder_path, "scraped_data")
    os.makedirs(folder, exist_ok=True)

    for item in items:
        sub_folder = os.path.join(folder, f"r_{item.subreddit}")
        os.makedirs(sub_folder, exist_ok=True)
        path = os.path.join(sub_folder, f"{item.post_id}.json")
        with open(path, "w") as f:
            json.dump({
                "post_id": item.post_id,
                "subreddit": item.subreddit,
                "title": item.title,
                "body": item.body,
                "url": item.url,
                "score": item.score,
                "num_comments": item.num_comments,
                "created_utc": item.created_utc,
                "comments": item.comments,
                "quality_score": item.quality_score,
                "weight": item.weight,
                "passed_filter": item.passed_filter,
            }, f, indent=2, ensure_ascii=False)


def load_scraped(folder: str) -> list[dict]:
    """Load scraped content from a session folder."""
    scraped_dir = os.path.join(folder, "scraped_data")
    if not os.path.exists(scraped_dir):
        return []
    items = []
    for sub in os.listdir(scraped_dir):
        sub_path = os.path.join(scraped_dir, sub)
        if not os.path.isdir(sub_path):
            continue
        for fname in os.listdir(sub_path):
            if fname.endswith(".json"):
                with open(os.path.join(sub_path, fname)) as f:
                    items.append(json.load(f))
    return items


def save_signals(session: Session, signals: list[Signal]) -> None:
    """Save extracted signals as JSON and human-readable markdown."""
    # JSON
    path = os.path.join(session.folder_path, "signals.json")
    with open(path, "w") as f:
        json.dump([vars(s) for s in signals], f, indent=2, ensure_ascii=False)

    # Markdown
    md_path = os.path.join(session.folder_path, "signals.md")
    lines = [f"# Extracted Signals — {session.question}\n", f"Total: {len(signals)}\n"]
    for i, s in enumerate(signals):
        lines.append(f"## Signal {i+1}: {s.signal_type} ({s.strength})")
        lines.append(f"- **Source**: r/{s.source_subreddit} | [{s.source_url}]({s.source_url})")
        lines.append(f"- **Quote**: > {s.verbatim_quote}")
        lines.append(f"- **Interpretation**: {s.interpretation}")
        lines.append("")
    with open(md_path, "w") as f:
        f.write("\n".join(lines))


def load_signals(folder: str) -> list[dict]:
    """Load signals from a session folder."""
    path = os.path.join(folder, "signals.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def save_report(session: Session, report: str, actions: list[BusinessAction]) -> None:
    """Save final report and actions to markdown."""
    path = os.path.join(session.folder_path, "final_report.md")
    with open(path, "w") as f:
        f.write(report)
        if actions:
            f.write("\n\n## Business Actions (Structured)\n\n")
            for a in actions:
                f.write(f"- **{a.action}** [priority {a.priority}]\n")
                f.write(f"  - Rationale: {a.rationale}\n")
                f.write(f"  - Timeline: {a.timeline}\n")
                f.write(f"  - Risk: {a.risk}\n")
                f.write(f"  - Expected: {a.expected_outcome}\n\n")


def save_youtube_data(session: Session, videos: list) -> None:
    """Save YouTube video data to JSON."""
    folder = os.path.join(session.folder_path, "youtube_data")
    os.makedirs(folder, exist_ok=True)
    for v in videos:
        if hasattr(v, "video_id"):
            vid = v.video_id
            data = {
                "video_id": vid,
                "title": v.title,
                "description": v.description[:500],
                "channel_title": v.channel_title,
                "transcript": v.transcript[:2000] if v.transcript else "",
                "comments": v.comments[:10],
                "view_count": v.view_count,
                "like_count": v.like_count,
                "comment_count": v.comment_count,
                "url": v.url,
                "tier": v.tier,
                "quality_score": v.quality_score,
                "weight": v.weight,
            }
            with open(os.path.join(folder, f"{vid}.json"), "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
