"""上传入口安全：路径隔离、扩展名/MIME 白名单、流式大小限额、隔离区落盘。

P0-0：禁止用客户端原始文件名直接拼接路径；落盘使用服务端 UUID 文件名。
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException, UploadFile

from agents.doc_parser_agent import DocParserAgent
from config import settings

logger = logging.getLogger(__name__)

# 展示名允许的字符（不含路径分隔符）
_SAFE_DISPLAY_NAME = re.compile(r"^[\w\u4e00-\u9fff\s.\-()（）【】\[\]_+]+$", re.UNICODE)

# 魔数 → 扩展名集合（宽松匹配；文本类靠扩展名+内容嗅探）
_MAGIC_RULES: list[tuple[bytes, set[str]]] = [
    (b"%PDF", {".pdf"}),
    (b"\x89PNG\r\n\x1a\n", {".png"}),
    (b"\xff\xd8\xff", {".jpg", ".jpeg"}),
    (b"PK\x03\x04", {".xlsx", ".xls"}),  # zip-based office；xls 旧格式另判
]


@dataclass
class SavedUpload:
    """安全落盘结果。"""

    stored_path: str  # 绝对规范化路径（入库/doc_id 用）
    display_name: str  # 客户端原名（仅展示）
    extension: str
    size_bytes: int
    content_type_declared: str
    quarantine_path: str | None = None


class UploadSecurityError(HTTPException):
    """上传安全校验失败 → 4xx。"""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(status_code=status_code, detail=detail)


def upload_root() -> Path:
    root = Path(settings.upload_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def quarantine_root() -> Path:
    q = (upload_root() / "_quarantine").resolve()
    q.mkdir(parents=True, exist_ok=True)
    # 确保隔离区仍在 upload_root 内
    if not _is_relative_to(q, upload_root()):
        raise UploadSecurityError(500, "Quarantine directory escapes upload root")
    return q


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def sanitize_display_name(filename: str | None) -> str:
    raw = (filename or "").strip() or "unnamed"
    # 去掉任何路径成分，只保留 basename
    name = Path(raw.replace("\\", "/")).name
    if not name or name in {".", ".."}:
        name = "unnamed"
    if not _SAFE_DISPLAY_NAME.match(name):
        # 保留扩展名，主体替换
        ext = Path(name).suffix.lower()
        stem = "upload"
        name = f"{stem}{ext}" if ext else stem
    # 限制长度
    if len(name) > 180:
        ext = Path(name).suffix.lower()[:20]
        name = name[: 180 - len(ext)] + ext
    return name


def assert_allowed_extension(display_name: str) -> str:
    ext = Path(display_name).suffix.lower()
    allowed = set(DocParserAgent.SUPPORTED_EXTENSIONS.keys())
    # 兼容前端常见额外类型：若未在解析器中支持则拒绝（安全优先）
    if ext not in allowed:
        raise UploadSecurityError(
            400,
            f"File extension '{ext or '(none)'}' is not allowed. "
            f"Allowed: {', '.join(sorted(allowed))}",
        )
    return ext


def _sniff_header(header: bytes, ext: str) -> None:
    """魔数与扩展名交叉校验；纯文本类允许无强魔数。"""
    text_like = {".txt", ".md", ".csv"}
    if ext in text_like:
        # 拒绝明显的二进制可执行头
        if header.startswith((b"\x7fELF", b"MZ", b"\x00\x00\x01\x00")):
            raise UploadSecurityError(400, "File content does not match declared text type")
        return

    matched = False
    for magic, exts in _MAGIC_RULES:
        if header.startswith(magic):
            matched = True
            if ext not in exts:
                # xls 老格式 D0 CF 11 E0
                if ext == ".xls" and header.startswith(b"\xd0\xcf\x11\xe0"):
                    return
                raise UploadSecurityError(
                    400,
                    f"File magic does not match extension '{ext}' (possible MIME spoofing)",
                )
            return
    if ext == ".xls" and header.startswith(b"\xd0\xcf\x11\xe0"):
        return
    if not matched and ext not in text_like:
        # 未识别魔数：对图片/PDF 视为可疑
        if ext in {".pdf", ".png", ".jpg", ".jpeg"}:
            raise UploadSecurityError(400, f"Unrecognized file signature for '{ext}'")


def _check_pdf_pages(path: Path) -> None:
    max_pages = int(settings.upload_max_pdf_pages)
    if max_pages <= 0:
        return
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(str(path))
        n = len(reader.pages)
    except Exception as exc:
        logger.warning("PDF page count failed path=%s err=%s", path, exc)
        raise UploadSecurityError(400, "Invalid or unreadable PDF") from exc
    if n > max_pages:
        raise UploadSecurityError(
            400,
            f"PDF has {n} pages; maximum allowed is {max_pages}",
        )


def _optional_antivirus_scan(path: Path) -> None:
    """可选 ClamAV；未启用或未安装时跳过（可配置强制）。"""
    if not settings.upload_av_scan_enabled:
        return
    clam = shutil.which("clamscan") or shutil.which("clamdscan")
    if not clam:
        if settings.upload_av_scan_required:
            raise UploadSecurityError(503, "Antivirus scanner required but not installed")
        logger.warning("AV scan enabled but clamscan not found; skipping")
        return
    try:
        proc = subprocess.run(
            [clam, "--no-summary", str(path)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise UploadSecurityError(408, "Antivirus scan timed out") from exc
    # clamscan: 0 clean, 1 infected, 2 error
    if proc.returncode == 1:
        raise UploadSecurityError(400, "File rejected by antivirus scan")
    if proc.returncode not in (0,):
        if settings.upload_av_scan_required:
            raise UploadSecurityError(503, f"Antivirus scan failed: {proc.stderr[:200]}")
        logger.warning("AV scan non-zero rc=%s stderr=%s", proc.returncode, (proc.stderr or "")[:200])


def _stream_to_file(src: BinaryIO, dest: Path, max_bytes: int) -> int:
    written = 0
    chunk_size = 1024 * 64
    with dest.open("wb") as out:
        while True:
            chunk = src.read(chunk_size)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                out.close()
                dest.unlink(missing_ok=True)
                raise UploadSecurityError(
                    413,
                    f"File exceeds maximum size of {max_bytes} bytes",
                )
            out.write(chunk)
    return written


def save_upload_securely(file: UploadFile) -> SavedUpload:
    """校验并安全保存上传文件；返回隔离区晋升后的最终路径。"""
    display_name = sanitize_display_name(file.filename)
    ext = assert_allowed_extension(display_name)
    max_bytes = int(settings.upload_max_bytes)
    if max_bytes <= 0:
        raise UploadSecurityError(500, "UPLOAD_MAX_BYTES misconfigured")

    # 先读一小段做魔数检测（UploadFile 可 seek 的 SpooledTemporaryFile）
    header = file.file.read(16)
    file.file.seek(0)
    _sniff_header(header, ext)

    declared = (file.content_type or "").split(";")[0].strip().lower()
    # 粗粒度 content-type 检查（浏览器常不准，只拦明显矛盾）
    if declared:
        if ext == ".pdf" and declared not in {"application/pdf", "application/octet-stream"}:
            raise UploadSecurityError(400, f"Content-Type '{declared}' incompatible with .pdf")
        if ext in {".png", ".jpg", ".jpeg"} and not (
            declared.startswith("image/") or declared == "application/octet-stream"
        ):
            raise UploadSecurityError(400, f"Content-Type '{declared}' incompatible with image")

    root = upload_root()
    qroot = quarantine_root()
    token = uuid.uuid4().hex
    q_name = f"{token}{ext}"
    q_path = (qroot / q_name).resolve()
    if not _is_relative_to(q_path, root):
        raise UploadSecurityError(500, "Resolved quarantine path escapes upload root")

    try:
        size = _stream_to_file(file.file, q_path, max_bytes)
    except UploadSecurityError:
        raise
    except Exception as exc:
        q_path.unlink(missing_ok=True)
        logger.exception("upload write failed")
        raise UploadSecurityError(400, f"Failed to store upload: {exc}") from exc

    if size == 0:
        q_path.unlink(missing_ok=True)
        raise UploadSecurityError(400, "Empty file rejected")

    # 再读落盘文件头复核
    with q_path.open("rb") as fh:
        _sniff_header(fh.read(16), ext)

    if ext == ".pdf":
        _check_pdf_pages(q_path)

    _optional_antivirus_scan(q_path)

    # 晋升到正式目录（仍用 UUID，不使用客户端路径）
    final_name = f"{token}{ext}"
    final_path = (root / final_name).resolve()
    if not _is_relative_to(final_path, root):
        q_path.unlink(missing_ok=True)
        raise UploadSecurityError(500, "Resolved final path escapes upload root")

    # 同名并发：UUID 几乎不撞；若存在则换名
    if final_path.exists():
        final_name = f"{uuid.uuid4().hex}{ext}"
        final_path = (root / final_name).resolve()

    shutil.move(str(q_path), str(final_path))
    stored = DocParserAgent.normalize_path(str(final_path))
    # 最终再确认仍在 root 内
    if not _is_relative_to(Path(stored), root):
        Path(stored).unlink(missing_ok=True)
        raise UploadSecurityError(500, "Normalized path escapes upload root")

    logger.info(
        "upload_saved display=%s stored=%s size=%s declared_type=%s",
        display_name,
        stored,
        size,
        declared,
    )
    return SavedUpload(
        stored_path=stored,
        display_name=display_name,
        extension=ext,
        size_bytes=size,
        content_type_declared=declared,
        quarantine_path=str(q_path),
    )
