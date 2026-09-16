from pathlib import Path

from app.archive import detect_archive, format_size


def test_detect_archive_by_extension(tmp_path: Path):
    for name, expected in {
        "a.zip": "zip",
        "a.tar.gz": "tar.gz",
        "a.tgz": "tgz",
        "a.7z": "7z",
    }.items():
        path = tmp_path / name
        path.write_bytes(b"not-an-archive")
        assert detect_archive(path) == expected


def test_detect_zip_by_magic(tmp_path: Path):
    path = tmp_path / "download"
    path.write_bytes(b"PK\x03\x04" + b"x")
    assert detect_archive(path) == "zip"


def test_format_size():
    assert format_size(1024) == "1.0 KB"
    assert format_size(1024 * 1024) == "1.0 MB"
