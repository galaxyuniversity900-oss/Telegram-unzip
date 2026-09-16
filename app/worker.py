from __future__ import annotations

import asyncio
from dataclasses import dataclass

from aiogram.types import Message

from .jobs import JobManager


@dataclass(frozen=True)
class WorkItem:
    message: Message
    archive_path: object
    job_root: object
    job_id: str


class ExtractionQueue:
    """Bounded in-process queue so Telegram polling never waits on extraction."""

    def __init__(self, workers: int, process):
        self.queue: asyncio.Queue[WorkItem] = asyncio.Queue(maxsize=max(1, workers * 4))
        self.workers = max(1, workers)
        self.process = process
        self.tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        if self.tasks:
            return
        self.tasks = [asyncio.create_task(self._worker(i), name=f"extract-worker-{i}") for i in range(self.workers)]

    async def submit(self, item: WorkItem) -> bool:
        try:
            self.queue.put_nowait(item)
            return True
        except asyncio.QueueFull:
            return False

    async def _worker(self, index: int) -> None:
        while True:
            item = await self.queue.get()
            try:
                await self.process(item.message, item.archive_path, item.job_root, item.job_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                # process() owns user-facing error reporting and cleanup.
                pass
            finally:
                self.queue.task_done()

    async def stop(self) -> None:
        for task in self.tasks:
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
