"""
Acadexis — Semantic Chunker (Sprint 1 + Sprint 8)
=================================================
Responsibility: Split ParsedPage text into semantically coherent chunks
while preserving and enriching citation metadata for every chunk.

Design Decisions:
-----------------
1.  RecursiveCharacterTextSplitter is chosen over TokenTextSplitter because:
    - It respects natural document structure (paragraphs → sentences → words)
    - It does NOT require a tokenizer dependency (no tiktoken for Gemini)
    - It produces stable chunk boundaries regardless of LLM tokenizer changes

2.  Chunk size is set to 800 characters (~150-200 tokens for English academic
    text) with 150-character overlap:
    - 800 chars: enough context for one complete concept/paragraph
    - 150 chars overlap: prevents concept truncation at chunk boundaries
    - These are NOT hardcoded — values are injected via parameters so the
      Sandbox validation loop (where lecturers test quality) can tune them.

3.  Every chunk inherits the COMPLETE metadata from its parent page:
    - filename, page_number, is_ocr, word_count
    - Plus chunk-level: chunk_index, char_start, char_end, raptor_level
    - raptor_level=0 marks leaf nodes; RAPTOR summaries will use levels 1-3

4.  chunk_id follows a deterministic format:
    "{filename}::{page}::{chunk_index}"
    This ensures idempotency — re-uploading the same file produces the same
    IDs, which means Pinecone upsert will update (not duplicate) the vectors.

5.  We preserve the source_text field in metadata (truncated to 500 chars)
    for the Source Badge excerpt display in Sprint 6. Full text is available
    via Pinecone metadata but we avoid storing entire chunks there for cost.

Known Limitations:
------------------
- For very long pages (> 5000 chars), the overlap may cause near-duplicate
  chunks. This is acceptable for Sprint 1; RAPTOR (Sprint 2) will further
  deduplicate semantically similar content at the cluster level.
- Non-paragraph-formatted PDFs (e.g., columns without newlines) may chunk
  poorly. The OCR flag is preserved so the evaluator can identify these.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag.ingestion.parser import ParsedPage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class DocumentChunk:
    """
    A single semantic chunk ready for embedding and upsertion.

    Attributes:
        chunk_id:    Deterministic unique ID for Pinecone upsert idempotency.
        text:        The actual chunk text to be embedded.
        metadata:    Complete provenance metadata for citation and filtering.
                     Stored as Pinecone vector metadata.
    """
    chunk_id: str
    text: str
    metadata: dict[str, Any]


@dataclass
class MultimodalChunk(DocumentChunk):
    """
    A DocumentChunk that also carries image bytes for multimodal embedding.

    Extends DocumentChunk so it can flow through the same Pinecone upsert
    path. The image_bytes field is used ONLY during embedding; it is NOT
    stored in Pinecone metadata (which has a 40KB per-vector limit).

    Attributes (additional to DocumentChunk):
        image_bytes:   Raw PNG or JPEG bytes for the embedded image.
                       Set to None for text-only chunks (even in multimodal
                       pipeline — text chunks produced from image pages still
                       use the base DocumentChunk class).
        mime_type:     MIME type of the image: 'image/png' or 'image/jpeg'.
        has_image:     Convenience flag, also mirrored in metadata['has_image'].
    """
    image_bytes: bytes | None = field(default=None, repr=False)
    mime_type: str = "image/png"
    has_image: bool = False


# ---------------------------------------------------------------------------
# Constants — Exposed as defaults but injectable via parameters
# ---------------------------------------------------------------------------

DEFAULT_CHUNK_SIZE = 800      # Characters (≈150-200 tokens for English text)
DEFAULT_CHUNK_OVERLAP = 150   # Characters of overlap between adjacent chunks
DEFAULT_EXCERPT_LENGTH = 500  # Max chars stored in metadata for Source Badges

# Hierarchy separators: the splitter tries each in order until it fits.
# Academic PDFs commonly use: double newlines (paragraphs), single newlines
# (list items), period + space (sentences).
_SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""]


# ---------------------------------------------------------------------------
# Core Chunking Function
# ---------------------------------------------------------------------------

def chunk_pages(
    pages: list[ParsedPage],
    course_id: str,
    uploaded_by: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[DocumentChunk]:
    """
    Split a list of ParsedPage objects into DocumentChunk objects.

    This function is deterministic: the same input always produces the same
    chunk_ids. This is essential for Pinecone upsert idempotency — re-ingesting
    a file will UPDATE existing vectors rather than creating duplicates.

    Args:
        pages:        Output from ingestion.parser.parse_pdf().
        course_id:    Course namespace identifier. Used for Pinecone namespace
                      isolation (each course has its own vector namespace).
        uploaded_by:  User ID of the lecturer. Stored in chunk metadata for
                      access control and audit logging.
        chunk_size:   Target chunk size in characters. Tune in Sandbox mode.
        chunk_overlap: Overlap in characters between consecutive chunks.

    Returns:
        List of DocumentChunk objects, ordered by (page_number, chunk_index).
        Each chunk carries full provenance metadata.

    Example chunk_id format:
        "lecture_03.pdf::14::2"
        → filename "lecture_03.pdf", page 14, third chunk on that page.
    """
    if not pages:
        logger.warning("chunk_pages called with an empty pages list.")
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,  # Character-count-based, not token-based
        separators=_SEPARATORS,
        # Keep_separator=False: removes the separator char from chunk text.
        # This avoids chunks that start with "\n" which confuses embeddings.
        keep_separator=False,
        # add_start_index=True: LangChain attaches a start_index field to
        # metadata — handy for reconstructing the exact range later.
        add_start_index=True,
    )

    all_chunks: list[DocumentChunk] = []

    for page in pages:
        # Split the page text into raw string segments
        # LangChain returns plain strings from split_text()
        raw_splits: list[str] = splitter.split_text(page.text)

        for chunk_idx, raw_text in enumerate(raw_splits):
            # ---- Clean and validate chunk text ----------------------------
            cleaned_text = raw_text.strip()
            if not cleaned_text:
                # Skip whitespace-only chunks produced by wide overlaps
                continue

            # ---- Deterministic chunk ID -----------------------------------
            # Format: "{filename}::{page}::{chunk_index}"
            # Double-colon delimiter is safe because filenames contain dots,
            # underscores, hyphens — but not double-colons.
            chunk_id = _build_chunk_id(
                filename=page.filename,
                page_number=page.page_number,
                chunk_index=chunk_idx,
            )

            # ---- Rich Metadata --------------------------------------------
            # Every metadata field here maps to a Pinecone metadata filter key.
            # Document the schema in techstack.md § 4.1 when fields change.
            metadata: dict[str, Any] = {
                # --- Citation fields (Sprint 6: Source Badge) ---
                "filename": page.filename,
                "page_number": page.page_number,
                # excerpt: first N chars of chunk, used for Source Badge tooltip
                "excerpt": cleaned_text[:DEFAULT_EXCERPT_LENGTH],

                # --- Retrieval filter fields ---
                "course_id": course_id,
                "uploaded_by": uploaded_by,

                # --- Quality / provenance signals ---
                "is_ocr": page.is_ocr,         # Lower confidence if OCR
                "chunk_index": chunk_idx,
                "char_count": len(cleaned_text),
                "word_count": len(cleaned_text.split()),

                # --- RAPTOR tree fields (Sprint 2) ---
                # raptor_level=0 means leaf node (original chunk).
                # RAPTOR will insert summaries at levels 1, 2, 3.
                "raptor_level": 0,
                "chunk_type": "text",
            }

            all_chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    text=cleaned_text,
                    metadata=metadata,
                )
            )

    logger.info(
        "Chunking complete: %d page(s) → %d chunk(s) "
        "(chunk_size=%d, overlap=%d).",
        len(pages),
        len(all_chunks),
        chunk_size,
        chunk_overlap,
    )

    return all_chunks


# ---------------------------------------------------------------------------
# Helper: Deterministic Chunk ID
# ---------------------------------------------------------------------------

def _build_chunk_id(filename: str, page_number: int, chunk_index: int) -> str:
    """
    Build a deterministic, URL-safe chunk ID.

    Format: "{filename}::{page_number}::{chunk_index}"

    We do NOT hash the content because:
    - Hashed IDs break idempotency when the same page produces the same chunks
      (identical content → same hash → correct deduplication is preserved).
    - Human-readable IDs make debugging Pinecone queries much easier.

    If the filename contains special characters, we keep them — Pinecone
    vector IDs must be strings of up to 512 bytes, any printable chars OK.
    """
    return f"{filename}::{page_number}::{chunk_index}"


# ---------------------------------------------------------------------------
# Sprint 8: Multimodal Chunking
# ---------------------------------------------------------------------------

# Overlap ratio threshold for deduplicating adjacent images whose surrounding
# text windows overlap substantially (e.g., two figures on same paragraph).
_DEDUP_OVERLAP_RATIO = 0.8


def chunk_multimodal_pages(
    multimodal_pages: list,           # list[MultimodalPage] — avoid circular import
    course_id: str,
    uploaded_by: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[DocumentChunk]:
    """
    Chunk a list of MultimodalPage objects into DocumentChunk and MultimodalChunk objects.

    Strategy:
      - Text-only pages (no images): processed identically to chunk_pages()
        using the existing RecursiveCharacterTextSplitter. Returns DocumentChunk.
      - Pages with images: creates ONE MultimodalChunk per qualifying image,
        containing the image bytes + surrounding text as the chunk text.
        Remaining text on the page (outside image context windows) is chunked
        normally and returned as DocumentChunk objects.
      - Adjacent images whose surrounding_text strings share ≥80% of tokens
        are deduplicated: only the first is kept (prevents near-duplicate vectors).

    Args:
        multimodal_pages: Output of ingestion.multimodal_parser.extract_multimodal_pages().
        course_id:        Pinecone namespace for course isolation.
        uploaded_by:      Uploader identifier stored in metadata.
        chunk_size:       Target size for text-only chunks (characters).
        chunk_overlap:    Overlap for text-only chunks (characters).

    Returns:
        Mixed list of DocumentChunk (text) and MultimodalChunk (image+text).
        MultimodalChunk objects carry .image_bytes in memory but NOT in Pinecone
        metadata — the embedder uses the bytes then discards them.
    """
    if not multimodal_pages:
        logger.warning("chunk_multimodal_pages called with empty list.")
        return []

    all_chunks: list[DocumentChunk] = []

    for mm_page in multimodal_pages:
        parsed_page = mm_page.parsed_page

        if not mm_page.has_images:
            # --- Text-only page: delegate to existing chunker ---
            text_chunks = chunk_pages(
                pages=[parsed_page],
                course_id=course_id,
                uploaded_by=uploaded_by,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            all_chunks.extend(text_chunks)
            continue

        # --- Page with images ---
        # 1. Deduplicate images with highly overlapping surrounding text
        qualifying_images = _deduplicate_images(mm_page.images)

        # Track how many multimodal chunks we've created on this page
        # so we can build deterministic IDs that don't collide with text chunks.
        mm_chunk_offset = 0

        for page_image in qualifying_images:
            # Build a descriptive text for the chunk:
            # surrounding_text already contains the contextual paragraphs.
            # We add the page reference for citation purposes.
            chunk_text = page_image.surrounding_text or f"[Image on page {mm_page.page_number}]"

            # Unique ID: "mm" prefix + existing format for easy identification
            chunk_id = f"mm::{parsed_page.filename}::{parsed_page.page_number}::{mm_chunk_offset}"
            mm_chunk_offset += 1

            metadata: dict[str, Any] = {
                # --- Citation fields ---
                "filename": parsed_page.filename,
                "page_number": parsed_page.page_number,
                "excerpt": chunk_text[:DEFAULT_EXCERPT_LENGTH],

                # --- Retrieval filter fields ---
                "course_id": course_id,
                "uploaded_by": uploaded_by,

                # --- Quality / provenance signals ---
                "is_ocr": parsed_page.is_ocr,
                "chunk_index": mm_chunk_offset - 1,
                "char_count": len(chunk_text),
                "word_count": len(chunk_text.split()),

                # --- RAPTOR tree fields ---
                "raptor_level": 0,

                # --- Multimodal-specific fields ---
                "chunk_type": "multimodal",
                "has_image": True,
                "image_format": page_image.mime_type.split("/")[-1],  # 'png' or 'jpeg'
                "image_width_px": page_image.width_px,
                "image_height_px": page_image.height_px,
                # NOTE: image_bytes are NOT included here (40KB Pinecone limit)
            }

            all_chunks.append(
                MultimodalChunk(
                    chunk_id=chunk_id,
                    text=chunk_text,
                    metadata=metadata,
                    image_bytes=page_image.image_bytes,
                    mime_type=page_image.mime_type,
                    has_image=True,
                )
            )

        # 2. Also chunk the remaining page text normally
        #    This ensures text content outside image context windows is indexed.
        text_chunks = chunk_pages(
            pages=[parsed_page],
            course_id=course_id,
            uploaded_by=uploaded_by,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        all_chunks.extend(text_chunks)

    mm_count = sum(1 for c in all_chunks if isinstance(c, MultimodalChunk))
    text_count = len(all_chunks) - mm_count
    logger.info(
        "chunk_multimodal_pages: %d multimodal chunk(s) + %d text chunk(s) = %d total.",
        mm_count, text_count, len(all_chunks),
    )

    return all_chunks


def _deduplicate_images(images: list) -> list:
    """
    Remove images whose surrounding text substantially overlaps with a prior image.

    Two images are considered duplicates if their surrounding_text token sets
    share ≥ _DEDUP_OVERLAP_RATIO of the smaller set's tokens.

    This handles the common case of figures placed close together on the same
    academic page — they often have the same paragraph as context.

    Args:
        images: List of PageImage objects from a single page.

    Returns:
        Filtered list with near-duplicate images removed (keeps first occurrence).
    """
    if len(images) <= 1:
        return images

    kept = [images[0]]
    for candidate in images[1:]:
        is_dup = False
        cand_tokens = set(candidate.surrounding_text.lower().split())
        for kept_img in kept:
            kept_tokens = set(kept_img.surrounding_text.lower().split())
            if not cand_tokens or not kept_tokens:
                continue
            intersection = cand_tokens & kept_tokens
            smaller = min(len(cand_tokens), len(kept_tokens))
            if smaller > 0 and len(intersection) / smaller >= _DEDUP_OVERLAP_RATIO:
                is_dup = True
                logger.debug(
                    "Deduplicating image xref=%d (%.0f%% text overlap with xref=%d).",
                    candidate.xref,
                    100 * len(intersection) / smaller,
                    kept_img.xref,
                )
                break
        if not is_dup:
            kept.append(candidate)

    return kept
