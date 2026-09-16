from __future__ import annotations

import asyncio
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Job:
    job_id: str
    user_id: int
    root: Path
    created_at: float
    files: list[Path]


class JobManager:
    def __init__(self, root: Path, max_concurrent: int, max_jobs_per_user: int, ttl_seconds: int):
        self.root = root
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.max_jobs_per_user = max_jobs_per_user
        self.ttl_seconds = ttl_seconds
        self.jobs: dict[str, Job] = {}
        self.user_jobs: dict[int, set[str]] = {}
        self.lock = asyncio.Lock()

    async def create(self, user_id: int) -> tuple[Job | None, Path]:
        async with self.lock:
            active = self.user_jobs.get(user_id, set())
            if len(active) >= self.max_jobs_per_user:
                return None, self.root
            job_id = uuid.uuid4().hex[:16]
            root = self.root / f"job-{job_id}"
            root.mkdir(parents=True, exist_ok=False)
            job = Job(job_id, user_id, root, time.time(), [])
            self.jobs[job_id] = job
            active.add(job_id)
            self.user_jobs[user_id] = active
            return job, root

    async def release(self, job_id: str) -> None:
        async with self.lock:
            job = self.jobs.pop(job_id, None)
            if not job:
                return
            ids = self.user_jobs.get(job.user_id)
            if ids:
                ids.discard(job_id)
                if not ids:
                    self.user_jobs.pop(job.user_id, None)
        shutil.rmtree(job.root, ignore_errors=True)

    async def get(self, job_id: str, user_id: int) -> Job | None:
        async with self.lock:
            job = self.jobs.get(job_id)
            if not job or job.user_id != user_id:
                return None
            if time.time() - job.created_at > self.ttl_seconds:
                return None
            return job

    async def cleanup_expired(self) -> None:
        while True:
            await asyncio.sleep(min(60, self.ttl_seconds))
            async with self.lock:
                expired = [job_id for job_id, job in self.jobs.items() if time.time() - job.created_at > self.ttl_seconds]
            for job_id in expired:
                await self.release(job_id)
