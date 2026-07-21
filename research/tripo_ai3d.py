"""Multi-case market research runner."""
import os, time, gc

from user_insights.api_client import APIClient
from user_insights.config import get_api_key, get_youtube_api_key
from user_insights.unified_pipeline import run_unified_pipeline

OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")

CASES = [
    {
        "name": "tripo_v4",
        "query": (
            "How do users of AI 3D model generation products like Tripo(AI 3D model generation product)? "
            "analyse from all angles including but not limited features comments, price, subscription, "
            "willingness to pay, use case, pain-points, requirements, and possibility to integrating in production."
        ),
    },
    {
        "name": "ai_assistants_v4",
        "query": (
            "how do users like the AI/agentic assistants? "
            "What's solved and unsolved? "
            "Are they worthy or pricy? "
            "Why and why not you pay for them? "
            "What are the top 3 AI assistants that people are using? "
            "What's the most 3 emerging and recommendable AI assistants other than the top 3?"
        ),
    },
]


def run_case(case, client, yt_key):
    print(f"\n{'='*60}")
    print(f"CASE: {case['name']}")
    print(f"QUERY: {case['query'][:120]}...")
    print(f"{'='*60}")

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

    print(f"\n  Elapsed: {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print(f"  Records: {stats.get('total_records', 0)} | Signals: {stats.get('total_signals', 0)}")
    xp = stats.get("cross_platform_ratio", {})
    print(f"  Platform: Reddit={xp.get('reddit_records', 0)}, YouTube={xp.get('youtube_records', 0)}")
    print(f"  Low-N: {manifest.get('is_low_n', False)}")

    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    v = time.strftime("%Y%m%d_%H%M%S")
    low_tag = "_LOW_N" if manifest.get("is_low_n") else ""
    rp = os.path.join(OUTPUTS_DIR, f"{case['name']}_{v}{low_tag}_report.md")
    with open(rp, "w") as f:
        f.write(output["report"])
    print(f"  Report: {rp}")

    print("\n" + "=" * 60)
    print(output["report"])

    return {"name": case["name"], "passed": True, "elapsed": elapsed, "report_path": rp}


def main():
    print("User Insights v3 — 2 Cases")
    print("=" * 60)
    client = APIClient(get_api_key())
    print(f"LLM: {client.model} | Provider: {client.provider}")
    yt_key = get_youtube_api_key()
    print(f"YouTube: OK\n")

    total_start = time.time()
    results = [run_case(c, client, yt_key) for c in CASES]
    total_elapsed = time.time() - total_start

    print(f"\n{'='*60}\nSUMMARY ({total_elapsed/60:.0f}m)\n{'='*60}")
    for r in results:
        s = "PASS" if r["passed"] else "FAIL"
        print(f"  [{s}] {r['name']} — {r.get('elapsed', 0):.0f}s — {r.get('report_path', 'N/A')}")
    print(f"Reports: {OUTPUTS_DIR}/")


if __name__ == "__main__":
    main()
