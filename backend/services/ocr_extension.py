"""OCR image/scanned-report extraction — opt-in extension point.

The existing parser architecture supports PDF/DOCX/XLSX/CSV/TXT well. Real OCR
(extracting text from scanned PDFs and images) requires an external engine such
as Tesseract (`pytesseract`) plus supporting system binaries, so it is intentionally
NOT auto-enabled: enabling it would add a heavy system dependency and, without those
dependencies present, silently degrade every upload.

This module provides a clean extension point so the feature can be wired up later
without re-architecting document ingestion:

    from services.ocr_extension import ocr_extract_text

    result = ocr_extract_text(filepath, extension)   # None when OCR is not available

When OCR is disabled or unavailable it returns ``None`` and records a warning —
it NEVER fabricates text or health observations.  No LLM is involved here, so no
AI output can be mistaken for a stored, verified medical fact.
"""

import logging
import os
from typing import Optional

from services.parsers import DocumentParseResult

logger = logging.getLogger(__name__)

# Image MIME types a future OCR parser would accept.
OCR_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}


def is_ocr_enabled() -> bool:
    """Whether OCR is opt-in. Disabled by default (avoids hard Tesseract dependency)."""
    return os.environ.get("OCR_ENABLED", "false").strip().lower() in {"1", "true", "yes"}


def is_ocr_available() -> bool:
    """True only when the OCR engine and its underlying binaries are importable."""
    if not is_ocr_enabled():
        return False
    try:
        import pytesseract  # noqa: F401  # optional hard dependency
        return True
    except ImportError:
        logger.warning("OCR_ENABLED=true but pytesseract is not installed; OCR disabled.")
        return False


def ocr_extract_text(filepath: str, extension: str) -> Optional[DocumentParseResult]:
    """Attempt OCR text extraction for an image file.

    Extension point for future OCR: return a DocumentParseResult on success, or
    ``None`` when OCR is not enabled/available/unsupported. Never fakes text.
    """
    if extension.lower() not in OCR_EXTENSIONS:
        return None
    if not is_ocr_available():
        return None
    try:
        import pytesseract
        from PIL import Image  # optional dependency

        text = pytesseract.image_to_string(Image.open(filepath))
        if not text or not text.strip():
            return None
        word_count = len(text.split())
        return DocumentParseResult(
            text=text,
            metadata={"model": "tesseract", "source": "ocr"},
            page_count=1,
            word_count=word_count or 0,
            warnings=[],
            parser_used="ocr_image_parser",
            processing_time_ms=0.0,
        )
    except Exception as exc:  # noqa: BLE001 - OCR must never break document ingestion
        logger.warning("OCR extraction failed for %s: %s", filepath, exc)
        return None