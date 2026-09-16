from __future__ import annotations

import asyncio
import contextlib
import os
import re
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .archive import extract_archive, format_size, inspect_archive, iter_files
from .config import Settings
from .downloader import download_url
from .jobs import JobManager

settings = Settings.from_env()
bot = Bot(settings.telegram_bot_token)
dp = Dispatcher()
jobs = JobManager(
    settings.work_dir,
    settings.max_concurrent_jobs,
    settings.max_jobs_per_user,
    settings.job_ttl_seconds,
)

URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
PAGE_SIZE = 10


def safe_name(name: str) -> str:
    name = Path(name).name
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name) or "archive"


def archive_keyboard(job_id: str) -> InlineKeyboardMarkup:
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
    if page < total_pages:
        rows.append([InlineKeyboardButton(text="📤 Download this page", callback_data=f"d:{job_id}:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def process_archive(message: Message, archive: Path, job_root: Path, job_id: str) -> None:
    try:
        await message.answer("🔎 Inspecting archive before extraction…")
        info = await asyncio.to_thread(
            inspect_archive,
            archive,
            settings.max_files,
            settings.max_extracted_bytes,
            settings.max_ratio,
        )
        await message.answer(
            "📦 Archive detected\n\n"
            f"Format: {info.kind.upper()}\n"
            f"Compressed: {format_size(info.compressed_bytes)}\n"
            f"Entries: {info.entries:,}\n"
            f"Declared output: {format_size(info.declared_uncompressed_bytes)}\n"
            f"Ratio: {info.ratio:.1f}×\n\n"
            "🛡️ Safety checks passed. Extracting…"
        )
        output = job_root / "extracted"
        result = await asyncio.to_thread(
            extract_archive,
            archive,
            output,
            settings.max_files,
            settings.max_extracted_bytes,
            settings.max_ratio,
            settings.extraction_timeout_seconds,
        )
        files = list(iter_files(output))
        job = await jobs.get(job_id, message.from_user.id)
        if not job:
            raise ValueError("Job expired.")
        job.files = files
        pages = max(1, (len(files) + PAGE_SIZE - 1) // PAGE_SIZE)
        await message.answer(
            "✅ Extraction complete\n\n"
            f"📁 Files: {result.entries:,}\n"
            f"💾 Output: {format_size(result.declared_uncompressed_bytes)}\n"
            f"📄 Pages: {pages}\n\n"
            "The extracted workspace will be deleted automatically after the job TTL.",
            reply_markup=archive_keyboard(job_id),
        )
    except Exception as exc:
        await jobs.release(job_id)
        await message.answer(f"❌ {exc}")


async def start_job(message: Message, archive: Path, job_root: Path, job_id: str) -> None:
    async with jobs.semaphore:
        await process_archive(message, archive, job_root, job_id)


@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "👋 TuzsBot\n\n"
        "Send me a ZIP, RAR, 7Z, TAR/GZ/BZ2/XZ archive or a direct HTTP(S) archive URL.\n\n"
        "I inspect it, enforce safety limits, extract it, and let you browse/download the result."
    )


@dp.message(F.document)
async def document_handler(message: Message):
    if not message.document or not message.from_user:
        return
    if message.document.file_size and message.document.file_size > settings.max_download_bytes:
        await message.answer("❌ File exceeds the configured download limit.")
        return
    job, root = await jobs.create(message.from_user.id)
    if not job:
        await message.answer("⏳ You already have an active job. Please wait for it to finish or expire.")
        return
    archive = root / safe_name(message.document.file_name or "archive")
    try:
        await message.answer("⬇️ Downloading archive from Telegram…")
        await bot.download(message.document, destination=archive)
        await start_job(message, archive, root, job.job_id)
    except Exception as exc:
        await jobs.release(job.job_id)
        await message.answer(f"❌ {exc}")


@dp.message(F.text.regexp(URL_RE))
async def url_handler(message: Message):
    if not message.text or not message.from_user:
        return
    job, root = await jobs.create(message.from_user.id)
    if not job:
        await message.answer("⏳ You already have an active job. Please wait for it to finish or expire.")
        return
    try:
        await message.answer("⬇️ Downloading archive URL…")
        archive, size = await download_url(
            message.text.strip(), root, settings.max_download_bytes, settings.download_timeout_seconds
        )
        await message.answer(f"⬇️ Download complete: {format_size(size)}")
        await start_job(message, archive, root, job.job_id)
    except Exception as exc:
        await jobs.release(job.job_id)
        await message.answer(f"❌ {exc}")


@dp.callback_query(F.data.regexp(re.compile(r"^[bd]:[A-Za-z0-9_-]+:\d+$")))
async def job_callback(callback: CallbackQuery):
    if not callback.from_user or not callback.data:
        return
    action, job_id, raw_page = callback.data.split(":")
    page = int(raw_page)
    job = await jobs.get(job_id, callback.from_user.id)
    if not job:
        await callback.answer("This job has expired.", show_alert=True)
        return
    total_pages = max(1, (len(job.files) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, total_pages - 1)
    start = page * PAGE_SIZE
    selected = job.files[start : start + PAGE_SIZE]
    if action == "b":
        lines = [f"📂 Page {page + 1}/{total_pages}", ""]
        for index, path in enumerate(selected, start=start + 1):
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            lines.append(f"{index}. {path.relative_to(job.root / 'extracted').as_posix()} — {format_size(size)}")
        await callback.message.edit_text("\n".join(lines), reply_markup=browse_keyboard(job_id, page, total_pages))
        await callback.answer()
        return
    await callback.answer("Sending files…")
    for path in selected:
        if path.exists() and path.is_file():
            try:
                relative = path.relative_to(job.root / "extracted").as_posix()
                await callback.message.answer_document(FSInputFile(path), caption=relative[:900])
            except Exception as exc:
                await callback.message.answer(f"⚠️ Could not send `{path.name}`: {exc}")


@dp.message()
async def fallback(message: Message):
    await message.answer("Send an archive file or a direct HTTP(S) archive URL. Use /start for help.")


async def main() -> None:
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    cleanup_task = asyncio.create_task(jobs.cleanup_expired())
    try:
        await dp.start_polling(bot)
    finally:
        cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
