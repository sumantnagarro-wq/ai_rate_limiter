import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

load_dotenv()

from rate_limiter import SlidingWindowRateLimiter
from redis_limiter import RedisRateLimiter
from models import TenantTier, get_limit_for_request, RateLimitConfig


app = FastAPI(title="AI Inference Rate Limiter")

config = RateLimitConfig(
    default_limit=int(os.getenv("RATE_LIMIT_DEFAULT", "100")),
    window_seconds=int(os.getenv("RATE_LIMIT_WINDOW", "3600")),
    redis_host=os.getenv("REDIS_HOST", "localhost"),
    redis_port=int(os.getenv("REDIS_PORT", "6379")),
    use_redis=os.getenv("USE_REDIS", "false").lower() == "true"
)

if config.use_redis:
    limiter = RedisRateLimiter(
        redis_host=config.redis_host,
        redis_port=config.redis_port,
        default_limit=config.default_limit,
        window_seconds=config.window_seconds
    )
else:
    limiter = SlidingWindowRateLimiter(
        default_limit=config.default_limit,
        window_seconds=config.window_seconds
    )


class InferenceRequest(BaseModel):
    user_id: str
    model_id: str
    tenant_tier: Optional[str] = None


class AllowResponse(BaseModel):
    allowed: bool
    user_id: str
    model_id: str


class UsageResponse(BaseModel):
    user_id: str
    model_id: str
    requests_used: int
    requests_remaining: int
    window_seconds: int


@app.post("/allow", response_model=AllowResponse)
def check_rate_limit(request: InferenceRequest):
    """
    Main endpoint to check if an inference request should be allowed.
    This sits in front of the AI model serving infrastructure.
    """
    tenant_tier = None
    if request.tenant_tier:
        try:
            tenant_tier = TenantTier(request.tenant_tier)
        except ValueError:
            pass

    limit = get_limit_for_request(
        tenant_tier=tenant_tier,
        model_id=request.model_id,
        default=config.default_limit
    )

    allowed = limiter.allow(request.user_id, request.model_id, limit=limit)

    return AllowResponse(
        allowed=allowed,
        user_id=request.user_id,
        model_id=request.model_id
    )


@app.get("/usage/{user_id}/{model_id}", response_model=UsageResponse)
def get_usage(user_id: str, model_id: str):
    """
    Returns current rate limit usage for a user+model combination.
    """
    usage = limiter.get_usage(user_id, model_id)
    return UsageResponse(**usage)


@app.delete("/usage/{user_id}/{model_id}")
def reset_usage(user_id: str, model_id: str):
    """
    Resets the rate limit counter for a user+model combination.
    Typically used by admins for support cases.
    """
    limiter.reset(user_id, model_id)
    return {"status": "reset", "user_id": user_id, "model_id": model_id}


@app.get("/health")
def health_check():
    """
    Simple health check endpoint for load balancer probes.
    """
    return {"status": "healthy"}
