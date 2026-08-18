"""P0-0: 上传路径隔离、扩展名/MIME、大小限额。"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi import UploadFile

from config import settings
from services.upload_security import (
    UploadSecurityError,
    sanitize_display_name,
    save_upload_securely,
    upload_root,
)


class _FakeUpload(UploadFile):
    def __init__(self, filename: str, data: bytes, content_type: str = "application/octet-stream"):
        super().__init__(file=io.BytesIO(data), filename=filename, headers=None)
        self._content_type = content_type

    @property
    def content_type(self) -> str | None:
        return self._content_type


def test_sanitize_strips_path_traversal():
    assert sanitize_display_name("../../etc/passwd") == "passwd"
    assert "/" not in sanitize_display_name("a/b/c.txt")
    assert "\\" not in sanitize_display_name("a\\b\\c.md")
    name = sanitize_display_name("/abs/../evil.pdf")
    assert name.endswith(".pdf")
    assert ".." not in name


def test_reject_disallowed_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "upload_max_bytes", 1024)
    with pytest.raises(UploadSecurityError) as ei:
        save_upload_securely(_FakeUpload("malware.exe", b"MZ\x90\x00fake"))
    assert ei.value.status_code == 400


def test_reject_oversized(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "upload_max_bytes", 64)
    with pytest.raises(UploadSecurityError) as ei:
        save_upload_securely(_FakeUpload("big.txt", b"x" * 200, "text/plain"))
    assert ei.value.status_code == 413


def test_reject_pdf_magic_spoof(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "upload_max_bytes", 10_000)
    # 扩展名 .pdf 但内容不是 PDF
    with pytest.raises(UploadSecurityError) as ei:
        save_upload_securely(
            _FakeUpload("fake.pdf", b"not-a-pdf-file!!!!", "application/pdf")
        )
    assert ei.value.status_code == 400


def test_safe_save_uses_uuid_under_upload_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "upload_max_bytes", 10_000)
    monkeypatch.setattr(settings, "upload_av_scan_enabled", False)

    # 恶意文件名不应写出 root 外
    saved = save_upload_securely(
        _FakeUpload("../../etc/passwd.md", b"# hello knowledge\n", "text/markdown")
    )
    root = upload_root()
    stored = Path(saved.stored_path).resolve()
    assert stored.is_relative_to(root)
    assert saved.display_name == "passwd.md"
    assert stored.name != "passwd.md"  # UUID 存储名
    assert stored.suffix == ".md"
    assert stored.read_text(encoding="utf-8").startswith("# hello")


def test_absolute_client_name_stays_inside_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "upload_max_bytes", 10_000)
    saved = save_upload_securely(
        _FakeUpload("/tmp/abs_escape.txt", b"content-ok", "text/plain")
    )
    assert Path(saved.stored_path).resolve().is_relative_to(upload_root())
    assert saved.display_name == "abs_escape.txt"


def test_empty_file_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "upload_max_bytes", 10_000)
    with pytest.raises(UploadSecurityError) as ei:
        save_upload_securely(_FakeUpload("empty.txt", b"", "text/plain"))
    assert ei.value.status_code == 400
