import time
import redis


RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

local window_start = now - window
redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

local current_count = redis.call('ZCARD', key)

if current_count >= limit then
    return 0
end

redis.call('ZADD', key, now, now .. '-' .. math.random(1000000))
redis.call('EXPIRE', key, window)
return 1
"""

GET_USAGE_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])

local window_start = now - window
redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

return redis.call('ZCARD', key)
"""


class RedisRateLimiter:
    """
    Distributed rate limiter using Redis sorted sets for the Sliding Window Log.
    Uses Lua scripts for atomic operations across distributed instances.
    """

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        default_limit: int = 100,
        window_seconds: int = 3600,
        key_prefix: str = "ratelimit"
    ):
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True
        )
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        self.key_prefix = key_prefix

        self.rate_limit_sha = self.redis_client.script_load(RATE_LIMIT_SCRIPT)
        self.get_usage_sha = self.redis_client.script_load(GET_USAGE_SCRIPT)

    def _get_key(self, user_id: str, model_id: str) -> str:
        return f"{self.key_prefix}:{user_id}:{model_id}"

    def allow(self, user_id: str, model_id: str, limit: int = None) -> bool:
        """
        Check if request should be allowed using atomic Redis operations.
        Returns True if within rate limit, False otherwise.
        """
        key = self._get_key(user_id, model_id)
        effective_limit = limit if limit is not None else self.default_limit
        now = time.time()

        result = self.redis_client.evalsha(
            self.rate_limit_sha,
            1,
            key,
            now,
            self.window_seconds,
            effective_limit
        )
        return result == 1

    def get_usage(self, user_id: str, model_id: str) -> dict:
        """
        Returns current usage stats for a user+model pair from Redis.
        """
        key = self._get_key(user_id, model_id)
        now = time.time()

        count = self.redis_client.evalsha(
            self.get_usage_sha,
            1,
            key,
            now,
            self.window_seconds
        )

        return {
            "user_id": user_id,
            "model_id": model_id,
            "requests_used": count,
            "requests_remaining": max(0, self.default_limit - count),
            "window_seconds": self.window_seconds
        }

    def reset(self, user_id: str, model_id: str) -> None:
        """
        Clears the rate limit data for a specific user+model pair.
        """
        key = self._get_key(user_id, model_id)
        self.redis_client.delete(key)

    def close(self) -> None:
        """
        Closes the Redis connection.
        """
        self.redis_client.close()
