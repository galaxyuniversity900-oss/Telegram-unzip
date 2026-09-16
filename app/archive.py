from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from .security import validate_extracted_tree

SUPPORTED_EXTENSIONS = {
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".tbz2", ".txz"
}

MAGIC_SIGNATURES = (
    (b"PK\x03\x04", "zip"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
    (b"Rar!\x1a\x07\x00", "rar"),
    (b"Rar!\x1a\x07\x01\x00", "rar"),
    (b"\x1f\x8b", "gz"),
    (b"BZh", "bz2"),
    (b"\xfd7zXZ\x00", "xz"),
)


@dataclass(frozen=True)
class ArchiveInfo:
    kind: str
    compressed_bytes: int
    entries: int
    declared_uncompressed_bytes: int

    @property
    def ratio(self) -> float:
        if self.compressed_bytes <= 0:
            return 0.0
        return self.declared_uncompressed_bytes / self.compressed_bytes


def detect_archive(path: Path) -> str | None:
    suffixes = "".join(path.suffixes).lower()
    for compound, kind in ((".tar.gz", "tar.gz"), (".tar.bz2", "tar.bz2"), (".tar.xz", "tar.xz")):
        if suffixes.endswith(compound):
            return kind
    if path.suffix.lower() in SUPPORTED_EXTENSIONS:
        return path.suffix.lower().lstrip(".")
    with path.open("rb") as handle:
        header = handle.read(16)
    for signature, kind in MAGIC_SIGNATURES:
        if header.startswith(signature):
            return kind
    try:
        with path.open("rb") as handle:
            handle.seek(257)
            if handle.read(5) == b"ustar":
                return "tar"
    except OSError:
        pass
    return None


def _validate_member_name(name: str) -> None:
    # Reject traversal before extraction, because validating only after 7z writes
    # files is too late if a malicious member escapes the extraction directory.
    normalized = name.replace("\\", "/")
    if not normalized or "\x00" in normalized:
        raise ValueError("Archive contains an invalid member name.")
    if normalized.startswith("/") or normalized.startswith("//"):
        raise ValueError("Archive contains an absolute path.")
    if re.match(r"^[A-Za-z]:/", normalized):
        raise ValueError("Archive contains a Windows absolute path.")
    parts = PurePosixPath(normalized).parts
    if ".." in parts:
        raise ValueError("Archive path traversal detected.")
    win_parts = PureWindowsPath(normalized).parts
    if any(part == ".." for part in win_parts) or PureWindowsPath(normalized).is_absolute():
        raise ValueError("Archive path traversal detected.")


def _list_entries(path: Path) -> tuple[int, int]:
    """Read 7-Zip metadata and validate member names before any extraction occurs."""
    proc = subprocess.run(
        ["7z", "l", "-slt", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        raise ValueError("Archive cannot be inspected. It may be corrupt or password-protected.")
    entries = 0
    declared = 0
    current: dict[str, str] = {}
    for line in proc.stdout.splitlines() + [""]:
        if line.strip() == "":
            member = current.get("Path")
            if member:
                _validate_member_name(member)
                if current.get("Folder") != "+":
                    entries += 1
                    try:
                        declared += int(current.get("Size", "0"))
                    except ValueError as exc:
                        raise ValueError("Archive contains an invalid size field.") from exc
            current = {}
            continue
        if " = " in line:
            key, value = line.split(" = ", 1)
            current[key] = value
    return entries, declared


def inspect_archive(path: Path, max_files: int, max_bytes: int, max_ratio: int) -> ArchiveInfo:
    kind = detect_archive(path)
    if not kind:
        raise ValueError("Unsupported archive format. Supported: ZIP, RAR, 7Z, TAR, GZ, BZ2 and XZ.")
    compressed = path.stat().st_size
    if compressed <= 0:
        raise ValueError("The archive is empty.")
    entries, declared = _list_entries(path)
    if entries > max_files:
        raise ValueError("Archive contains too many files.")
    if declared > max_bytes:
        raise ValueError("Archive expands beyond the configured size limit.")
    if declared and declared / compressed > max_ratio:
        raise ValueError("Archive compression ratio exceeds the safety limit.")
    return ArchiveInfo(kind, compressed, entries, declared)


def extract_archive(path: Path, output: Path, max_files: int, max_bytes: int, max_ratio: int, timeout: int) -> ArchiveInfo:
    info = inspect_archive(path, max_files, max_bytes, max_ratio)
    output.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["7z", "x", "-y", "-bd", f"-o{output}", str(path)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        message = "Archive extraction failed."
        if "Wrong password" in proc.stderr or "password" in proc.stderr.lower():
            message = "This archive is password-protected. Password extraction will be added in a later release."
        raise ValueError(message)
    entries, total = validate_extracted_tree(output, max_files, max_bytes)
    if total > max_bytes or entries > max_files:
        raise ValueError("Extraction exceeded the configured safety limits.")
    return ArchiveInfo(info.kind, info.compressed_bytes, entries, total)


def iter_files(root: Path):
    yield from sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.as_posix().lower())


def format_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
