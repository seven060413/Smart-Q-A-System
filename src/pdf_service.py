"""Bounded PDF extraction and OCR helpers."""

from __future__ import annotations

import json
import threading
import time

from .errors import ApiError
from .ocr import get_ocr_adapter

MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_RENDER_DPI = 120
MAX_TOTAL_PIXELS = 80_000_000
MAX_PROCESS_SECONDS = 90
MAX_ACTIVE_DOCUMENTS = 2
MAX_PAGE_TEXT = 4000
_slots = threading.BoundedSemaphore(MAX_ACTIVE_DOCUMENTS)


def _error(status: int, code: str, message: str) -> ApiError:
    return ApiError(status, code, message)


def validate_pdf(data: bytes):
    if not data:
        raise _error(400, "PDF_EMPTY", "PDF 文件为空")
    if len(data) > MAX_PDF_BYTES:
        raise _error(413, "PDF_TOO_LARGE", "PDF 文件不能超过 20 MB")
    try:
        import fitz
    except ModuleNotFoundError:
        raise _error(503, "PDF_DEPENDENCY_MISSING", "PDF 处理依赖未安装，请联系管理员") from None
    if not data.startswith(b"%PDF-"):
        raise _error(400, "PDF_CORRUPT", "PDF 文件损坏或格式无效")
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        if doc.needs_pass:
            doc.close()
            raise _error(422, "PDF_ENCRYPTED", "暂不支持加密 PDF，请先解除密码保护")
        count = doc.page_count
        if count < 1:
            doc.close()
            raise _error(422, "PDF_EMPTY_DOCUMENT", "PDF 不包含页面")
        if count > MAX_PDF_PAGES:
            doc.close()
            raise _error(413, "PDF_TOO_MANY_PAGES", "PDF 最多支持 100 页")
        # Reject pathological page boxes before rendering.
        pixels = 0
        scale = MAX_RENDER_DPI / 72
        for page in doc:
            pixels += int(page.rect.width * scale) * int(page.rect.height * scale)
            if pixels > MAX_TOTAL_PIXELS:
                doc.close()
                raise _error(413, "PDF_PIXEL_LIMIT", "PDF 页面总像素超过处理限制")
        return doc, count
    except ApiError:
        raise
    except Exception:
        raise _error(400, "PDF_CORRUPT", "PDF 文件损坏或格式无效") from None


def _page_text(page) -> str:
    try:
        return (page.get_text("text") or "").strip()[:MAX_PAGE_TEXT]
    except Exception:
        return ""


def process_pdf(data: bytes) -> dict:
    if not _slots.acquire(blocking=False):
        raise _error(429, "PDF_BUSY", "PDF 处理人数已满，请稍后重试")
    started = time.monotonic()
    try:
        doc, count = validate_pdf(data)
    except Exception:
        _slots.release()
        raise
    pages = []
    failures = []
    try:
        for index, page in enumerate(doc):
            if time.monotonic() - started > MAX_PROCESS_SECONDS:
                failures.extend(range(index + 1, count + 1))
                break
            try:
                text = _page_text(page)
                if len("".join(text.split())) < 12:
                    pix = page.get_pixmap(dpi=MAX_RENDER_DPI, alpha=False)
                    if pix.width * pix.height > MAX_TOTAL_PIXELS:
                        raise RuntimeError("page pixel limit")
                    if pix.samples and max(pix.samples) - min(pix.samples) > 8:
                        result = get_ocr_adapter().recognize(pix.tobytes("png"), "image/png")
                        text = (result.text or "").strip()[:MAX_PAGE_TEXT]
                    if text:
                        pages.append({"page": index + 1, "text": text})
                    else:
                        pages.append({"page": index + 1, "text": ""})
                else:
                    pages.append({"page": index + 1, "text": text})
            except Exception:
                failures.append(index + 1)
        combined = "\n".join(f"[第 {item['page']} 页]\n{item['text']}" for item in pages if item["text"])
        return {
            "page_count": count,
            "page_results": pages,
            "failed_pages": failures,
            "text": combined[:MAX_PDF_PAGES * MAX_PAGE_TEXT],
            "status": "completed" if not failures else ("partial" if combined else "failed"),
            "error_code": "PDF_PAGE_PARTIAL_FAILURE" if failures and combined else ("PDF_PAGE_PROCESSING_FAILED" if failures else None),
        }
    finally:
        doc.close()
        _slots.release()


def page_results_json(result: dict) -> str:
    return json.dumps(result["page_results"], ensure_ascii=False)
