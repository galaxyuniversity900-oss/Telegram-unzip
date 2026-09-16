import asyncio
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.types import FSInputFile, Message
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
MAX_DOWNLOAD = int(os.getenv("MAX_DOWNLOAD_MB", "200")) * 1024 * 1024
MAX_EXTRACTED = int(os.getenv("MAX_EXTRACTED_MB", "500")) * 1024 * 1024
MAX_FILES = int(os.getenv("MAX_FILES", "5000"))
MAX_RATIO = int(os.getenv("MAX_RATIO", "100"))
WORK_ROOT = Path(os.getenv("WORK_DIR", "/tmp/tuzsbot"))

bot = Bot(TOKEN)
dp = Dispatcher()


def safe_name(name: str) -> str:
    name = Path(name).name
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name) or "archive"


def archive_kind(path: Path) -> str | None:
    suffixes = ''.join(path.suffixes).lower()
    if suffixes.endswith(".tar.gz") or suffixes.endswith(".tgz"):
        return "tar.gz"
    if suffixes.endswith(".tar.bz2") or suffixes.endswith(".tbz2"):
        return "tar.bz2"
    if suffixes.endswith(".tar.xz") or suffixes.endswith(".txz"):
        return "tar.xz"
    if path.suffix.lower() in {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"}:
        return path.suffix.lower()[1:]
    return None


def validate_members(extract_dir: Path) -> tuple[int, int]:
    total_size = 0
    count = 0
    root = extract_dir.resolve()
    for item in extract_dir.rglob("*"):
        count += 1
        if count > MAX_FILES:
            raise ValueError("Too many extracted files.")
        resolved = item.resolve()
        if root != resolved and root not in resolved.parents:
            raise ValueError("Unsafe archive path detected.")
        if item.is_symlink():
            raise ValueError("Symlinks are not allowed in extracted archives.")
        if item.is_file():
            total_size += item.stat().st_size
            if total_size > MAX_EXTRACTED:
                raise ValueError("Extracted data exceeds the configured limit.")
    return count, total_size


def extract_archive(archive: Path, out: Path) -> tuple[int, int]:
    kind = archive_kind(archive)
    if not kind:
        raise ValueError("Unsupported archive format.")
    if archive.stat().st_size * MAX_RATIO < 1:
        raise ValueError("Invalid archive size.")
    out.mkdir(parents=True, exist_ok=True)
    # 7z provides one extraction interface for ZIP/RAR/7Z/TAR and common compressed formats.
    proc = subprocess.run(
        ["7z", "x", "-y", f"-o{out}", str(archive)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        raise ValueError("Archive extraction failed. The archive may be corrupt or password-protected.")
    return validate_members(out)


async def download_url(url: str, destination: Path) -> int:
    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            length = response.headers.get("content-length")
            if length and int(length) > MAX_DOWNLOAD:
                raise ValueError("Download exceeds the configured limit.")
            total = 0
            with destination.open("wb") as f:
                async for chunk in response.aiter_bytes(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_DOWNLOAD:
                        raise ValueError("Download exceeds the configured limit.")
                    f.write(chunk)
            return total


async def process(message: Message, archive: Path):
    job = Path(tempfile.mkdtemp(prefix="job-", dir=WORK_ROOT))
    try:
        await message.answer("🔎 Analyzing archive…")
        out = job / "extracted"
        count, size = await asyncio.to_thread(extract_archive, archive, out)
        await message.answer(f"✅ Extracted successfully\n\n📁 Files: {count}\n💾 Size: {size / 1024 / 1024:.1f} MB")
        files = [p for p in out.rglob("*") if p.is_file()]
        for path in files:
            await message.answer_document(FSInputFile(path), caption=path.relative_to(out).as_posix()[:900])
    except Exception as exc:
        await message.answer(f"❌ {exc}")
    finally:
        shutil.rmtree(job, ignore_errors=True)


@dp.message(F.document)
async def document_handler(message: Message):
    if not message.document:
        return
    if message.document.file_size and message.document.file_size > MAX_DOWNLOAD:
        await message.answer("❌ File exceeds the configured size limit.")
        return
    job = Path(tempfile.mkdtemp(prefix="job-", dir=WORK_ROOT))
    archive = job / safe_name(message.document.file_name or "archive")
    try:
        await message.answer("⬇️ Downloading…")
        await bot.download(message.document, destination=archive)
        await process(message, archive)
    except Exception as exc:
        shutil.rmtree(job, ignore_errors=True)
        await message.answer(f"❌ {exc}")


@dp.message(F.text.regexp(r"^https?://"))
async def url_handler(message: Message):
    job = Path(tempfile.mkdtemp(prefix="job-", dir=WORK_ROOT))
    archive = job / "downloaded_archive"
    try:
        await message.answer("⬇️ Downloading URL…")
        await download_url(message.text.strip(), archive)
        await process(message, archive)
    except Exception as exc:
        shutil.rmtree(job, ignore_errors=True)
        await message.answer(f"❌ {exc}")


@dp.message()
async def fallback(message: Message):
    await message.answer("Send an archive file or a direct HTTP(S) download link.")


async def main():
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
