import sys
import time
import threading
import unittest

sys.path.insert(0, '../src')

from rate_limiter import SlidingWindowRateLimiter


class TestSlidingWindowRateLimiter(unittest.TestCase):

    def setUp(self):
        self.limiter = SlidingWindowRateLimiter(default_limit=5, window_seconds=2)

    def test_allows_requests_under_limit(self):
        for i in range(5):
            result = self.limiter.allow("user1", "gpt-4")
            self.assertTrue(result, f"Request {i+1} should be allowed")

    def test_blocks_requests_over_limit(self):
        for _ in range(5):
            self.limiter.allow("user1", "gpt-4")

        result = self.limiter.allow("user1", "gpt-4")
        self.assertFalse(result, "6th request should be blocked")

    def test_separate_limits_per_user(self):
        for _ in range(5):
            self.limiter.allow("user1", "gpt-4")

        result = self.limiter.allow("user2", "gpt-4")
        self.assertTrue(result, "Different user should have separate limit")

    def test_separate_limits_per_model(self):
        for _ in range(5):
            self.limiter.allow("user1", "gpt-4")

        result = self.limiter.allow("user1", "gpt-3.5")
        self.assertTrue(result, "Different model should have separate limit")

    def test_window_expiry(self):
        for _ in range(5):
            self.limiter.allow("user1", "gpt-4")

        self.assertFalse(self.limiter.allow("user1", "gpt-4"))

        time.sleep(2.1)

        result = self.limiter.allow("user1", "gpt-4")
        self.assertTrue(result, "Should allow after window expires")

    def test_custom_limit_override(self):
        for _ in range(3):
            self.limiter.allow("user1", "gpt-4", limit=3)

        result = self.limiter.allow("user1", "gpt-4", limit=3)
        self.assertFalse(result, "Should block at custom limit of 3")

    def test_get_usage(self):
        for _ in range(3):
            self.limiter.allow("user1", "gpt-4")

        usage = self.limiter.get_usage("user1", "gpt-4")

        self.assertEqual(usage["requests_used"], 3)
        self.assertEqual(usage["requests_remaining"], 2)
        self.assertEqual(usage["user_id"], "user1")
        self.assertEqual(usage["model_id"], "gpt-4")

    def test_reset(self):
        for _ in range(5):
            self.limiter.allow("user1", "gpt-4")

        self.assertFalse(self.limiter.allow("user1", "gpt-4"))

        self.limiter.reset("user1", "gpt-4")

        result = self.limiter.allow("user1", "gpt-4")
        self.assertTrue(result, "Should allow after reset")

    def test_concurrent_requests(self):
        limiter = SlidingWindowRateLimiter(default_limit=100, window_seconds=60)
        results = []

        def make_request():
            result = limiter.allow("user1", "gpt-4")
            results.append(result)

        threads = [threading.Thread(target=make_request) for _ in range(150)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        allowed_count = sum(1 for r in results if r)
        blocked_count = sum(1 for r in results if not r)

        self.assertEqual(allowed_count, 100, "Exactly 100 requests should be allowed")
        self.assertEqual(blocked_count, 50, "Exactly 50 requests should be blocked")


if __name__ == "__main__":
    unittest.main()
