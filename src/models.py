from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TenantTier(Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class ModelTier(Enum):
    HEAVY = "heavy"
    STANDARD = "standard"
    LIGHT = "light"


TENANT_LIMITS = {
    TenantTier.FREE: 100,
    TenantTier.PRO: 1000,
    TenantTier.ENTERPRISE: 10000,
}

MODEL_LIMITS = {
    ModelTier.HEAVY: 50,
    ModelTier.STANDARD: 200,
    ModelTier.LIGHT: 1000,
}

MODEL_TIER_MAPPING = {
    "gpt-4": ModelTier.HEAVY,
    "gpt-4-turbo": ModelTier.HEAVY,
    "claude-3-opus": ModelTier.HEAVY,
    "gpt-3.5-turbo": ModelTier.STANDARD,
    "claude-3-sonnet": ModelTier.STANDARD,
    "text-embedding-ada": ModelTier.LIGHT,
    "text-embedding-3-small": ModelTier.LIGHT,
}


@dataclass
class RateLimitConfig:
    default_limit: int = 100
    window_seconds: int = 3600
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    use_redis: bool = False


@dataclass
class RateLimitRequest:
    user_id: str
    model_id: str
    tenant_tier: Optional[TenantTier] = None


@dataclass
class RateLimitResponse:
    allowed: bool
    user_id: str
    model_id: str
    requests_used: int
    requests_remaining: int
    limit: int


def get_limit_for_request(
    tenant_tier: Optional[TenantTier] = None,
    model_id: Optional[str] = None,
    default: int = 100
) -> int:
    """
    Determines the effective rate limit based on tenant tier and model.
    Uses the more restrictive limit when both are specified.
    """
    limits = []

    if tenant_tier and tenant_tier in TENANT_LIMITS:
        limits.append(TENANT_LIMITS[tenant_tier])

    if model_id and model_id in MODEL_TIER_MAPPING:
        model_tier = MODEL_TIER_MAPPING[model_id]
        limits.append(MODEL_LIMITS[model_tier])

    if not limits:
        return default

    return min(limits)
