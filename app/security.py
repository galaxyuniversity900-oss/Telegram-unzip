from __future__ import annotations

import os
from pathlib import Path


def is_within(root: Path, candidate: Path) -> bool:
    root = root.resolve()
    try:
        candidate.resolve().relative_to(root)
        return True
    except ValueError:
        return False


def validate_extracted_tree(root: Path, max_files: int, max_bytes: int) -> tuple[int, int]:
    """Validate the materialized extraction tree and return (entries, file_bytes)."""
    root = root.resolve()
    entries = 0
    total = 0
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirs[:] = [d for d in dirs if not (current_path / d).is_symlink()]
        for name in dirs + files:
            path = current_path / name
            entries += 1
            if entries > max_files:
                raise ValueError("Archive contains too many extracted entries.")
            if path.is_symlink():
                raise ValueError("Symlinks are not allowed in extracted archives.")
            if not is_within(root, path):
                raise ValueError("Unsafe archive path detected.")
            if path.is_file():
                total += path.stat().st_size
                if total > max_bytes:
                    raise ValueError("Extracted data exceeds the configured limit.")
    return entries, total
