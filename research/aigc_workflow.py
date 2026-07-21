"""Single-case runner: AIGC Workflow Friction Correction Test."""
import os, time, gc

from user_insights.api_client import APIClient
from user_insights.config import get_api_key, get_youtube_api_key
from user_insights.unified_pipeline import run_unified_pipeline

OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", "regression")

case = {
    "name": "case2_aigc_flush",
    "query": "In creative AIGC workflows—specifically visual generation, automated content templates, and media asset production—which exact steps cause the highest human-AI friction?",
}

print(f"CASE: {case['name']}")
print(f"QUERY: {case['query']}")
print()

gc.collect()

client = APIClient(get_api_key())
print(f"LLM: {client.model}")
yt_key = get_youtube_api_key()
print(f"YouTube: OK\n")

t_start = time.time()
try:
    output = run_unified_pipeline(question=case["query"], client=client, yt_api_key=yt_key)
except Exception as e:
    import traceback
    print(f"FAILED: {e}")
    traceback.print_exc()
    sys.exit(1)
elapsed = time.time() - t_start

stats = output["stats"]
manifest = stats.get("manifest", {})
sover = stats.get("sovereignty", {})

print(f"\n  Elapsed: {elapsed:.0f}s ({elapsed/60:.1f}m)")
print(f"  Records: {stats.get('total_records', 0)} | Signals: {stats.get('total_signals', 0)}")
print(f"  Subreddits: {manifest.get('target_subreddits', [])}")
print(f"  Anchors: {manifest.get('positive_anchors', [])}")
print(f"  Exclusion: {manifest.get('exclusion_wall', [])}")
print(f"  AIGC dropped: {stats.get('dropped_aigc_noise', 0)}")

os.makedirs(OUTPUTS_DIR, exist_ok=True)
v = time.strftime("%Y%m%d_%H%M%S")
rp = os.path.join(OUTPUTS_DIR, f"{case['name']}_wired_{v}_report.md")
with open(rp, "w") as f:
    f.write(output["report"])
print(f"  Report: {rp}")
