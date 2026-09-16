from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass

from redis.asyncio import Redis


QUEUE_NAME = "tuzsbot:jobs"
JOB_PREFIX = "tuzsbot:job:"


@dataclass(frozen=True)
class QueueJob:
    job_id: str
    user_id: int
    chat_id: int
    archive_path: str
    job_root: str
    created_at: float


class RedisJobQueue:
    def __init__(self, url: str, ttl_seconds: int):
        self.redis: Redis = Redis.from_url(url, decode_responses=True)
        self.ttl_seconds = ttl_seconds

    async def ping(self) -> None:
        await self.redis.ping()

    async def close(self) -> None:
        await self.redis.aclose()

    def _key(self, job_id: str) -> str:
        return f"{JOB_PREFIX}{job_id}"

    async def create(self, job: QueueJob) -> None:
        key = self._key(job.job_id)
        payload = asdict(job)
        payload["status"] = "queued"
        await self.redis.hset(key, mapping=payload)
        await self.redis.expire(key, self.ttl_seconds)
        await self.redis.rpush(QUEUE_NAME, json.dumps(asdict(job), separators=(",", ":")))

    async def get(self, job_id: str) -> dict[str, str]:
        return await self.redis.hgetall(self._key(job_id))

    async def update(self, job_id: str, **fields: str) -> None:
        if fields:
            await self.redis.hset(self._key(job_id), mapping=fields)
            await self.redis.expire(self._key(job_id), self.ttl_seconds)

    async def user_has_active_job(self, user_id: int) -> bool:
        pattern = f"{JOB_PREFIX}*"
        async for key in self.redis.scan_iter(match=pattern, count=100):
            data = await self.redis.hgetall(key)
            if data.get("user_id") == str(user_id) and data.get("status") in {"queued", "running"}:
                return True
        return False

    async def claim(self, timeout: int = 5) -> QueueJob | None:
        item = await self.redis.blpop(QUEUE_NAME, timeout=timeout)
        if not item:
            return None
        payload = json.loads(item[1])
        job = QueueJob(**payload)
        await self.update(job.job_id, status="running", started_at=str(time.time()))
        return job
