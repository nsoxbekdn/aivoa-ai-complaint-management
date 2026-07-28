"""Document extraction tests. Vision calls are mocked; no test reaches Groq."""

from __future__ import annotations

import pymupdf
import pytest

from app.services import document_extract
from app.services.document_extract import (
    DocumentExtractionError,
    VisionOcrUnavailableError,
    extract_document,
)


def _text_pdf(text: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 100), text, fontsize=12)
    return document.tobytes()


def _complaint_png() -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=900, height=1200)
    page.insert_text(
        (70, 100),
        "Complaint: five ClearCough bottles leaked. Batch CC26045.",
        fontsize=20,
    )
    return page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False).tobytes("png")


def _scanned_pdf(page_count: int = 1) -> bytes:
    image = _complaint_png()
    document = pymupdf.open()
    for _ in range(page_count):
        page = document.new_page(width=900, height=1200)
        page.insert_image(page.rect, stream=image)
    return document.tobytes()


def test_native_pdf_bypasses_vision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        document_extract,
        "complete_vision_json",
        lambda *_args, **_kwargs: pytest.fail("vision must not run for native text"),
    )

    source, warnings = extract_document(
        _text_pdf("Native complaint text for batch NATIVE-42 and leaking bottles."),
        "native.pdf",
        "application/pdf",
    )

    assert source.extraction_method == "native_text"
    assert source.ocr_used is False
    assert "NATIVE-42" in source.text
    assert warnings == []


def test_scanned_pdf_invokes_groq_vision(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_vision(_prompt: str, images: list[bytes], **_kwargs) -> dict:
        calls.append(len(images))
        return {"pages": [{"page_number": 1, "text": "Five leaking bottles, batch CC26045."}]}

    monkeypatch.setattr(document_extract, "complete_vision_json", fake_vision)
    source, warnings = extract_document(_scanned_pdf(), "scan.pdf", "application/pdf")

    assert calls == [1]
    assert source.extraction_method == "groq_vision"
    assert source.ocr_used is True
    assert "CC26045" in source.text
    assert any("verify" in warning.lower() for warning in warnings)


@pytest.mark.parametrize(
    ("filename", "media_type"),
    [("complaint.png", "image/png"), ("complaint.jpg", "image/jpeg")],
)
def test_png_and_jpg_invoke_vision(
    filename: str,
    media_type: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        document_extract,
        "complete_vision_json",
        lambda *_args, **_kwargs: {
            "pages": [{"page_number": 1, "text": "Image complaint transcription."}]
        },
    )

    source, _warnings = extract_document(_complaint_png(), filename, media_type)

    assert source.ocr_used is True
    assert source.media_type == media_type


def test_mixed_pdf_combines_native_and_ocr_pages_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = _complaint_png()
    document = pymupdf.open()
    first = document.new_page(width=900, height=1200)
    first.insert_text((70, 100), "Native first-page complaint text for batch MIX-100.", fontsize=18)
    second = document.new_page(width=900, height=1200)
    second.insert_image(second.rect, stream=image)
    monkeypatch.setattr(
        document_extract,
        "complete_vision_json",
        lambda *_args, **_kwargs: {
            "pages": [{"page_number": 2, "text": "OCR second-page observations."}]
        },
    )

    source, _warnings = extract_document(document.tobytes(), "mixed.pdf", "application/pdf")

    assert source.extraction_method == "mixed"
    assert source.text.index("[Page 1]") < source.text.index("[Page 2]")
    assert "OCR second-page" in source.text


def test_more_than_three_scanned_pages_has_explicit_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_counts: list[int] = []

    def fake_vision(_prompt: str, images: list[bytes], **_kwargs) -> dict:
        image_counts.append(len(images))
        return {
            "pages": [
                {"page_number": page, "text": f"OCR page {page}"} for page in (1, 2, 3)
            ]
        }

    monkeypatch.setattr(
        document_extract,
        "complete_vision_json",
        fake_vision,
    )

    source, warnings = extract_document(_scanned_pdf(4), "four-pages.pdf", "application/pdf")

    assert image_counts == [3]
    assert source.page_count == 4
    assert any("skipped" in warning.lower() for warning in warnings)
    assert "[Page 4]" not in source.text


def test_rendered_vision_payload_limit_is_checked_after_base64_growth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        document_extract.get_settings(),
        "max_vision_payload_mb",
        1,
        raising=False,
    )

    with pytest.raises(DocumentExtractionError, match="too large"):
        document_extract._check_vision_payload([b"x" * 800_000])


def test_malformed_or_empty_vision_json_fails_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        document_extract,
        "complete_vision_json",
        lambda *_args, **_kwargs: {"unexpected": "shape"},
    )

    with pytest.raises(VisionOcrUnavailableError, match="did not find readable text"):
        extract_document(_complaint_png(), "scan.png", "image/png")


def test_corrupt_pdf_fails_clearly() -> None:
    with pytest.raises(DocumentExtractionError, match="could not be read"):
        extract_document(b"not a PDF", "broken.pdf", "application/pdf")
