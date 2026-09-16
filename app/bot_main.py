from __future__ import annotations

import asyncio
import contextlib
import re
import shutil
import time
import uuid
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .archive import format_size, iter_files
from .config import Settings
from .downloader import download_url
from .redis_queue import QueueJob, RedisJobQueue

PAGE_SIZE = 10
URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


def safe_name(name: str) -> str:
    value = Path(name).name
    return re.sub(r"[^A-Za-z0-9._ -]", "_", value) or "archive"


def keyboard(job_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 Browse files", callback_data=f"b:{job_id}:0")],
        [InlineKeyboardButton(text="📤 Download first page", callback_data=f"d:{job_id}:0")],
    ])


def browse_keyboard(job_id: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"b:{job_id}:{page-1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"b:{job_id}:{page+1}"))
    rows = [nav] if nav else []
    rows.append([InlineKeyboardButton(text="📤 Download this page", callback_data=f"d:{job_id}:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def main() -> None:
    settings = Settings.from_env()
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    bot = Bot(settings.telegram_bot_token)
    dp = Dispatcher()
    queue = RedisJobQueue(settings.redis_url, settings.job_ttl_seconds)
    await queue.ping()

    async def create_job(message: Message, archive: Path, root: Path) -> str:
        job_id = uuid.uuid4().hex[:16]
        await queue.create(QueueJob(job_id, message.from_user.id, message.chat.id, str(archive), str(root), time.time()))
        return job_id

    @dp.message(CommandStart())
    async def start_handler(message: Message):
        await message.answer(
            "👋 TuzsBot\n\n"
            "Send a ZIP, RAR, 7Z, TAR/GZ/BZ2/XZ archive or a direct HTTP(S) archive URL.\n\n"
            "Jobs are stored in a durable Redis queue and processed by independent workers."
        )

    @dp.message(F.document)
    async def document_handler(message: Message):
        if not message.document or not message.from_user:
            return
        if await queue.user_has_active_job(message.from_user.id):
            await message.answer("⏳ You already have an active job. Please wait for it to finish.")
            return
        if message.document.file_size and message.document.file_size > settings.max_download_bytes:
            await message.answer("❌ File exceeds the configured download limit.")
            return
        root = settings.work_dir / f"job-pending-{uuid.uuid4().hex[:12]}"
        root.mkdir(parents=True, exist_ok=False)
        archive = root / safe_name(message.document.file_name or "archive")
        try:
            await message.answer("⬇️ Downloading archive from Telegram…")
            await bot.download(message.document, destination=archive)
            job_id = await create_job(message, archive, root)
            await message.answer(f"📥 Job queued\n🆔 {job_id}\n👷 Workers will process it independently.")
            new_root = settings.work_dir / f"job-{job_id}"
            root.rename(new_root)
            await queue.update(job_id, archive_path=str(new_root / archive.name), job_root=str(new_root))
        except Exception as exc:
            shutil.rmtree(root, ignore_errors=True)
            await message.answer(f"❌ {exc}")

    @dp.message(F.text.regexp(URL_RE))
    async def url_handler(message: Message):
        if not message.text or not message.from_user:
            return
        if await queue.user_has_active_job(message.from_user.id):
            await message.answer("⏳ You already have an active job. Please wait for it to finish.")
            return
        root = settings.work_dir / f"job-pending-{uuid.uuid4().hex[:12]}"
        root.mkdir(parents=True, exist_ok=False)
        try:
            await message.answer("⬇️ Downloading archive URL…")
            archive, size = await download_url(message.text.strip(), root, settings.max_download_bytes, settings.download_timeout_seconds)
            new_root = settings.work_dir / f"job-{uuid.uuid4().hex[:16]}"
            root.rename(new_root)
            archive = new_root / archive.name
            job_id = uuid.uuid4().hex[:16]
            await queue.create(QueueJob(job_id, message.from_user.id, message.chat.id, str(archive), str(new_root), time.time()))
            await message.answer(f"📥 Download complete: {format_size(size)}\n📋 Job queued\n🆔 {job_id}")
        except Exception as exc:
            shutil.rmtree(root, ignore_errors=True)
            await message.answer(f"❌ {exc}")

    @dp.callback_query(F.data.regexp(re.compile(r"^[bd]:[A-Za-z0-9_-]+:\d+$")))
    async def job_callback(callback: CallbackQuery):
        if not callback.from_user or not callback.data:
            return
        action, job_id, raw_page = callback.data.split(":")
        data = await queue.get(job_id)
        if not data or data.get("user_id") != str(callback.from_user.id) or data.get("status") != "completed":
            await callback.answer("This job is unavailable.", show_alert=True)
            return
        root = Path(data["job_root"]) / "extracted"
        files = list(iter_files(root)) if root.exists() else []
        total_pages = max(1, (len(files) + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(int(raw_page), total_pages - 1)
        start = page * PAGE_SIZE
        selected = files[start:start + PAGE_SIZE]
        if action == "b":
            lines = [f"📂 Page {page + 1}/{total_pages}", ""]
            for index, path in enumerate(selected, start=start + 1):
                lines.append(f"{index}. {path.relative_to(root).as_posix()} — {format_size(path.stat().st_size)}")
            await callback.message.edit_text("\n".join(lines), reply_markup=browse_keyboard(job_id, page, total_pages))
            await callback.answer()
            return
        await callback.answer("Sending files…")
        for path in selected:
            if path.exists() and path.is_file():
                relative = path.relative_to(root).as_posix()
                await callback.message.answer_document(FSInputFile(path), caption=relative[:900])

    @dp.message()
    async def fallback(message: Message):
        await message.answer("Send an archive file or a direct HTTP(S) archive URL. Use /start for help.")

    async def cleanup_loop():
        while True:
            await asyncio.sleep(60)
            cutoff = time.time() - settings.job_ttl_seconds
            for path in settings.work_dir.glob("job-*"):
                with contextlib.suppress(OSError):
                    if path.stat().st_mtime < cutoff:
                        shutil.rmtree(path, ignore_errors=True)

    cleanup = asyncio.create_task(cleanup_loop())
    try:
        await dp.start_polling(bot)
    finally:
        cleanup.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup
        await queue.close()
        await bot.session.close()
