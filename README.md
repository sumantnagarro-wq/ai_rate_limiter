# AI Inference Rate Limiter

A distributed rate limiter designed to protect GPU resources and enforce fair usage across tenants for AI model serving infrastructure.

## Class Overview

| File | Class/Module | Description |
|------|--------------|-------------|
| `rate_limiter.py` | `SlidingWindowRateLimiter` | In-memory rate limiter with per-key locking |
| `redis_limiter.py` | `RedisRateLimiter` | Distributed rate limiter using Redis sorted sets |
| `api.py` | FastAPI `app` | REST API exposing rate limit endpoints |

## Architecture Overview

```
Client Request → API Gateway → [RATE LIMITER] → Model Router → GPU Pool
```

The rate limiter sits in front of AI inference endpoints, acting as a gatekeeper before requests reach the model serving infrastructure.

## Design Decisions

### Why Sliding Window Log?

We chose the Sliding Window Log algorithm over alternatives for these reasons:

| Algorithm | Pros | Cons |
|-----------|------|------|
| Fixed Window | Simple, low memory | Boundary burst problem (2x limit at window edges) |
| **Sliding Window Log** | Exact counting, no boundary issues | Higher memory per key |

For AI inference where each request consumes significant GPU resources, precision matters more than memory efficiency. A user shouldn't be able to game the system by timing requests at window boundaries.

### Core Data Structure

For each `(user_id, model_id)` pair, we maintain a sorted list of timestamps:

```
Key: "ratelimit:{user_id}:{model_id}"
Value: [1701234567.123, 1701234568.456, 1701234569.789, ...]
```

**Memory Analysis:**
- Each timestamp: ~8 bytes
- Max entries per key: 100 (at limit)
- Per user+model pair: ~800 bytes
- 100K active pairs: ~80MB

### Algorithm

```
allow(user_id, model_id):
    current_time = now()
    window_start = current_time - 1 hour
    key = "{user_id}:{model_id}"

    Remove timestamps older than window_start
    count = len(timestamps)

    if count >= limit:
        return False

    Add current_time to timestamps
    return True
```

## Concurrency Handling

### Single Instance (In-Memory)

Uses per-key locking to handle concurrent requests:

```python
locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)
```

Each `(user_id, model_id)` pair gets its own lock. A global lock protects the locks dictionary itself. This allows concurrent requests for different user+model pairs while serializing requests for the same pair.

### Distributed (Redis)

Uses Lua scripts for atomic operations:

```lua
local window_start = now - window
redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)
local count = redis.call('ZCARD', key)

if count >= limit then
    return 0
end

redis.call('ZADD', key, now, now .. '-' .. random())
redis.call('EXPIRE', key, window)
return 1
```

This executes atomically on the Redis server, eliminating race conditions between checking the count and adding a new entry.

**Why Redis Sorted Sets?**
- `ZREMRANGEBYSCORE`: O(log(N)+M) removal of old entries
- `ZCARD`: O(1) count
- `ZADD`: O(log(N)) insertion
- Natural ordering by timestamp score
- Built-in TTL support for automatic cleanup

### Sharding Strategy

For high-scale deployments, shard by hashing the key:

```python
shard = hash(f"{user_id}:{model_id}") % num_shards
redis_node = redis_nodes[shard]
```

Consistent hashing ensures even distribution and minimizes redistribution when nodes are added/removed.

## Extensibility

### Different Limits per Tenant

```python
TENANT_LIMITS = {
    TenantTier.FREE: 100,
    TenantTier.PRO: 1000,
    TenantTier.ENTERPRISE: 10000,
}
```

### Different Limits per Model

```python
MODEL_LIMITS = {
    ModelTier.HEAVY: 50,      # GPT-4, Claude Opus
    ModelTier.STANDARD: 200,  # GPT-3.5, Claude Sonnet
    ModelTier.LIGHT: 1000,    # Embeddings
}
```

When both tenant and model limits apply, the system uses the more restrictive limit.

## API

### Check Rate Limit

```
POST /allow
{
    "user_id": "user123",
    "model_id": "gpt-4",
    "tenant_tier": "pro"  // optional
}

Response:
{
    "allowed": true,
    "user_id": "user123",
    "model_id": "gpt-4"
}
```

### Get Usage

```
GET /usage/{user_id}/{model_id}

Response:
{
    "user_id": "user123",
    "model_id": "gpt-4",
    "requests_used": 45,
    "requests_remaining": 55,
    "window_seconds": 3600
}
```

### Reset Usage (Admin)

```
DELETE /usage/{user_id}/{model_id}
```

## Running the Service

### Setup

```bash
pip install -r requirements.txt
cp .env.example .env  # Configure your settings
```

### Local Development (In-Memory)

```bash
cd src
uvicorn api:app --reload --port 8000
```

### Production (Redis)

Edit `.env` to enable Redis:
```
USE_REDIS=true
REDIS_HOST=redis.example.com
REDIS_PORT=6379
```

Then run:
```bash
cd src
uvicorn api:app --host 0.0.0.0 --port 8000
```

### Configuration

Settings are loaded from `.env` file (see `.env.example`):

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| RATE_LIMIT_DEFAULT | 100 | Default requests per window |
| RATE_LIMIT_WINDOW | 3600 | Window size in seconds |
| USE_REDIS | false | Enable distributed mode |
| REDIS_HOST | localhost | Redis server host |
| REDIS_PORT | 6379 | Redis server port |

## Running Tests

```bash
cd tests
python -m pytest test_rate_limiter.py -v
python -m pytest test_models.py -v

# With Redis integration tests
REDIS_TEST=1 python -m pytest test_redis_limiter.py -v
```

## Project Structure

```
ai_inference_limiter/
├── src/
│   ├── rate_limiter.py     # In-memory implementation
│   ├── redis_limiter.py    # Distributed Redis implementation
│   ├── models.py           # Data models and config
│   └── api.py              # FastAPI REST endpoint
├── tests/
│   ├── test_rate_limiter.py
│   ├── test_redis_limiter.py
├── requirements.txt
└── README.md
```
