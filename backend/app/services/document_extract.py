"""Text extraction for PDFs and images, with Groq Vision OCR as the scan fallback."""

from __future__ import annotations

import io
import logging
from pathlib import Path

import pymupdf
from pydantic import ValidationError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.config import get_settings
from app.llm.groq_client import LLMError, LLMOutputError, complete_vision_json
from app.schemas.analysis import SourceDocument, VisionOcrResult

logger = logging.getLogger(__name__)

MIN_USABLE_PAGE_CHARS = 20
OCR_REVIEW_WARNING = "Groq Vision OCR was used — please verify the extracted details."
SUPPORTED_IMAGE_SUFFIXES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
SUPPORTED_MEDIA_TYPES = {"application/pdf", *SUPPORTED_IMAGE_SUFFIXES.values()}


class DocumentExtractionError(ValueError):
    """The attachment itself is invalid or unsupported."""


class VisionOcrUnavailableError(RuntimeError):
    """The attachment is valid but the hosted vision model could not read it."""


def _render_page(page: pymupdf.Page) -> bytes:
    """Render a page to a bounded JPEG suitable for Groq's image input."""
    settings = get_settings()
    longest_points = max(page.rect.width, page.rect.height)
    scale = min(160 / 72, settings.vision_image_max_edge / max(longest_points, 1))
    matrix = pymupdf.Matrix(scale, scale)
    pixmap = page.get_pixmap(matrix=matrix, colorspace=pymupdf.csRGB, alpha=False)
    return pixmap.tobytes("jpeg", jpg_quality=84)


def _vision_transcribe(images: list[bytes], page_numbers: list[int]) -> dict[int, str]:
    prompt = (
        "You are an OCR transcription service for pharmaceutical complaint documents. "
        "Transcribe every visible word faithfully, preserving reading order. Do not summarize, "
        "interpret, correct, or invent text. The images correspond in order to page numbers "
        f"{page_numbers}. Return JSON exactly as "
        '{"pages":[{"page_number":1,"text":"verbatim text"}]}.'
    )
    try:
        raw = complete_vision_json(prompt, images)
        result = VisionOcrResult.model_validate(raw)
    except (LLMError, LLMOutputError, ValidationError) as exc:
        logger.warning("Vision OCR failed: %s", type(exc).__name__)
        raise VisionOcrUnavailableError(
            "Groq Vision could not read this attachment. Retry it or type the complaint."
        ) from exc

    expected = set(page_numbers)
    transcriptions = {
        page.page_number: page.text.strip()
        for page in result.pages
        if page.page_number in expected and page.text.strip()
    }
    if not transcriptions:
        raise VisionOcrUnavailableError(
            "Groq Vision did not find readable text. Type the complaint instead."
        )
    return transcriptions


def _extract_pdf(data: bytes, filename: str) -> tuple[SourceDocument, list[str]]:
    try:
        reader = PdfReader(io.BytesIO(data))
    except (PdfReadError, OSError, ValueError) as exc:
        raise DocumentExtractionError("The uploaded file could not be read as a PDF.") from exc

    if reader.is_encrypted:
        try:
            if reader.decrypt("") == 0:
                raise DocumentExtractionError(
                    "The PDF is password protected and cannot be read."
                )
        except DocumentExtractionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DocumentExtractionError(
                "The PDF is password protected and cannot be read."
            ) from exc

    native_pages: dict[int, str] = {}
    scan_pages: list[int] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:  # noqa: BLE001 - one unreadable page can still be OCRed
            text = ""
        if len(text) >= MIN_USABLE_PAGE_CHARS:
            native_pages[index] = text
        else:
            scan_pages.append(index)

    warnings: list[str] = []
    ocr_pages = scan_pages[: get_settings().max_ocr_pages]
    if len(scan_pages) > len(ocr_pages):
        warnings.append(
            f"Only the first {get_settings().max_ocr_pages} scanned pages were OCR processed; "
            f"{len(scan_pages) - len(ocr_pages)} additional scanned page(s) were skipped."
        )

    vision_pages: dict[int, str] = {}
    if ocr_pages:
        try:
            document = pymupdf.open(stream=data, filetype="pdf")
            images = [_render_page(document[number - 1]) for number in ocr_pages]
        except Exception as exc:  # noqa: BLE001
            raise DocumentExtractionError("The PDF pages could not be rendered for OCR.") from exc
        _check_vision_payload(images)
        vision_pages = _vision_transcribe(images, ocr_pages)
        warnings.append(OCR_REVIEW_WARNING)

    all_pages = []
    for number in range(1, len(reader.pages) + 1):
        text = native_pages.get(number) or vision_pages.get(number)
        if text:
            all_pages.append(f"[Page {number}]\n{text}")
    combined = "\n\n".join(all_pages).strip()
    if not combined:
        raise VisionOcrUnavailableError(
            "No readable text was found in the PDF. Retry it or type the complaint."
        )

    if native_pages and vision_pages:
        method = "mixed"
    elif vision_pages:
        method = "groq_vision"
    else:
        method = "native_text"
    return (
        SourceDocument(
            filename=filename,
            media_type="application/pdf",
            extraction_method=method,
            text=combined,
            page_count=max(len(reader.pages), 1),
            ocr_used=bool(vision_pages),
        ),
        warnings,
    )


def _check_vision_payload(images: list[bytes]) -> None:
    # Base64 grows by roughly one third; leave headroom under Groq's 20 MB request cap.
    encoded_bytes = sum(((len(image) + 2) // 3) * 4 for image in images)
    if encoded_bytes > get_settings().max_vision_payload_mb * 1024 * 1024:
        raise DocumentExtractionError(
            "The rendered document is too large for vision OCR. Upload fewer or clearer pages."
        )


def _extract_image(data: bytes, filename: str, media_type: str) -> tuple[SourceDocument, list[str]]:
    suffix = Path(filename).suffix.lower()
    filetype = "jpeg" if suffix in {".jpg", ".jpeg"} else "png"
    try:
        document = pymupdf.open(stream=data, filetype=filetype)
        if document.page_count != 1:
            raise DocumentExtractionError("The uploaded image could not be decoded.")
        image = _render_page(document[0])
    except DocumentExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise DocumentExtractionError("The uploaded image could not be decoded.") from exc

    _check_vision_payload([image])
    transcribed = _vision_transcribe([image], [1]).get(1, "")
    return (
        SourceDocument(
            filename=filename,
            media_type=media_type,
            extraction_method="groq_vision",
            text=transcribed,
            page_count=1,
            ocr_used=True,
        ),
        [OCR_REVIEW_WARNING],
    )


def extract_document(
    data: bytes, filename: str, content_type: str | None
) -> tuple[SourceDocument, list[str]]:
    """Extract one supported attachment, invoking Groq Vision only where needed."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(data, filename)
    if suffix in SUPPORTED_IMAGE_SUFFIXES:
        return _extract_image(
            data,
            filename,
            SUPPORTED_IMAGE_SUFFIXES[suffix],
        )
    raise DocumentExtractionError(
        "Only PDF, PNG, JPG, and JPEG complaint attachments are supported."
    )
