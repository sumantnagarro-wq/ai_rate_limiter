import sys
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, '../src')


class TestRedisRateLimiter(unittest.TestCase):

    def setUp(self):
        self.mock_redis = MagicMock()
        self.mock_redis.script_load.return_value = "fake_sha"

    @patch('redis.Redis')
    def test_allow_returns_true_when_under_limit(self, mock_redis_class):
        mock_redis_class.return_value = self.mock_redis
        self.mock_redis.evalsha.return_value = 1

        from redis_limiter import RedisRateLimiter
        limiter = RedisRateLimiter()

        result = limiter.allow("user1", "gpt-4")

        self.assertTrue(result)
        self.mock_redis.evalsha.assert_called_once()

    @patch('redis.Redis')
    def test_allow_returns_false_when_over_limit(self, mock_redis_class):
        mock_redis_class.return_value = self.mock_redis
        self.mock_redis.evalsha.return_value = 0

        from redis_limiter import RedisRateLimiter
        limiter = RedisRateLimiter()

        result = limiter.allow("user1", "gpt-4")

        self.assertFalse(result)

    @patch('redis.Redis')
    def test_get_usage_returns_correct_structure(self, mock_redis_class):
        mock_redis_class.return_value = self.mock_redis
        self.mock_redis.evalsha.return_value = 42

        from redis_limiter import RedisRateLimiter
        limiter = RedisRateLimiter(default_limit=100)

        usage = limiter.get_usage("user1", "gpt-4")

        self.assertEqual(usage["user_id"], "user1")
        self.assertEqual(usage["model_id"], "gpt-4")
        self.assertEqual(usage["requests_used"], 42)
        self.assertEqual(usage["requests_remaining"], 58)

    @patch('redis.Redis')
    def test_reset_calls_delete(self, mock_redis_class):
        mock_redis_class.return_value = self.mock_redis

        from redis_limiter import RedisRateLimiter
        limiter = RedisRateLimiter()

        limiter.reset("user1", "gpt-4")

        self.mock_redis.delete.assert_called_once_with("ratelimit:user1:gpt-4")

    @patch('redis.Redis')
    def test_custom_key_prefix(self, mock_redis_class):
        mock_redis_class.return_value = self.mock_redis

        from redis_limiter import RedisRateLimiter
        limiter = RedisRateLimiter(key_prefix="myapp")

        limiter.reset("user1", "gpt-4")

        self.mock_redis.delete.assert_called_once_with("myapp:user1:gpt-4")

    @patch('redis.Redis')
    def test_custom_limit_passed_to_script(self, mock_redis_class):
        mock_redis_class.return_value = self.mock_redis
        self.mock_redis.evalsha.return_value = 1

        from redis_limiter import RedisRateLimiter
        limiter = RedisRateLimiter(default_limit=100)

        limiter.allow("user1", "gpt-4", limit=50)

        call_args = self.mock_redis.evalsha.call_args
        self.assertEqual(call_args[0][4], 50)


class TestRedisRateLimiterIntegration(unittest.TestCase):
    """
    Integration tests that require a running Redis instance.
    These are skipped by default - run with REDIS_TEST=1 to enable.
    """

    @classmethod
    def setUpClass(cls):
        import os
        cls.run_integration = os.getenv("REDIS_TEST", "0") == "1"

    def setUp(self):
        if not self.run_integration:
            self.skipTest("Redis integration tests disabled")

        from redis_limiter import RedisRateLimiter
        self.limiter = RedisRateLimiter(
            default_limit=5,
            window_seconds=2,
            key_prefix="test_ratelimit"
        )
        self.limiter.reset("testuser", "testmodel")

    def tearDown(self):
        if hasattr(self, 'limiter'):
            self.limiter.reset("testuser", "testmodel")
            self.limiter.close()

    def test_integration_basic_rate_limiting(self):
        for i in range(5):
            result = self.limiter.allow("testuser", "testmodel")
            self.assertTrue(result, f"Request {i+1} should be allowed")

        result = self.limiter.allow("testuser", "testmodel")
        self.assertFalse(result, "6th request should be blocked")

    def test_integration_window_expiry(self):
        for _ in range(5):
            self.limiter.allow("testuser", "testmodel")

        time.sleep(2.1)

        result = self.limiter.allow("testuser", "testmodel")
        self.assertTrue(result, "Should allow after window expires")


if __name__ == "__main__":
    unittest.main()
