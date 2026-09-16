from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable

from .archive import _validate_member_name, detect_archive
from .security import validate_extracted_tree


@dataclass(frozen=True)
class ArchiveMember:
    name: str
    size: int
    is_directory: bool


@dataclass(frozen=True)
class StagedResult:
    batches: int
    entries: int
    bytes_written: int


def list_archive_members(path: Path) -> list[ArchiveMember]:
    """Return validated archive members in deterministic 7-Zip listing order."""
    proc = subprocess.run(
        ["7z", "l", "-slt", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        raise ValueError("Archive cannot be inspected. It may be corrupt or password-protected.")

    result: list[ArchiveMember] = []
    current: dict[str, str] = {}
    for line in proc.stdout.splitlines() + [""]:
        if not line.strip():
            name = current.get("Path")
            # 7-Zip's first metadata block describes the container itself.
            if name and "Type" not in current and "Physical Size" not in current:
                _validate_member_name(name)
                directory = current.get("Folder") == "+"
                try:
                    size = int(current.get("Size", "0"))
                except ValueError as exc:
                    raise ValueError("Archive contains an invalid size field.") from exc
                result.append(ArchiveMember(name=name, size=max(0, size), is_directory=directory))
            current = {}
            continue
        if " = " in line:
            key, value = line.split(" = ", 1)
            current[key] = value
    return result


def _safe_member_target(root: Path, member: str) -> Path:
    normalized = member.replace("\\", "/")
    candidate = (root / PurePosixPath(normalized)).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("Archive member escapes the extraction directory.") from exc
    if PureWindowsPath(normalized).is_absolute():
        raise ValueError("Archive contains an absolute Windows path.")
    return candidate


def extract_archive_staged(
    archive: Path,
    output: Path,
    max_files: int,
    max_bytes: int,
    max_ratio: int,
    timeout: int,
    batch_size: int = 100,
    progress: Callable[[int, int, int, int], None] | None = None,
    password: str | None = None,
) -> StagedResult:
    """Extract in deterministic batches, keeping each completed stage usable."""
    if batch_size < 1 or batch_size > 1000:
        raise ValueError("batch_size must be between 1 and 1000")
    kind = detect_archive(archive)
    if not kind:
        raise ValueError("Unsupported archive format.")
    compressed = archive.stat().st_size
    if compressed <= 0:
        raise ValueError("The archive is empty.")

    members = list_archive_members(archive)
    files = [m for m in members if not m.is_directory]
    declared = sum(m.size for m in files)
    if len(files) > max_files:
        raise ValueError("Archive contains too many files.")
    if declared > max_bytes:
        raise ValueError("Archive expands beyond the configured size limit.")
    if declared and declared / compressed > max_ratio:
        raise ValueError("Archive compression ratio exceeds the safety limit.")

    output.mkdir(parents=True, exist_ok=True)
    total_batches = max(1, (len(files) + batch_size - 1) // batch_size)
    completed = 0
    bytes_written = 0

    for batch_no, offset in enumerate(range(0, len(files), batch_size), start=1):
        batch = files[offset : offset + batch_size]
        command = ["7z", "x", "-y", "-bd", f"-o{output}"]
        if password is not None:
            command.append(f"-p{password}")
        command.extend([str(archive), *[m.name for m in batch]])
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        if proc.returncode != 0:
            if "password" in (proc.stderr + proc.stdout).lower():
                raise ValueError(f"Batch {batch_no}/{total_batches} needs a valid archive password.")
            raise ValueError(f"Staged extraction failed at batch {batch_no}/{total_batches}.")

        _, actual_bytes = validate_extracted_tree(output, max_files, max_bytes)
        completed += len(batch)
        bytes_written = actual_bytes
        if progress:
            progress(batch_no, total_batches, completed, bytes_written)

    if not files and progress:
        progress(1, 1, 0, 0)
    return StagedResult(total_batches, completed, bytes_written)
