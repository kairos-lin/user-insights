"""State-Flushed Regression Matrix — 3 cases with dynamic wiring."""

import os, sys, time, gc
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from user_insights.api_client import APIClient
from user_insights.config import get_api_key, get_youtube_api_key
from user_insights.unified_pipeline import run_unified_pipeline

OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "testcases")

CASES = [
    {
        "name": "case1_pmax_routing",
        "query": "What are the core efficiency bottlenecks and attribution transparency complaints from media buyers regarding Google Ads P-MAX (Performance Max) automated campaigns?",
    },
    {
        "name": "case2_aigc_flush",
        "query": "In creative AIGC workflows—specifically visual generation, automated content templates, and media asset production—which exact steps cause the highest human-AI friction?",
    },
]


def run_case(case, client, yt_key):
    print(f"\n{'='*60}")
    print(f"CASE: {case['name']}")
    print(f"{'='*60}")
    print(f"QUERY: {case['query'][:100]}...\n")

    # ABSOLUTE STATE FLUSH — clear all memory between runs
    gc.collect()

    t_start = time.time()
    try:
        output = run_unified_pipeline(question=case["query"], client=client, yt_api_key=yt_key)
    except Exception as e:
        import traceback
        print(f"FAILED: {e}")
        traceback.print_exc()
        return {"name": case["name"], "passed": False, "elapsed": time.time() - t_start}
    elapsed = time.time() - t_start

    stats = output["stats"]
    manifest = stats.get("manifest", {})
    sover = stats.get("sovereignty", {})

    print(f"\n  Elapsed: {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print(f"  Records: {stats.get('total_records', 0)} | Signals: {stats.get('total_signals', 0)}")
    print(f"  Subreddits: {manifest.get('target_subreddits', [])}")
    print(f"  Anchors: {manifest.get('positive_anchors', [])}")
    print(f"  Exclusion: {manifest.get('exclusion_wall', [])}")
    print(f"  Low-N: {manifest.get('is_low_n', False)}")
    xp = stats.get("cross_platform_ratio", {})
    print(f"  Platform: Reddit={xp.get('reddit_records', 0)}, YouTube={xp.get('youtube_records', 0)}")

    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    v = time.strftime("%Y%m%d_%H%M%S")
    low_tag = "_LOW_N" if manifest.get("is_low_n") else ""
    rp = os.path.join(OUTPUTS_DIR, f"{case['name']}_wired_{v}{low_tag}_report.md")
    with open(rp, "w") as f:
        f.write(output["report"])
    print(f"  Report: {rp}")

    # Show Manifest section from report
    manifest_start = output["report"].find("## EXECUTION MANIFEST")
    if manifest_start >= 0:
        end = output["report"].find("\n## ", manifest_start + 10)
        print(f"\n  [MANIFEST]\n{output['report'][manifest_start:end]}")

    # Pulse
    pulse_start = output["report"].find("## 1. Quantitative")
    if pulse_start >= 0:
        end = output["report"].find("\n## ", pulse_start + 10)
        print(f"  [PULSE]\n{output['report'][pulse_start:end][:500]}")

    return {"name": case["name"], "passed": True, "elapsed": elapsed, "report_path": rp}


def main():
    print("P-MAX & AIGC Regression Matrix — 2 Cases")
    print("=" * 60)
    client = APIClient(get_api_key())
    print(f"LLM: {client.model}")
    yt_key = get_youtube_api_key()
    print(f"YouTube: OK\n")

    total_start = time.time()
    results = [run_case(c, client, yt_key) for c in CASES]
    total_elapsed = time.time() - total_start

    print(f"\n{'='*60}\nSUMMARY ({total_elapsed/60:.0f}m total)\n{'='*60}")
    for r in results:
        s = "PASS" if r["passed"] else "FAIL"
        print(f"  [{s}] {r['name']} — {r.get('elapsed', 0):.0f}s — {r.get('report_path', 'N/A')}")
    print(f"Reports: {OUTPUTS_DIR}/")


if __name__ == "__main__":
    main()
