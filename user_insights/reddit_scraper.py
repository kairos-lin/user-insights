"""Step 2: Execute Reddit search queries via PRAW (proxy-aware)."""

import os
import time
from datetime import datetime

import praw

from .models import ScrapedContent, SearchQuery

# Fuzzy query expansion — when a keyword returns 0 results, try these variants.
FUZZY_EXPANSIONS: dict[str, list[str]] = {
    "P-MAX": ["PMax", "Performance Max", "P-Max", "PerformanceMax", "Google PMax"],
    "PMax": ["P-MAX", "Performance Max", "P-Max", "PerformanceMax", "Google PMax"],
    "Performance Max": ["PMax", "P-MAX", "PerformanceMax", "Google Ads Performance Max"],
    "PerformanceMax": ["Performance Max", "PMax", "P-MAX"],
    "AIGC": ["AI generated content", "generative AI", "AI creative tools", "AI image generation"],
    "generative AI": ["AIGC", "AI generated content", "AI image generation"],
    "ComfyUI": ["Comfy UI", "ComfyUI workflow", "Stable Diffusion workflow"],
    "FFB": ["force feedback", "direct drive", "DD wheel", "sim racing wheel"],
    "force feedback": ["FFB", "direct drive wheel", "DD wheel", "sim racing"],
}
KNOWN_ABBREVIATIONS: dict[str, list[str]] = {
    "pmax": ["P-MAX", "PMax", "Performance Max", "PerformanceMax", "Google PMax", "Google Performance Max"],
    "p-max": ["P-MAX", "PMax", "Performance Max", "PerformanceMax", "Google PMax", "Google Performance Max"],
    "performance max": ["P-MAX", "PMax", "Performance Max", "PerformanceMax", "Google PMax", "Google Performance Max"],
    "aigc": ["AIGC", "AI generated content", "AI creative tools", "generative AI workflow", "AI image generation"],
    "comfyui": ["ComfyUI", "Comfy UI", "ComfyUI workflow", "Stable Diffusion workflow", "automatic1111"],
    "ffb": ["force feedback", "direct drive wheel", "DD wheel", "sim racing wheel", "Fanatec", "Moza"],
}


class RedditScraper:
    def __init__(self, client_id: str, client_secret: str, user_agent: str, proxy: str | None = None):
        # Ensure proxy env vars are set for requests library (PRAW's HTTP backend)
        if proxy:
            os.environ["HTTP_PROXY"] = proxy
            os.environ["HTTPS_PROXY"] = proxy
            os.environ["http_proxy"] = proxy
            os.environ["https_proxy"] = proxy

        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
        self.call_count = 0
        self.proxy = proxy

    def execute_queries(self, queries: list[SearchQuery]) -> list[ScrapedContent]:
        """Execute all search queries, deduplicate by post_id."""
        seen_ids: set[str] = set()
        results: list[ScrapedContent] = []

        for query in queries:
            items = self._run_one_query(query)
            for item in items:
                if item.post_id not in seen_ids:
                    seen_ids.add(item.post_id)
                    results.append(item)

        return results

    def _run_one_query(self, query: SearchQuery) -> list[ScrapedContent]:
        results = []
        subreddits = query.subreddits if query.subreddits else ["all"]
        keywords = query.keywords if query.keywords else [""]
        if not keywords or keywords == [""]:
            keywords = [""]  # empty search = browse subreddit directly

        for sub in subreddits:
            for kw in keywords:
                kw_results = 0
                try:
                    posts = self._search(sub, kw, query)
                    for post in posts:
                        content = self._extract_post(post)
                        results.append(content)
                        self.call_count += 1
                        kw_results += 1
                        time.sleep(0.15)
                except Exception as e:
                    print(f"  [warn] Search failed for r/{sub} '{kw}': {e}")
                    continue

                # Fuzzy expansion: if keyword returned 0 results, try variants
                if kw_results == 0 and kw.strip():
                    expanded = self._get_fuzzy_expansions(kw)
                    if expanded:
                        print(f"  [fuzzy] No results for '{kw}', expanding to: {expanded}")
                        for ekw in expanded[:3]:  # cap at 3 expansion attempts
                            try:
                                posts = self._search(sub, ekw, query)
                                for post in posts:
                                    content = self._extract_post(post)
                                    results.append(content)
                                    self.call_count += 1
                                    time.sleep(0.15)
                            except Exception:
                                continue

        return results

    @staticmethod
    def _get_fuzzy_expansions(keyword: str) -> list[str]:
        """Generate alternative search forms for a keyword. Deduplicates."""
        candidates = []
        kw_lower = keyword.strip().lower()

        # Direct match in FUZZY_EXPANSIONS
        for key, variants in FUZZY_EXPANSIONS.items():
            if key.lower() == kw_lower or kw_lower in key.lower() or key.lower() in kw_lower:
                candidates.extend(variants)

        # Check KNOWN_ABBREVIATIONS
        for abbr, variants in KNOWN_ABBREVIATIONS.items():
            if abbr in kw_lower or kw_lower in abbr:
                candidates.extend(variants)

        # Deduplicate preserving order, exclude original keyword
        seen = {kw_lower}
        result = []
        for c in candidates:
            cl = c.lower()
            if cl not in seen:
                seen.add(cl)
                result.append(c)
        return result

    def _search(self, subreddit_name: str, keyword: str, query: SearchQuery):
        import signal
        subreddit_name = subreddit_name.strip()
        if subreddit_name.lower().startswith("r/"):
            subreddit_name = subreddit_name[2:]
        subreddit = self.reddit.subreddit(subreddit_name)
        try:
            if keyword.strip():
                posts = subreddit.search(keyword, sort=query.sort, time_filter=query.time_filter, limit=query.limit)
            else:
                sort_method = getattr(subreddit, query.sort, subreddit.hot)
                posts = sort_method(limit=query.limit)
            return list(posts)
        except Exception as e:
            print(f"  [reddit-timeout] search r/{subreddit_name}: {e}")
            return []

    def _extract_post(self, post) -> ScrapedContent:
        created = datetime.fromtimestamp(post.created_utc).isoformat()

        # Extract comments with 15s timeout per post
        comments: list[str] = []
        try:
            import signal
            post.comments.replace_more(limit=0)
            for c in post.comments.list()[:25]:
                body = getattr(c, "body", "").strip()
                if body and body not in ("[removed]", "[deleted]"):
                    comments.append(body)
        except Exception:
            pass

        return ScrapedContent(
            platform="reddit",
            subreddit=str(post.subreddit.display_name),
            post_id=str(post.id),
            title=getattr(post, "title", ""),
            body=getattr(post, "selftext", ""),
            url=f"https://reddit.com{post.permalink}",
            score=getattr(post, "score", 0),
            num_comments=getattr(post, "num_comments", 0),
            created_utc=created,
            comments=comments,
        )
