from pathlib import Path

import pytest

from app.security import is_within, validate_extracted_tree


def test_is_within_rejects_escape(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    assert is_within(root, root / "nested" / "file.txt")
    assert not is_within(root, tmp_path / "outside.txt")


def test_validate_tree_counts_files_and_bytes(tmp_path: Path):
    root = tmp_path / "extract"
    root.mkdir()
    (root / "a.txt").write_text("hello")
    (root / "b.txt").write_text("world")
    assert validate_extracted_tree(root, 10, 100) == (2, 10)


def test_validate_tree_rejects_too_many_entries(tmp_path: Path):
    root = tmp_path / "extract"
    root.mkdir()
    for i in range(3):
        (root / f"{i}.txt").write_text("x")
    with pytest.raises(ValueError, match="too many"):
        validate_extracted_tree(root, 2, 100)


def test_validate_tree_rejects_too_many_bytes(tmp_path: Path):
    root = tmp_path / "extract"
    root.mkdir()
    (root / "big.bin").write_bytes(b"x" * 20)
    with pytest.raises(ValueError, match="size"):
        validate_extracted_tree(root, 10, 10)
