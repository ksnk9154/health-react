"""PDF parser using PyPDF2. Detects scanned PDFs (no extractable text)."""

import time
import logging
from ..parsers import BaseParser, DocumentParseResult, register_parser

logger = logging.getLogger(__name__)


def _fix_pua_encoded_text(text: str) -> str:
    """Decode Private-Use-Area glyphs that some PDFs use instead of real ASCII.

    Some PDFs (commonly produced by "Microsoft Print to PDF" or other printer
    drivers) embed fonts WITHOUT a proper ToUnicode CMap. PyPDF2's
    ``extract_text()`` then returns glyph codes that fall in the Unicode
    Private Use Area (U+E000–U+F8FF), where the LOW byte is the real ASCII
    code: e.g. U+F052 -> 'R', U+F065 -> 'e', U+F070 -> 'p' ... so
    ``\\uf052\\uf065\\uf070\\uf06f\\uf072\\uf074`` decodes to "Report".

    Without this decoding, the extracted text is unreadable garbage to an LLM,
    which hallucinates wildly unrelated summaries (device/prosthetic, "test",
    Trinity nuclear test, ...) for a clearly content-bearing document.

    Args:
        text: Raw text returned by the PDF extractor.

    Returns:
        Text with PUA-encoded printable-ASCII glyphs mapped to their real ASCII.
        Non-printable PUA code points are left untouched.
    """
    if not text:
        return text
    chars = []
    for ch in text:
        cp = ord(ch)
        if 0xE000 <= cp <= 0xF8FF:
            low = cp & 0x00FF
            if 0x20 <= low <= 0x7E:
                chars.append(chr(low))
                continue
        chars.append(ch)
    return "".join(chars)


# ---------------------------------------------------------------------------
# Layout-preserving extraction (keeps table columns aligned for the LLM)
# ---------------------------------------------------------------------------

# Rough average glyph width (points) at the default 10pt font used by most
# lab-report PDFs. Used to convert PDF x-coordinates to fixed-width columns.
_AVG_CHAR_WIDTH_PTS = 5.0
# Segments are on the same visual line when their y coordinates differ less
# than this (points).
_LINE_Y_TOLERANCE_PTS = 2.0


def _join_segments(segments: list) -> str:
    """Join (x, text) segments of one visual line into a fixed-width row.

    Each token is placed at character position ``round(x / 5.0)``. Because the
    mapping from PDF x-coordinate to character column is the SAME for every row,
    table columns align exactly across rows — the LLM (and the lab extractor)
        can reliably tell which column a number belongs to
    (Test Name | Results | Units | Bio. Ref. Interval).
    """
    if not segments:
        return ""
    # Place each token at column round(x / _AVG_CHAR_WIDTH_PTS) so that table
    # columns line up across rows. Tokens that are *close* (their column
    # overlaps text already written) cannot share the fixed-width grid without
    # overwriting each other -- in that case join them with a single space
    # instead, which keeps adjacent words in one cell (e.g. "GLUCOSE, FASTING")
    # from collapsing into a garbled blob.
    ordered = sorted(segments, key=lambda s: s[0])
    placements: list[tuple[int, str]] = []  # (start_col, text)
    cursor = 0
    for x, text in ordered:
        start = max(0, int(round(x / _AVG_CHAR_WIDTH_PTS)))
        if placements and start < cursor:
            # Close/colliding token -> single-space join after current text.
            start = cursor + 1
        placements.append((start, text))
        cursor = max(cursor, start + len(text))
    width = max(1, cursor)
    chars = [" "] * width
    for start, text in placements:
        for i, ch in enumerate(text):
            if start + i < width:
                chars[start + i] = ch
    return "".join(chars).strip()


def _extract_page_segment_lines(page) -> list:
    """Return the page's visual lines as a list of sorted (x, text) segments.

    Raises/returns empty list on error so callers can fall back to the default
    ``extract_text()``.
    """
    segments = []

    def visitor(text, cm, tm, font_dict, font_size):
        if not text:
            return
        # PyPDF2 often appends a trailing newline to every segment; it must
        # be removed or the row reconstruction breaks into separate lines.
        text = text.rstrip("\r\n")
        if not text.strip():
            return
        x = tm[4]
        y = tm[5]
        segments.append((y, x, text))

    page.extract_text(visitor_text=visitor)

    if not segments:
        return []

    # Sort top-to-bottom (PDF y grows upward), then left-to-right.
    segments.sort(key=lambda s: (-s[0], s[1]))

    lines = []
    current_y = None
    current_line = []
    for y, x, text in segments:
        if current_y is None or abs(y - current_y) > _LINE_Y_TOLERANCE_PTS:
            if current_line:
                lines.append(current_line)
            current_y = y
            current_line = [(x, text)]
        else:
            current_line.append((x, text))
    if current_line:
        lines.append(current_line)

    return lines


def _extract_page_with_layout(page) -> str:
    """Extract a page's text preserving the visual table layout.

    PyPDF2 3.x has no built-in ``extraction_mode="layout"`` (that is a pypdf 4
    feature), but its ``extract_text(visitor_text=...)`` callback provides the
    PDF text matrix with the x/y position of every text segment. We group
    segments by y-coordinate (visual row) and sort by x-coordinate (column), so
    table cells that share a row stay on the same line instead of being
    flattened into one long unaligned string.

    Falls back to the default ``extract_text()`` on any error.
    """
    try:
        lines = _extract_page_segment_lines(page)
        if not lines:
            return page.extract_text()
        return "\n".join(_join_segments(line) for line in lines)
    except Exception:
        return page.extract_text()


class PDFParser(BaseParser):
    extension = ".pdf"
    display_name = "PDF Parser"

    def _import_library(self):
        from PyPDF2 import PdfReader  # noqa: F401

    def validate(self, filepath: str) -> list[str]:
        warnings = []
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(filepath)
            if len(reader.pages) > 500:
                warnings.append(
                    f"PDF has {len(reader.pages)} pages. Processing may be slow."
                )
        except Exception as e:
            warnings.append(f"Could not validate PDF structure: {e}")
        return warnings

    def extract_metadata(self, filepath: str) -> dict:
        from PyPDF2 import PdfReader
        reader = PdfReader(filepath)
        meta = reader.metadata
        return {
            "pages": len(reader.pages),
            "author": str(meta.author) if meta and meta.author else None,
            "producer": str(meta.producer) if meta and meta.producer else None,
            "title": str(meta.title) if meta and meta.title else None,
        }

    def parse(self, filepath: str) -> DocumentParseResult:
        start = time.time()
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(filepath)
            text_parts = []
            for page in reader.pages:
                page_text = _extract_page_with_layout(page)
                if page_text:
                    text_parts.append(page_text.strip())

            full_text = "\n\n".join(text_parts)
            # Decode PUA-encoded glyphs (0xF000|ASCII) so the text the LLM
            # receives is real, readable characters — not Private Use Area
            # codepoints that caused wildly inaccurate summaries.
            full_text = _fix_pua_encoded_text(full_text)
            word_count = len(full_text.split())
            elapsed = (time.time() - start) * 1000

            # Detect scanned PDF: no extractable text but has pages
            if word_count < 10 and len(reader.pages) > 0:
                logger.info("Scanned PDF detected: %s (%d pages)", filepath, len(reader.pages))
                return DocumentParseResult(
                    text="",
                    metadata={"pages": len(reader.pages)},
                    page_count=len(reader.pages),
                    word_count=0,
                    warnings=[
                        "Scanned document detected. "
                        "OCR support will be added in the Vision phase."
                    ],
                    parser_used="pdf_parser",
                    processing_time_ms=round(elapsed, 2),
                )

            logger.debug(
                "Parsed PDF: %s (%d pages, %d words, %.0fms)",
                filepath, len(reader.pages), word_count, elapsed,
            )
            return DocumentParseResult(
                text=full_text,
                metadata=self.extract_metadata(filepath),
                page_count=len(reader.pages),
                word_count=word_count,
                warnings=[],
                parser_used="pdf_parser",
                processing_time_ms=round(elapsed, 2),
            )

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            logger.error("PDF parsing failed for %s: %s", filepath, e)
            return DocumentParseResult(
                text="",
                metadata={},
                page_count=0,
                word_count=0,
                warnings=[f"PDF parsing failed: {e}"],
                parser_used="pdf_parser",
                processing_time_ms=round(elapsed, 2),
            )


register_parser(PDFParser())