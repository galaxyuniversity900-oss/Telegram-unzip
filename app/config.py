from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}")
    return value


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    max_download_bytes: int
    max_extracted_bytes: int
    max_files: int
    max_ratio: int
    max_archive_depth: int
    extraction_timeout_seconds: int
    download_timeout_seconds: int
    max_concurrent_jobs: int
    max_jobs_per_user: int
    job_ttl_seconds: int
    extraction_batch_size: int
    extraction_progress_seconds: int
    work_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
        return cls(
            telegram_bot_token=token,
            max_download_bytes=env_int("MAX_DOWNLOAD_MB", 200),
            max_extracted_bytes=env_int("MAX_EXTRACTED_MB", 500),
            max_files=env_int("MAX_FILES", 5000),
            max_ratio=env_int("MAX_RATIO", 100),
            max_archive_depth=env_int("MAX_ARCHIVE_DEPTH", 2),
            extraction_timeout_seconds=env_int("EXTRACTION_TIMEOUT_SECONDS", 180),
            download_timeout_seconds=env_int("DOWNLOAD_TIMEOUT_SECONDS", 60),
            max_concurrent_jobs=env_int("MAX_CONCURRENT_JOBS", 2),
            max_jobs_per_user=env_int("MAX_JOBS_PER_USER", 1),
            job_ttl_seconds=env_int("JOB_TTL_SECONDS", 900),
            extraction_batch_size=env_int("EXTRACTION_BATCH_SIZE", 100),
            extraction_progress_seconds=env_int("EXTRACTION_PROGRESS_SECONDS", 5),
            work_dir=Path(os.getenv("WORK_DIR", "/tmp/tuzsbot")).expanduser(),
        )
