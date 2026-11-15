import io

import pytest

from src import pdf_service
from src.errors import ApiError

fitz = pytest.importorskip("fitz")


def make_pdf(pages=1, text_pages=None, password=None):
    doc = fitz.open()
    text_pages = text_pages or ["题目 第 1 页"] * pages
    for text in text_pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    kwargs = {}
    if password:
        kwargs = {"encryption": fitz.PDF_ENCRYPT_AES_256, "owner_pw": password, "user_pw": password}
    return doc.tobytes(**kwargs)


def assert_code(fn, code):
    with pytest.raises(ApiError) as exc:
        fn()
    assert exc.value.code == code


def test_text_pdf_preserves_page_numbers_and_blank_pages():
    result = pdf_service.process_pdf(make_pdf(text_pages=["第一个题目", "", "第二个题目"]))
    assert result["page_count"] == 3
    assert [p["page"] for p in result["page_results"]] == [1, 2, 3]
    assert "[第 1 页]" in result["text"]
    assert "[第 3 页]" in result["text"]
    assert result["failed_pages"] == []


def test_corrupt_empty_and_too_many_pages_have_stable_codes():
    assert_code(lambda: pdf_service.validate_pdf(b""), "PDF_EMPTY")
    assert_code(lambda: pdf_service.validate_pdf(b"%PDF-not-valid"), "PDF_CORRUPT")
    assert_code(lambda: pdf_service.validate_pdf(make_pdf(pdf_service.MAX_PDF_PAGES + 1)), "PDF_TOO_MANY_PAGES")


def test_encrypted_pdf_is_rejected():
    assert_code(lambda: pdf_service.validate_pdf(make_pdf(password="secret")), "PDF_ENCRYPTED")
