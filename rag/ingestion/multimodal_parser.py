"""
Acadexis — Multimodal Parser (Sprint 8)
========================================
Responsibility: Extract images from PDF pages alongside their surrounding
textual context, producing MultimodalPage objects ready for coherent chunking.

Architecture:
-------------
This module EXTENDS the Sprint 1 parser rather than replacing it.
  - `parse_pdf()` (parser.py)         → text extraction only (unchanged)
  - `extract_multimodal_pages()`      → text + embedded images with context

Why PyMuPDF for image extraction (not Unstructured.io):
  - PyMuPDF is already our PDF dependency (zero new installs)
  - `page.get_images()` + `page.get_image_rects()` gives exact bounding boxes
  - `page.get_text("dict")` gives full block layout for proximity detection
  - Unstructured.io requires a separate service/Docker container — JIT principle

Image Format Handling:
  - JPEG / PNG / BMP / GIF  → passed directly (JPEG as image/jpeg, rest as PNG)
  - JPEG2000 / JBIG2        → rendered to PNG via PyMuPDF pixmap (Gemini does
                              not support these formats natively)
  - Images smaller than MIN_PX on any dimension → skipped (decorative noise)

Surrounding Text Algorithm:
  - For each image, compute its vertical centre (y_mid) on the page
  - Scan all text blocks from page.get_text("dict")
  - Collect text blocks whose bottom edge is within CONTEXT_CHARS_PROXIMITY px
    above the image top, or whose top edge is within the same distance below
  - Join as a single string, truncate to configured character limit
  - This text + image bytes form one multimodal semantic unit

Security:
  - Image bytes are validated to be non-empty before inclusion
  - No image bytes are stored in Pinecone metadata — only the flag + format
  - Memory: extracted images are not cached; bytes are used once then GC'd

Known Limitations:
  - PDFs with vector graphics (SVG-like paths) rather than raster images will
    NOT have images extracted. These are rare in academic PDFs.
  - Very large images (>10MB raw bytes) are truncated to avoid OOM.
    The Gemini API has a practical per-request payload limit.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from rag.ingestion.parser import ParsedPage, PDFParseError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Formats Gemini Embedding 2 natively accepts
_SUPPORTED_MIME_TYPES = {"jpeg", "jpg", "png"}

# Formats requiring PyMuPDF pixmap re-render to PNG
_NEEDS_RENDER_EXTS = {"jp2", "jpx", "jb2", "jbig2", "bmp", "gif", "tiff", "tif"}

# Maximum raw image bytes to pass to Gemini (prevent OOM on huge scanned images)
_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10MB

# Vertical proximity in PDF points (1pt = 1/72 inch) to search for
# surrounding text blocks. 72pt = 1 inch — generous for academic layouts.
_CONTEXT_VERTICAL_PROXIMITY_PT = 72


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class PageImage:
    """
    A single image extracted from a PDF page, with positional context.

    Attributes:
        xref:             PyMuPDF cross-reference ID of the image object.
        image_bytes:      Raw image bytes (PNG or JPEG format only).
        mime_type:        MIME type string for Gemini API ('image/png' or
                          'image/jpeg'). Always one of these two values.
        bbox:             Bounding box as (x0, y0, x1, y1) in PDF points.
                          y0 is the TOP of the image (PDF coordinate origin is
                          bottom-left, but PyMuPDF uses top-left convention
                          after applying the page's transformation matrix).
        surrounding_text: Text from blocks immediately above/below the image,
                          truncated to `context_chars` characters.
                          Empty string if no adjacent text found.
        width_px:         Original image width in pixels.
        height_px:        Original image height in pixels.
        page_number:      1-indexed page number where image was found.
    """
    xref: int
    image_bytes: bytes
    mime_type: str
    bbox: tuple[float, float, float, float]   # (x0, y0, x1, y1)
    surrounding_text: str
    width_px: int
    height_px: int
    page_number: int


@dataclass
class MultimodalPage:
    """
    Extended ParsedPage that also carries images extracted from the page.

    Attributes:
        parsed_page: The underlying ParsedPage (text extraction result).
        images:      List of PageImage objects found on this page.
                     Empty list if the page has no qualifying images.
    """
    parsed_page: ParsedPage
    images: list[PageImage] = field(default_factory=list)

    # Convenience proxies to the underlying ParsedPage fields
    @property
    def page_number(self) -> int:
        return self.parsed_page.page_number

    @property
    def text(self) -> str:
        return self.parsed_page.text

    @property
    def filename(self) -> str:
        return self.parsed_page.filename

    @property
    def is_ocr(self) -> bool:
        return self.parsed_page.is_ocr

    @property
    def has_images(self) -> bool:
        return len(self.images) > 0


# ---------------------------------------------------------------------------
# Core Extraction Function
# ---------------------------------------------------------------------------

def extract_multimodal_pages(
    file_path: str | Path,
    parsed_pages: list[ParsedPage],
    min_image_px: int = 50,
    context_chars: int = 400,
) -> list[MultimodalPage]:
    """
    Enrich already-parsed pages with image data extracted via PyMuPDF.

    This function runs AFTER `parse_pdf()` in the ingestion pipeline.
    It re-opens the document to access the visual layout (which parse_pdf
    discards), extracts qualifying images from each page, and returns
    MultimodalPage objects that bundle text + images together.

    Args:
        file_path:    Path to the original PDF file (must still exist on disk).
        parsed_pages: Output of ingestion.parser.parse_pdf().
                      Only pages present here will be processed.
        min_image_px: Minimum dimension (w or h) to consider an image
                      substantive. Default 50px filters decorative noise.
        context_chars: Maximum characters of surrounding text to include
                       with each image. Default 400 ≈ 2-3 paragraphs.

    Returns:
        List of MultimodalPage objects, one per parsed page, in page_number
        order. Pages with no qualifying images have `images=[]`.

    Raises:
        PDFParseError: If the document cannot be re-opened.
        FileNotFoundError: If file_path no longer exists.

    Design Note:
        We accept pre-parsed pages rather than re-parsing text here to avoid
        duplicate work. The PDF is opened twice total (once in parse_pdf,
        once here), but image data is inaccessible from ParsedPage objects.
        This is an acceptable trade-off: image extraction is fast (no OCR).
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"PDF file not found for multimodal extraction: {file_path}")

    if not parsed_pages:
        logger.debug("extract_multimodal_pages: no parsed pages provided, returning empty.")
        return []

    # Build a lookup: page_number (1-indexed) → ParsedPage
    page_lookup: dict[int, ParsedPage] = {p.page_number: p for p in parsed_pages}

    logger.info(
        "Multimodal extraction: opening '%s' for image scan (%d pages).",
        file_path.name,
        len(parsed_pages),
    )

    try:
        doc = fitz.open(str(file_path))
    except Exception as exc:
        raise PDFParseError(
            f"Could not re-open '{file_path.name}' for image extraction: {exc}"
        ) from exc

    multimodal_pages: list[MultimodalPage] = []
    total_images_found = 0
    total_images_skipped = 0

    try:
        with doc:
            for page in doc:
                human_page_num = page.number + 1

                # Only process pages that successfully parsed text
                if human_page_num not in page_lookup:
                    continue

                parsed_page = page_lookup[human_page_num]
                images = _extract_page_images(
                    page=page,
                    doc=doc,
                    human_page_num=human_page_num,
                    min_image_px=min_image_px,
                    context_chars=context_chars,
                )

                total_images_found += len(images)
                if not images:
                    total_images_skipped += len(page.get_images(full=False))

                multimodal_pages.append(
                    MultimodalPage(parsed_page=parsed_page, images=images)
                )

    except PDFParseError:
        raise
    except Exception as exc:
        raise PDFParseError(
            f"Unexpected error during image extraction from '{file_path.name}': {exc}"
        ) from exc

    logger.info(
        "Multimodal extraction complete: %d qualifying image(s) extracted from '%s' "
        "(%d page(s) processed).",
        total_images_found,
        file_path.name,
        len(multimodal_pages),
    )

    return multimodal_pages


# ---------------------------------------------------------------------------
# Per-Page Image Extraction
# ---------------------------------------------------------------------------

def _extract_page_images(
    page: fitz.Page,
    doc: fitz.Document,
    human_page_num: int,
    min_image_px: int,
    context_chars: int,
) -> list[PageImage]:
    """
    Extract all qualifying images from a single PDF page.

    Returns a list of PageImage objects. Returns empty list if the page
    has no images, or all images are below the size threshold.
    """
    image_list = page.get_images(full=True)
    if not image_list:
        return []

    # Get full block layout for surrounding text detection.
    # We fetch this once per page (not per image) for efficiency.
    page_dict: dict[str, Any] = page.get_text("dict", sort=True)
    text_blocks = _extract_text_blocks(page_dict)

    page_images: list[PageImage] = []

    for img_info in image_list:
        xref = img_info[0]

        # --- Get bounding box(es) for this image ---
        rects = page.get_image_rects(xref)
        if not rects:
            logger.debug(
                "  Page %d, xref %d: No display rect found, skipping.",
                human_page_num, xref,
            )
            continue

        # Use the first rect (most images appear once per page)
        rect = rects[0]
        bbox = (rect.x0, rect.y0, rect.x1, rect.y1)

        # --- Extract raw image data ---
        try:
            image_data = doc.extract_image(xref)
        except Exception as exc:
            logger.warning(
                "  Page %d, xref %d: extract_image failed (%s), skipping.",
                human_page_num, xref, exc,
            )
            continue

        if not image_data or not image_data.get("image"):
            logger.debug(
                "  Page %d, xref %d: Empty image data, skipping.",
                human_page_num, xref,
            )
            continue

        width_px = image_data.get("width", 0)
        height_px = image_data.get("height", 0)
        ext = image_data.get("ext", "png").lower()

        # --- Size filter: skip decorative noise ---
        if width_px < min_image_px or height_px < min_image_px:
            logger.debug(
                "  Page %d, xref %d: Skipping small image (%dx%d px < %dpx threshold).",
                human_page_num, xref, width_px, height_px, min_image_px,
            )
            continue

        # --- Normalise image bytes + MIME type ---
        image_bytes, mime_type = _normalise_image(
            image_data=image_data,
            ext=ext,
            page=page,
            rect=rect,
            xref=xref,
            human_page_num=human_page_num,
        )

        if image_bytes is None:
            continue

        # --- Size guard: prevent OOM on enormous scanned images ---
        if len(image_bytes) > _MAX_IMAGE_BYTES:
            logger.warning(
                "  Page %d, xref %d: Image too large (%d bytes > %d limit). "
                "Re-rendering at reduced resolution.",
                human_page_num, xref, len(image_bytes), _MAX_IMAGE_BYTES,
            )
            image_bytes = _render_region_to_png(page, rect, dpi=72)
            if image_bytes is None or len(image_bytes) > _MAX_IMAGE_BYTES:
                logger.warning(
                    "  Page %d, xref %d: Still too large after re-render. Skipping.",
                    human_page_num, xref,
                )
                continue
            mime_type = "image/png"

        # --- Surrounding text extraction ---
        surrounding_text = _get_surrounding_text(
            text_blocks=text_blocks,
            image_rect=rect,
            context_chars=context_chars,
        )

        page_images.append(PageImage(
            xref=xref,
            image_bytes=image_bytes,
            mime_type=mime_type,
            bbox=bbox,
            surrounding_text=surrounding_text,
            width_px=width_px,
            height_px=height_px,
            page_number=human_page_num,
        ))

        logger.debug(
            "  Page %d, xref %d: Extracted %dx%d image (%s, %d bytes). "
            "Context: %d chars.",
            human_page_num, xref, width_px, height_px,
            mime_type, len(image_bytes), len(surrounding_text),
        )

    return page_images


# ---------------------------------------------------------------------------
# Image Normalisation
# ---------------------------------------------------------------------------

def _normalise_image(
    image_data: dict[str, Any],
    ext: str,
    page: fitz.Page,
    rect: fitz.Rect,
    xref: int,
    human_page_num: int,
) -> tuple[bytes | None, str]:
    """
    Convert extracted image data to a Gemini-compatible format.

    Returns:
        (image_bytes, mime_type) where mime_type is 'image/png' or 'image/jpeg'.
        Returns (None, '') if normalisation fails.

    Gemini Embedding 2 supports: image/png, image/jpeg, image/gif, image/webp.
    We normalise everything to PNG or JPEG for predictability.
    """
    raw_bytes: bytes = image_data["image"]

    if ext in ("jpeg", "jpg"):
        # Native JPEG — pass directly
        return raw_bytes, "image/jpeg"

    if ext == "png":
        # Native PNG — pass directly
        return raw_bytes, "image/png"

    if ext in _NEEDS_RENDER_EXTS:
        # Unsupported format — render the page region to PNG via pixmap
        logger.debug(
            "  Page %d, xref %d: Format '%s' unsupported by Gemini; "
            "re-rendering region to PNG.",
            human_page_num, xref, ext,
        )
        rendered = _render_region_to_png(page, rect, dpi=150)
        if rendered is None:
            logger.warning(
                "  Page %d, xref %d: Re-render failed. Skipping.",
                human_page_num, xref,
            )
            return None, ""
        return rendered, "image/png"

    # Unknown extension — attempt to treat as PNG first, fallback to render
    try:
        # If PyMuPDF produced valid bytes, trust it as PNG
        if raw_bytes[:4] == b"\x89PNG":
            return raw_bytes, "image/png"
        if raw_bytes[:2] in (b"\xff\xd8", b"\xff\xe0", b"\xff\xe1"):
            return raw_bytes, "image/jpeg"
    except Exception:
        pass

    # Last resort: render the region
    logger.debug(
        "  Page %d, xref %d: Unknown ext '%s'; falling back to region render.",
        human_page_num, xref, ext,
    )
    rendered = _render_region_to_png(page, rect, dpi=150)
    if rendered is None:
        return None, ""
    return rendered, "image/png"


def _render_region_to_png(
    page: fitz.Page,
    rect: fitz.Rect,
    dpi: int = 150,
) -> bytes | None:
    """
    Render a rectangular region of a PDF page to PNG bytes via pixmap.

    Used as a fallback for unsupported image formats (JPEG2000, JBIG2, etc.)
    and for oversized images that need resolution reduction.

    Args:
        page: The PDF page object.
        rect: The bounding rectangle to render.
        dpi:  Resolution in dots per inch. 150 DPI balances quality vs. size.

    Returns:
        PNG bytes, or None if rendering fails.
    """
    try:
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        clip = fitz.Rect(rect)
        pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
        return pix.tobytes("png")
    except Exception as exc:
        logger.warning("Region render failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Surrounding Text Detection
# ---------------------------------------------------------------------------

def _extract_text_blocks(
    page_dict: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Extract text blocks from a page.get_text("dict") result.

    Returns a list of dicts with keys: 'text', 'bbox' (x0, y0, x1, y1).
    Block type 0 = text, type 1 = image. We filter to text only.
    """
    blocks = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:  # 0 = text block
            continue
        lines = block.get("lines", [])
        block_text = " ".join(
            span.get("text", "")
            for line in lines
            for span in line.get("spans", [])
        ).strip()
        if not block_text:
            continue
        bbox = block.get("bbox", (0, 0, 0, 0))
        blocks.append({"text": block_text, "bbox": bbox})
    return blocks


def _get_surrounding_text(
    text_blocks: list[dict[str, Any]],
    image_rect: fitz.Rect,
    context_chars: int,
) -> str:
    """
    Find text blocks immediately above and below an image and concatenate them.

    Algorithm:
      1. Compute image vertical centre (y_mid) in PDF points.
      2. For each text block, compute its bottom edge (y1) and top edge (y0).
      3. "Above" = block.y1 is within CONTEXT_VERTICAL_PROXIMITY_PT above
         image.y0  (i.e., image_rect.y0 - PROX < block.y1 <= image_rect.y0)
      4. "Below" = block.y0 is within CONTEXT_VERTICAL_PROXIMITY_PT below
         image.y1  (i.e., image_rect.y1 <= block.y0 < image_rect.y1 + PROX)
      5. Sort above blocks by proximity (closest first), take as many as fit
         within context_chars. Same for below.
      6. Return: [above_text] + " [IMAGE] " + [below_text], truncated.

    Args:
        text_blocks: Output of _extract_text_blocks().
        image_rect:  PyMuPDF Rect of the image on the page.
        context_chars: Max total characters in output.

    Returns:
        Combined context string. "[IMAGE]" sentinel marks image position.
        Empty string if no nearby text found.
    """
    img_y0 = image_rect.y0
    img_y1 = image_rect.y1
    prox = _CONTEXT_VERTICAL_PROXIMITY_PT

    above_blocks: list[tuple[float, str]] = []  # (distance, text)
    below_blocks: list[tuple[float, str]] = []

    for block in text_blocks:
        bx0, by0, bx1, by1 = block["bbox"]
        text = block["text"]

        # Above: block bottom (by1) is above the image top (img_y0)
        if by1 <= img_y0 and (img_y0 - by1) <= prox:
            distance = img_y0 - by1   # smaller = closer
            above_blocks.append((distance, text))

        # Below: block top (by0) is below the image bottom (img_y1)
        elif by0 >= img_y1 and (by0 - img_y1) <= prox:
            distance = by0 - img_y1
            below_blocks.append((distance, text))

    if not above_blocks and not below_blocks:
        return ""

    # Sort: closest first
    above_blocks.sort(key=lambda x: x[0])
    below_blocks.sort(key=lambda x: x[0])

    half_budget = context_chars // 2

    # Build above text (closest → furthest, then reversed to read top-down)
    above_text = ""
    for _, text in reversed(above_blocks):
        candidate = (above_text + " " + text).strip() if above_text else text
        if len(candidate) <= half_budget:
            above_text = candidate
        else:
            # Include as much as fits
            remaining = half_budget - len(above_text)
            if remaining > 20:
                above_text = (above_text + " " + text[:remaining]).strip()
            break

    # Build below text (closest → furthest)
    below_text = ""
    for _, text in below_blocks:
        candidate = (below_text + " " + text).strip() if below_text else text
        if len(candidate) <= half_budget:
            below_text = candidate
        else:
            remaining = half_budget - len(below_text)
            if remaining > 20:
                below_text = (below_text + " " + text[:remaining]).strip()
            break

    # Assemble: above text, image sentinel, below text
    parts = []
    if above_text:
        parts.append(above_text)
    parts.append("[IMAGE]")
    if below_text:
        parts.append(below_text)

    result = " ".join(parts)

    # Final safety truncation
    return result[:context_chars]
