"""Step-by-step test of the market sensing workflow."""
import os
import sys

from user_insights.api_client import APIClient
from user_insights.config import get_api_key, get_output_base, get_reddit_credentials
from user_insights.task_decomposer import decompose_question, detect_language
from user_insights.reddit_scraper import RedditScraper
from user_insights.quality_engine import assess_quality
from user_insights.signal_extractor import extract_signals
from user_insights.synthesizer import synthesize
from user_insights.agent_ops import AgentOps
from user_insights.session_persist import save_scraped, save_signals, save_report

question = "How can AI solve real problems in language learning?"

print("=" * 60)
print("STEP 0: Setup")
try:
    api_key = get_api_key()
    print(f"  API key: {api_key[:15]}...")
    client = APIClient(api_key)
    print("  LLM client: OK")
    creds = get_reddit_credentials()
    reddit = RedditScraper(**creds)
    print("  Reddit scraper: OK")
    ops = AgentOps(get_output_base())
    print("  AgentOps: OK")
except Exception as e:
    print(f"  FAILED: {e}")
    sys.exit(1)

language = detect_language(question)
print(f"  Language: {language}")

print("=" * 60)
print("STEP 1: Task Decomposition")
try:
    ops.create_session(question, language)
    ops.start_step("decompose")
    queries = decompose_question(question, client)
    ops.track_llm_call()
    ops.finish_step("decompose", {"query_count": len(queries)})
    print(f"  Generated {len(queries)} queries:")
    for i, q in enumerate(queries):
        subs = ", ".join(f"r/{s}" for s in q.subreddits[:3])
        kws = ", ".join(f'"{k}"' for k in q.keywords[:3])
        print(f"  [{i+1}] {subs} | {kws} | {q.rationale[:60]}")
except Exception as e:
    print(f"  FAILED: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

print("=" * 60)
print("STEP 2: Scrape Reddit")
try:
    ops.start_step("scrape")
    raw_items = reddit.execute_queries(queries)
    print(f"  Fetched {len(raw_items)} raw posts")
    assessed = assess_quality(raw_items)
    ops.finish_step("scrape", {"fetched": len(raw_items), "passed": len(assessed)})
    print(f"  Passed quality: {len(assessed)}")
    for i, item in enumerate(assessed[:5]):
        print(f"  [{i+1}] r/{item.subreddit} score={item.score} weight={item.weight} | {item.title[:60]}")
    save_scraped(ops.session, raw_items)
    ops.session.scraped_items = [vars(a) for a in assessed]
    ops.checkpoint()
except Exception as e:
    print(f"  FAILED: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

if not assessed:
    print("  No content passed quality filter — stopping.")
    sys.exit(0)

print("=" * 60)
print(f"STEP 3: Extract Signals from {len(assessed)} items")
try:
    ops.start_step("extract")
    signals = extract_signals(assessed, question, language, client, max_items=5)
    for _ in range(len(assessed)):
        ops.track_llm_call()
    ops.finish_step("extract", {"signal_count": len(signals)})
    print(f"  Extracted {len(signals)} signals:")
    by_type = {}
    for s in signals:
        by_type[s.signal_type] = by_type.get(s.signal_type, 0) + 1
    for st, cnt in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"    {st}: {cnt}")
    save_signals(ops.session, signals)
    ops.session.signals = [vars(s) for s in signals]
    ops.checkpoint()
except Exception as e:
    print(f"  FAILED: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

print("=" * 60)
print("STEP 4: Synthesize Report")
try:
    ops.start_step("synthesize")
    report, actions = synthesize(signals, question, language, client)
    ops.track_llm_call()
    ops.finish_step("synthesize", {"action_count": len(actions)})
    ops.session.actions = [vars(a) for a in actions]
    ops.checkpoint()
    save_report(ops.session, report, actions)
    print(report[:2000])
    print(f"\n  Actions: {len(actions)}")
    print(f"\n  Session: {ops.session.folder_path}")
    print(f"\n  {ops.summary()}")
except Exception as e:
    print(f"  FAILED: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

print("=" * 60)
print("DONE — workflow completed successfully.")
