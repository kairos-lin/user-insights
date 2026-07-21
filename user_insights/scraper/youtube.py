"""Quota-optimized YouTube Data API v3 scraper.

Uses urllib (stdlib) for HTTP — no googleapiclient dependency, no httplib2 issues.

Strict quota budget per query (~120 units max):
  search.list:      100 units (ONE call, maxResults=5, fields filter)
  videos.list:        1 unit  (ONE call, up to 50 IDs batched)
  commentThreads:     1 unit  (ONE call per video, maxResults=20)

Anti-rate-limit:
  Exponential backoff + jitter for HTTP 429
  Catch HTTP 403 quotaExceeded → save partial data, warn, continue
  NEVER call search.list in a loop
"""

import json
import os
import random
import re
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

from .cache import ResponseCache

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


class QuotaExceededError(Exception):
    pass


class YouTubeScraper:
    def __init__(self, api_key: str, proxy: str | None = None):
        self.api_key = api_key
        self.cache = ResponseCache()
        self.quota_used = 0
        self.quota_budget = 9500
        self.proxy = proxy

    # ── Public API ────────────────────────────────────────────────────

    def search_videos(self, keywords: list[str], max_results: int = 5) -> list[str]:
        """ONE search.list call. Returns video IDs. Cost: 100 units."""
        query = " ".join(keywords)
        params = {
            "part": "id",
            "q": query,
            "maxResults": max_results,
            "type": "video",
            "order": "relevance",
            "fields": "items(id/videoId)",
        }
        cached = self.cache.get("search.list", params)
        if cached is not None:
            return cached

        self._check_quota(100)
        data = self._call_api("search", params)
        self.quota_used += 100
        video_ids = [item["id"]["videoId"] for item in data.get("items", [])]
        self.cache.set("search.list", params, video_ids)
        return video_ids

    def get_video_details(self, video_ids: list[str]) -> list[dict]:
        """ONE videos.list call for up to 50 IDs. Cost: 1 unit."""
        if not video_ids:
            return []

        all_items = []
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            ids_str = ",".join(batch)
            params = {
                "part": "snippet,statistics",
                "id": ids_str,
                "fields": "items(id,snippet(title,description,channelTitle),statistics(viewCount,likeCount,commentCount))",
            }
            cached = self.cache.get("videos.list", params)
            if cached is not None:
                all_items.extend(cached)
                continue

            self._check_quota(1)
            data = self._call_api("videos", params)
            self.quota_used += 1
            items = data.get("items", [])
            self.cache.set("videos.list", params, items)
            all_items.extend(items)

        return all_items

    def get_comments(self, video_id: str, max_results: int = 20) -> list[str]:
        """ONE commentThreads.list call per video. order=relevance. Cost: 1 unit."""
        params = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": max_results,
            "order": "relevance",
            "fields": "items/snippet/topLevelComment/snippet/textDisplay",
        }
        cached = self.cache.get("commentThreads.list", params)
        if cached is not None:
            return cached

        self._check_quota(1)
        data = self._call_api("commentThreads", params)
        self.quota_used += 1
        comments = []
        for item in data.get("items", []):
            text = (
                item.get("snippet", {})
                .get("topLevelComment", {})
                .get("snippet", {})
                .get("textDisplay", "")
            )
            if text.strip():
                comments.append(text)
        self.cache.set("commentThreads.list", params, comments)
        return comments

    def get_comments_paginated(
        self, video_id: str, max_pages: int = 3, per_page: int = 30
    ) -> list[str]:
        """Paginate commentThreads.list up to max_pages. 1 unit per page."""
        all_comments: list[str] = []
        page_token: str | None = None
        for page in range(max_pages):
            params = {
                "part": "snippet",
                "videoId": video_id,
                "maxResults": per_page,
                "order": "relevance",
                "fields": "items/snippet/topLevelComment/snippet/textDisplay,nextPageToken",
            }
            if page_token:
                params["pageToken"] = page_token

            cached = self.cache.get("commentThreads.page", params)
            if cached is not None:
                all_comments.extend(cached.get("comments", []))
                page_token = cached.get("nextPageToken")
                if not page_token:
                    break
                continue

            self._check_quota(1)
            data = self._call_api("commentThreads", params)
            self.quota_used += 1
            comments = []
            for item in data.get("items", []):
                text = (
                    item.get("snippet", {})
                    .get("topLevelComment", {})
                    .get("snippet", {})
                    .get("textDisplay", "")
                )
                if text.strip():
                    comments.append(text)
            all_comments.extend(comments)
            page_token = data.get("nextPageToken")
            self.cache.set("commentThreads.page", params, {
                "comments": comments, "nextPageToken": page_token,
            })
            if not page_token:
                break
        return all_comments

    def get_transcript(self, video_id: str) -> str:
        """yt-dlp transcript extraction. Cost: 0 units, no API key needed."""
        params = {"video_id": video_id}
        cached = self.cache.get("transcript", params)
        if cached is not None:
            return cached if isinstance(cached, str) else ""

        url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            cmd = [
                "yt-dlp", "--write-auto-subs", "--sub-lang", "en",
                "--skip-download", "--print", "after_move:filepath",
                "--sub-format", "vtt", "-o",
                f"{tempfile.gettempdir()}/%(id)s.%(ext)s",
            ]
            if self.proxy:
                cmd.insert(1, "--proxy")
                cmd.insert(2, self.proxy)
            # Also set env proxy as fallback
            env = os.environ.copy()
            if self.proxy:
                env["HTTP_PROXY"] = self.proxy
                env["HTTPS_PROXY"] = self.proxy
            cmd.append(url)
            result = subprocess.run(cmd,
                capture_output=True, text=True, timeout=60, env=env,
            )
            output = result.stdout + result.stderr
            match = re.search(r"([^\s]+\.en\.vtt)", output)
            if not match:
                match = re.search(r"([^\s]+\.vtt)", output)

            if match:
                vtt_path = match.group(1).strip()
                if os.path.exists(vtt_path):
                    text = _parse_vtt(vtt_path)
                    os.remove(vtt_path)
                    self.cache.set("transcript", params, text)
                    return text

            for fname in os.listdir(tempfile.gettempdir()):
                if fname.endswith(".en.vtt") and video_id in fname:
                    fpath = os.path.join(tempfile.gettempdir(), fname)
                    text = _parse_vtt(fpath)
                    os.remove(fpath)
                    self.cache.set("transcript", params, text)
                    return text

            self.cache.set("transcript", params, "")
            return ""
        except Exception:
            self.cache.set("transcript", params, "")
            return ""

    # ── Internal ──────────────────────────────────────────────────────

    def _call_api(self, endpoint: str, params: dict, timeout: int = 15) -> dict:
        """Make a YouTube Data API v3 request using urllib (stdlib). Hard timeout."""
        params["key"] = self.api_key
        url = f"{YOUTUBE_API_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"

        handlers = []
        if self.proxy:
            handlers.append(urllib.request.ProxyHandler({"https": self.proxy}))
        opener = urllib.request.build_opener(*handlers) if handlers else urllib.request.build_opener()

        for attempt in range(2):
            try:
                req = urllib.request.Request(url)
                with opener.open(req, timeout=timeout) as resp:
                    body = resp.read().decode("utf-8")
                    data = json.loads(body)

                if "error" in data:
                    code = data["error"].get("code", 0)
                    errors = data["error"].get("errors", [{}])
                    if any(e.get("reason") == "quotaExceeded" for e in errors):
                        raise QuotaExceededError(f"YouTube API quota exceeded")
                    if code == 403:
                        raise QuotaExceededError(f"YouTube API 403: {data['error']}")
                    if code == 429 or "rate" in str(data).lower():
                        backoff = (2 ** attempt) + random.uniform(0, 1)
                        time.sleep(backoff)
                        continue
                    # Other API errors: return empty
                    return {}

                return data

            except QuotaExceededError:
                raise
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    backoff = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(backoff)
                    continue
                if e.code == 403:
                    body = e.read().decode("utf-8", errors="ignore")
                    if "quotaExceeded" in body:
                        raise QuotaExceededError("YouTube API quota exceeded")
                    return {}
                return {}
            except Exception:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                return {}

        return {}

    def _check_quota(self, cost: int):
        if self.quota_used + cost > self.quota_budget:
            raise QuotaExceededError(
                f"Quota budget exhausted ({self.quota_used}/{self.quota_budget}). "
                f"Next operation costs {cost} units."
            )


def _parse_vtt(path: str) -> str:
    """Strip VTT timestamps and metadata, return plain text."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    lines = content.split("\n")
    cleaned = []
    skip = True
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if skip:
            if line == "WEBVTT" or line.startswith("Kind:") or line.startswith("Language:"):
                continue
            skip = False
        if "-->" in line:
            continue
        if re.match(r"^\d+$", line):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            cleaned.append(line)
    return " ".join(cleaned)
