import time
import threading
from collections import defaultdict
from typing import Dict, List


class SlidingWindowRateLimiter:
    """
    In-memory rate limiter using the Sliding Window Log algorithm.
    Tracks request timestamps per (user_id, model_id) pair and enforces
    a configurable request limit within a rolling time window.
    """

    def __init__(self, default_limit: int = 100, window_seconds: int = 3600):
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        self.request_logs: Dict[str, List[float]] = defaultdict(list)
        self.locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)
        self.global_lock = threading.Lock()

    def _get_key(self, user_id: str, model_id: str) -> str:
        return f"{user_id}:{model_id}"

    def _get_lock(self, key: str) -> threading.Lock:
        with self.global_lock:
            return self.locks[key]

    def _cleanup_old_entries(self, key: str, current_time: float) -> None:
        window_start = current_time - self.window_seconds
        self.request_logs[key] = [
            ts for ts in self.request_logs[key] if ts > window_start
        ]

    def allow(self, user_id: str, model_id: str, limit: int = None) -> bool:
        """
        Check if a request from user_id for model_id should be allowed.
        Returns True if within rate limit, False otherwise.
        """
        key = self._get_key(user_id, model_id)
        lock = self._get_lock(key)
        effective_limit = limit if limit is not None else self.default_limit

        with lock:
            current_time = time.time()
            self._cleanup_old_entries(key, current_time)

            if len(self.request_logs[key]) >= effective_limit:
                return False

            self.request_logs[key].append(current_time)
            return True

    def get_usage(self, user_id: str, model_id: str) -> dict:
        """
        Returns current usage stats for a user+model pair.
        """
        key = self._get_key(user_id, model_id)
        lock = self._get_lock(key)

        with lock:
            current_time = time.time()
            self._cleanup_old_entries(key, current_time)
            count = len(self.request_logs[key])

            return {
                "user_id": user_id,
                "model_id": model_id,
                "requests_used": count,
                "requests_remaining": max(0, self.default_limit - count),
                "window_seconds": self.window_seconds
            }

    def reset(self, user_id: str, model_id: str) -> None:
        """
        Clears the request log for a specific user+model pair.
        """
        key = self._get_key(user_id, model_id)
        lock = self._get_lock(key)

        with lock:
            self.request_logs[key] = []
