"""
Acadexis — Document Parser (Sprint 1, Step 1.1)
=================================================
Responsibility: Extract structured, page-annotated text from PDF files.

Design Decisions:
-----------------
1.  PyMuPDF (fitz) is used over pdfplumber / pdfminer because it is:
    - Dramatically faster on large academic PDFs
    - Gives precise page.number attribute (0-indexed internally; we +1 for humans)
    - Supports text ordering via sort=True (handles multi-column layouts)
    - Supports OCR fallback for scanned PDFs via page.get_textpage_ocr()

2.  We return a list[ParsedPage] dataclass rather than raw dicts.
    This gives downstream consumers (chunker.py) strong type safety and
    prevents the common bug of silently using wrong field names.

3.  We implement an OCR fallback:
    - Academic PDFs from old Nigerian universities are frequently scanned images.
    - If page.get_text() returns < 10 characters, we attempt OCR.
    - OCR is flagged with is_ocr=True so the chunker can attach a lower
      confidence metadata field (important for RAGAS evaluation in Sprint 7).

4.  We open the document once and yield pages as a generator — this is memory-
    efficient for 200-page textbooks without loading the whole file into RAM.

Known Limitations & Cautions (logged in lesson.txt):
------------------------------------------------------
- Scanned PDFs with complex multi-language content (e.g., Yoruba Unicode)
  may produce garbled text from the base OCR engine. Flag for manual review.
- Encrypted/password-protected PDFs: fitz.open() raises an exception.
  We catch this explicitly and raise PDFParseError with a clear user msg.
- PyMuPDF page.number is 0-indexed. We add +1 everywhere to get human-
  readable page numbers that match what the student sees in their PDF viewer.
  This is critical for the Source Badge citation system in Sprint 6.
"""

import fitz  # PyMuPDF
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class ParsedPage:
    """
    Represents one page extracted from a PDF document.

    Attributes:
        page_number:   1-indexed page number matching the visible PDF page.
        text:          Extracted plain text (may be OCR-derived; see is_ocr).
        filename:      Original filename for citation metadata.
        word_count:    Number of whitespace-separated tokens on the page.
        is_ocr:        True when text was obtained via fallback OCR.
                       Used downstream to set lower confidence in metadata.
        char_count:    Raw character count; used for quality filtering.
    """
    page_number: int
    text: str
    filename: str
    word_count: int = field(init=False)
    is_ocr: bool = False
    char_count: int = field(init=False)

    def __post_init__(self) -> None:
        # Compute derived fields after init — never call externally
        self.char_count = len(self.text)
        self.word_count = len(self.text.split())


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------

class PDFParseError(Exception):
    """
    Raised when a PDF cannot be parsed.

    Wraps fitz exceptions to decouple the API layer from PyMuPDF internals.
    The FastAPI endpoint catches this and returns HTTP 422.
    """
    pass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Pages with fewer characters than this threshold are treated as
# likely-scanned images and trigger OCR fallback.
_OCR_THRESHOLD_CHARS = 50

# Pages with fewer characters after OCR attempt are logged as warnings
# and skipped — they are probably blank / decorative pages.
_BLANK_PAGE_THRESHOLD_CHARS = 10


# ---------------------------------------------------------------------------
# Core Parsing Function
# ---------------------------------------------------------------------------

def parse_pdf(file_path: str | Path) -> list[ParsedPage]:
    """
    Parse a PDF file and return a list of ParsedPage objects, one per page.

    Args:
        file_path: Absolute path to the PDF file on disk.
                   Must be a file already saved to disk — not an UploadFile
                   object — because PyMuPDF reads from the filesystem.

    Returns:
        List of ParsedPage objects ordered by page_number (ascending).
        Empty pages (< 10 chars after OCR attempt) are excluded with a warning.

    Raises:
        PDFParseError: If the file is encrypted, corrupted, or not a valid PDF.
        FileNotFoundError: If file_path does not exist on disk.

    Performance Notes:
        - Opens the document ONCE and iterates in a single pass.
        - Uses page.get_text(flags=...) to strip formatting that would pollute
          chunking (e.g., ligatures, soft hyphens).
        - OCR is only triggered on pages below the char threshold — not globally.
          OCR is ~100x slower than native text extraction; we avoid it unless
          absolutely necessary.
    """
    file_path = Path(file_path)

    # Explicit existence check before fitz.open() to get a clean Python error
    if not file_path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    logger.info("Opening PDF: %s", file_path.name)

    try:
        doc = fitz.open(str(file_path))
    except fitz.FileDataError as exc:
        raise PDFParseError(
            f"'{file_path.name}' is corrupted or not a valid PDF: {exc}"
        ) from exc
    except fitz.FileNotFoundError as exc:
        raise FileNotFoundError(str(exc)) from exc
    except Exception as exc:
        if "password" in str(exc).lower() or "encrypted" in str(exc).lower():
            raise PDFParseError(
                f"'{file_path.name}' is password-protected. "
                "Please decrypt the PDF before uploading."
            ) from exc
        raise PDFParseError(f"Unexpected error opening PDF: {exc}") from exc

    if doc.is_encrypted:
        doc.close()
        raise PDFParseError(
            f"'{file_path.name}' is password-protected. "
            "Please decrypt the PDF before uploading."
        )

    pages: list[ParsedPage] = []
    filename = file_path.name

    try:
        with doc:
            total_pages = len(doc)
            logger.info("  → %d page(s) detected in '%s'", total_pages, filename)

            for page in doc:
                # page.number is 0-indexed; add 1 for human-readable numbering.
                human_page_num = page.number + 1

                # ---- Primary extraction ----------------------------------------
                # TEXT_PRESERVE_WHITESPACE: keeps paragraph structure
                # sort=True: reorder text blocks top-left to bottom-right,
                # which handles multi-column academic papers correctly.
                raw_text: str = page.get_text(
                    "text",
                    sort=True,
                    flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_DEHYPHENATE,
                ).strip()

                is_ocr = False

                # ---- OCR Fallback ----------------------------------------------
                if len(raw_text) < _OCR_THRESHOLD_CHARS:
                    logger.debug(
                        "  Page %d: Only %d chars from native extraction. "
                        "Attempting OCR fallback.",
                        human_page_num,
                        len(raw_text),
                    )
                    try:
                        ocr_textpage = page.get_textpage_ocr(flags=0, full=True)
                        ocr_text = page.get_text(textpage=ocr_textpage).strip()

                        if len(ocr_text) > len(raw_text):
                            raw_text = ocr_text
                            is_ocr = True
                            logger.debug(
                                "  Page %d: OCR produced %d chars.",
                                human_page_num,
                                len(raw_text),
                            )
                    except Exception as ocr_exc:
                        logger.warning(
                            "  Page %d: OCR fallback failed (%s).",
                            human_page_num,
                            ocr_exc,
                        )

                # ---- Blank Page Filter -----------------------------------------
                if len(raw_text) < _BLANK_PAGE_THRESHOLD_CHARS:
                    logger.debug(
                        "  Page %d: Skipping — appears blank (%d chars).",
                        human_page_num,
                        len(raw_text),
                    )
                    continue

                pages.append(
                    ParsedPage(
                        page_number=human_page_num,
                        text=raw_text,
                        filename=filename,
                        is_ocr=is_ocr,
                    )
                )

    except ValueError as exc:
        if "encrypted" in str(exc).lower():
            raise PDFParseError(
                f"'{filename}' is password-protected. "
                "Please decrypt the PDF before uploading."
            ) from exc
        raise PDFParseError(f"Value error parsing '{filename}': {exc}") from exc
    except Exception as exc:
        raise PDFParseError(f"Unexpected error parsing '{filename}': {exc}") from exc

    logger.info(
        "Parsed '%s': %d/%d pages with extractable text.",
        filename,
        len(pages),
        total_pages,
    )

    return pages
