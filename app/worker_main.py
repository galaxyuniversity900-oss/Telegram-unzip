from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .archive import format_size, iter_files
from .config import Settings
from .redis_queue import RedisJobQueue
from .staged import extract_archive_staged


def result_keyboard(job_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 Browse files", callback_data=f"b:{job_id}:0")],
        [InlineKeyboardButton(text="📤 Download first page", callback_data=f"d:{job_id}:0")],
    ])


async def run_worker() -> None:
    settings = Settings.from_env()
    queue = RedisJobQueue(settings.redis_url, settings.job_ttl_seconds)
    bot = Bot(settings.telegram_bot_token)
    await queue.ping()

    async def process(job):
        try:
            await queue.update(job.job_id, status="running", progress="0")
            await bot.send_message(job.chat_id, "⚙️ Worker started extraction…")
            started = time.monotonic()
            output = Path(job.job_root) / "extracted"

            def progress(batch: int, total_batches: int, completed: int, written: int) -> None:
                asyncio.create_task(queue.update(
                    job.job_id,
                    progress=str(completed),
                    batches=f"{batch}/{total_batches}",
                    bytes_written=str(written),
                ))

            result = await asyncio.to_thread(
                extract_archive_staged,
                Path(job.archive_path),
                output,
                settings.max_files,
                settings.max_extracted_bytes,
                settings.max_ratio,
                settings.extraction_timeout_seconds,
                settings.extraction_batch_size,
                progress,
                None,
            )
            files = list(iter_files(output))
            await queue.update(job.job_id, status="completed", progress=str(result.entries), files=str(len(files)), bytes_written=str(result.bytes_written))
            pages = max(1, (len(files) + 9) // 10)
            await bot.send_message(
                job.chat_id,
                "✅ Extraction complete\n\n"
                f"🧩 Batches: {result.batches:,}\n"
                f"📁 Files: {result.entries:,}\n"
                f"💾 Output: {format_size(result.bytes_written)}\n"
                f"📄 Pages: {pages}\n"
                f"⏱️ Elapsed: {time.monotonic() - started:.1f}s\n\n"
                f"Job ID: {job.job_id}",
                reply_markup=result_keyboard(job.job_id),
            )
        except Exception as exc:
            await queue.update(job.job_id, status="failed", error=str(exc))
            with contextlib.suppress(Exception):
                await bot.send_message(job.chat_id, f"❌ Extraction failed: {exc}\n\nJob ID: {job.job_id}")

    try:
        while True:
            job = await queue.claim(timeout=5)
            if job is not None:
                await process(job)
    finally:
        await bot.session.close()
        await queue.close()


if __name__ == "__main__":
    asyncio.run(run_worker())
