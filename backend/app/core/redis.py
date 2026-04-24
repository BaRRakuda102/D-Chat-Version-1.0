from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis, from_url

from app.core.config import settings

redis_client: Redis | None = None


async def init_redis() -> Redis:
    global redis_client
    if redis_client is None:
        redis_client = from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return redis_client


def get_redis() -> Redis:
    if redis_client is None:
        raise RuntimeError("Redis client is not initialized")
    return redis_client


async def close_redis() -> None:
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        redis_client = None


class CacheService:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def get_json(self, key: str) -> dict[str, Any] | None:
        raw_value = await self.redis.get(key)
        if not raw_value:
            return None
        return json.loads(raw_value)

    async def set_json(self, key: str, value: dict[str, Any], ttl: int) -> None:
        await self.redis.set(key, json.dumps(value), ex=ttl)

    async def delete(self, *keys: str) -> None:
        if keys:
            await self.redis.delete(*keys)
