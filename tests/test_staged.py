from pathlib import Path

import pytest

from app.staged import _safe_member_target, list_archive_members


def test_safe_member_target_rejects_traversal(tmp_path: Path):
    root = tmp_path / "out"
    root.mkdir()
    with pytest.raises(ValueError):
        _safe_member_target(root, "../../outside.txt")
    with pytest.raises(ValueError):
        _safe_member_target(root, "/absolute.txt")
    with pytest.raises(ValueError):
        _safe_member_target(root, "C:/absolute.txt")


def test_safe_member_target_accepts_nested_paths(tmp_path: Path):
    root = tmp_path / "out"
    root.mkdir()
    target = _safe_member_target(root, "part-001/docs/report.pdf")
    assert target == (root / "part-001/docs/report.pdf").resolve()
