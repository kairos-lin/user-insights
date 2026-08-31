"""End-to-end YouTube workflow test."""
import os, sys

from user_insights.api_client import APIClient
from user_insights.config import get_api_key, get_youtube_api_key, get_output_base
from user_insights.brain_planner import route_query
from user_insights.scraper.youtube import YouTubeScraper, QuotaExceededError
from user_insights.quality_engine import assess_youtube_quality, classify_youtube_tier
from user_insights.youtube_extractor import tag_youtube_content
from user_insights.stats_aggregator import compute_pulse, format_pulse_markdown
from user_insights.models import YouTubeVideo
from user_insights.synthesizer import synthesize_unified
from user_insights.agent_ops import AgentOps

question = "What are the core feature complaints and migration reasons for users switching from VS Code Copilot to Cursor?"

print("=" * 60)
print("YOUTUBE END-TO-END TEST")
print(f"Question: {question}")
print("=" * 60)

# Setup
client = APIClient(get_api_key())
scraper = YouTubeScraper(get_youtube_api_key(), proxy="http://127.0.0.1:8118")
ops = AgentOps(get_output_base())
ops.create_session(question, "en")

# Step 0: Brain Planner
print("\n--- Brain Planner ---")
plan, baseline_keywords = route_query(question, client)
if not plan.search_keywords:
    plan.search_keywords = plan.search_queries[:] if plan.search_queries else baseline_keywords
print(f"Domain: {plan.domain}")
print(f"Platforms: {plan.platforms}")
print(f"Objective: {plan.auto_objective}")
print(f"Noise: {plan.noise_checklist}")
print(f"Keywords: {plan.search_keywords}")

# Step 1: YouTube Search
print("\n--- YouTube Search ---")
try:
    video_ids = []
    for kw in (plan.search_keywords or [""])[:4]:
        video_ids.extend(scraper.search_videos([kw], max_results=5))
    video_ids = list(dict.fromkeys(video_ids))
    print(f"Found {len(video_ids)} videos: {video_ids}")
except QuotaExceededError as e:
    print(f"Quota exceeded: {e}")
    sys.exit(1)

# Step 2: Video Details + Transcripts + Comments
print("\n--- Video Details ---")
details = scraper.get_video_details(video_ids)
videos = []
for d in details:
    vid = d["id"]
    title = d.get("snippet", {}).get("title", "")
    desc = d.get("snippet", {}).get("description", "")
    channel = d.get("snippet", {}).get("channelTitle", "")
    s = d.get("statistics", {})

    print(f"\n  Video: {channel} — {title[:80]}")
    print(f"  Views: {s.get('viewCount', 0)} | Likes: {s.get('likeCount', 0)}")

    # Transcript (free)
    transcript = scraper.get_transcript(vid)
    print(f"  Transcript: {len(transcript)} chars")

    # Comments (1 unit)
    comments = scraper.get_comments(vid, max_results=10)
    print(f"  Comments: {len(comments)}")

    tier = classify_youtube_tier(channel)
    video = YouTubeVideo(
        video_id=vid, title=title, description=desc,
        channel_title=channel, transcript=transcript,
        comments=comments,
        view_count=int(s.get("viewCount", 0)),
        like_count=int(s.get("likeCount", 0)),
        comment_count=int(s.get("commentCount", 0)),
        url=f"https://www.youtube.com/watch?v={vid}",
        tier=tier,
    )
    videos.append(video)

print(f"\nQuota used: {scraper.quota_used} units")

# Step 3: Quality + Tagging
print("\n--- Quality Assessment ---")
assessed = assess_youtube_quality(videos)
for v in assessed:
    print(f"  {v.channel_title}: weight={v.weight} score={v.quality_score:.2f}")

print("\n--- LLM Tagging (structured JSON) ---")
tagged = tag_youtube_content(assessed, plan.auto_objective, plan.noise_checklist, client, max_items=5)
print(f"Tagged signals: {len(tagged)}")
for i, ts in enumerate(tagged):
    print(f"  [{i+1}] features={ts.features} user_types={ts.user_types} sentiment={ts.sentiment}")
    print(f"       quote: {ts.verbatim_quote[:100]}...")

# Step 4: Stats (pure Python)
print("\n--- Statistical Aggregation (Python) ---")
stats = compute_pulse(tagged)
print(f"Total items: {stats['total']}")
print(f"Features: {stats['feature_pct']}")
print(f"Sentiment: {stats['sentiment_pct']}")
print(f"User types: {stats['user_type_pct']}")

# Step 5: Synthesis
print("\n--- Synthesis Report ---")
report, actions = synthesize_unified(
    reddit_signals=[], tagged_signals=tagged, stats=stats,
    question=question, language="en", client=client,
)
print(report[:2000])
print(f"\nActions: {len(actions)}")

print(f"\nQuota used: {scraper.quota_used} units")
print("DONE — YouTube workflow completed successfully.")
