"""Development cache for YouTube API responses.

Hash-based caching: same endpoint + params = cache hit, 0 API units.
Stores JSON responses in .cache/youtube/ directory.
"""

import hashlib
import json
import os
import time


class ResponseCache:
    def __init__(self, cache_dir: str = ".cache/youtube"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _hash(self, endpoint: str, params: dict) -> str:
        raw = endpoint + json.dumps(params, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get(self, endpoint: str, params: dict) -> dict | None:
        key = self._hash(endpoint, params)
        path = os.path.join(self.cache_dir, f"{key}.json")
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            # Cache valid for 24h for development
            if time.time() - data.get("_cached_at", 0) < 86400:
                return data.get("response")
        return None

    def set(self, endpoint: str, params: dict, response: dict) -> None:
        key = self._hash(endpoint, params)
        path = os.path.join(self.cache_dir, f"{key}.json")
        with open(path, "w") as f:
            json.dump({
                "endpoint": endpoint,
                "params": params,
                "_cached_at": time.time(),
                "response": response,
            }, f, indent=2)

    def clear(self) -> int:
        count = 0
        for fname in os.listdir(self.cache_dir):
            if fname.endswith(".json"):
                os.remove(os.path.join(self.cache_dir, fname))
                count += 1
        return count
