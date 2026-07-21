"""Normalize Reddit ScrapedContent and YouTubeVideo into a unified schema.

Every record:
  {source, author_tier, author_name, text, text_type, raw_metadata}
"""

from .models import ScrapedContent, YouTubeVideo


def normalize_reddit(item: ScrapedContent) -> list[dict]:
    """Normalize a Reddit post + its comments into unified records."""
    records = []
    base_meta = {
        "platform": "reddit",
        "subreddit": item.subreddit,
        "post_id": item.post_id,
        "url": item.url,
        "score": item.score,
        "quality_score": item.quality_score,
    }

    # Map weight to author_tier
    tier_map = {"high": 1, "medium": 2, "low": 3}

    # Post body as one record
    if item.body and len(item.body) > 30:
        records.append({
            "source": "Reddit",
            "author_tier": tier_map.get(item.weight, 2),
            "author_name": f"r/{item.subreddit}",
            "text": item.body,
            "text_type": "post_body",
            "raw_metadata": base_meta,
        })

    # Each comment as a separate record
    for i, comment in enumerate(item.comments):
        if comment and len(comment) > 20:
            records.append({
                "source": "Reddit",
                "author_tier": 2,  # commenters default to tier 2
                "author_name": f"r/{item.subreddit} commenter",
                "text": comment,
                "text_type": "comment",
                "raw_metadata": {**base_meta, "comment_index": i},
            })

    return records


def normalize_youtube(video: YouTubeVideo) -> list[dict]:
    """Normalize a YouTube video into unified records.

    Video context (title+description+transcript) is one record.
    Each comment is a separate record.
    """
    records = []
    base_meta = {
        "platform": "youtube",
        "video_id": video.video_id,
        "channel": video.channel_title,
        "url": video.url,
        "views": video.view_count,
        "likes": video.like_count,
        "quality_score": video.quality_score,
    }

    tier_map = {"high": 1, "medium": 2, "low": 3}

    # Video context (transcript + description)
    context_text = video.transcript or video.description or ""
    if context_text and len(context_text) > 30:
        records.append({
            "source": "YouTube",
            "author_tier": tier_map.get(video.weight, 2),
            "author_name": video.channel_title,
            "text": context_text,
            "text_type": "video_context",
            "raw_metadata": {**base_meta, "title": video.title},
        })

    # Title as metadata-rich record
    if video.title:
        records.append({
            "source": "YouTube",
            "author_tier": tier_map.get(video.weight, 2),
            "author_name": video.channel_title,
            "text": f"TITLE: {video.title} — {video.description[:300]}" if video.description else f"TITLE: {video.title}",
            "text_type": "video_title",
            "raw_metadata": base_meta,
        })

    # Each comment
    for i, comment in enumerate(video.comments):
        if comment and len(comment) > 20:
            records.append({
                "source": "YouTube",
                "author_tier": 2,
                "author_name": f"{video.channel_title} commenter",
                "text": comment,
                "text_type": "comment",
                "raw_metadata": {**base_meta, "comment_index": i},
            })

    return records


def merge_datasets(reddit_items: list, youtube_videos: list) -> list[dict]:
    """Merge Reddit and YouTube content into a single normalized dataset."""
    all_records = []

    for item in reddit_items:
        try:
            all_records.extend(normalize_reddit(item))
        except Exception:
            continue

    for video in youtube_videos:
        try:
            all_records.extend(normalize_youtube(video))
        except Exception:
            continue

    return all_records
