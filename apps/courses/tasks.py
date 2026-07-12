"""
apps/courses/tasks.py — Celery tasks for course material processing.

AI Integration: RAG ingestion pipeline (PyMuPDF → Gemini Embed → Pinecone)
Notification: Django Channels push (backend team's code, untouched)

Contract:
    process_material(material_id: str) — Celery shared_task
    Sets material.status to "ready" on success, "failed" on error.
    Retries up to 3 times with 10s delay.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile

from celery import shared_task
from django.conf import settings as django_settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Availability guard
# ─────────────────────────────────────────────────────────────────────────────

def _rag_available() -> bool:
    """True only when both required API keys are set."""
    return bool(
        getattr(django_settings, "GOOGLE_API_KEY", "")
        and getattr(django_settings, "PINECONE_API_KEY", "")
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main Celery Task
# ─────────────────────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def process_material(self, material_id: str):
    """
    Process an uploaded course material through the RAG pipeline.

    Flow:
      1. Fetch CourseMaterial from Django DB
      2. Route to RAG pipeline (if keys present) or legacy text extraction
      3. Set status = "ready" and send notification on success
      4. Set status = "failed" and retry on error
    """
    from .models import CourseMaterial

    try:
        material = CourseMaterial.objects.get(id=material_id)
    except CourseMaterial.DoesNotExist:
        logger.error("process_material: CourseMaterial %s not found.", material_id)
        return

    try:
        material.status = "processing"
        material.save(update_fields=["status"])

        if _rag_available():
            logger.info(
                "process_material: using RAG pipeline for %s", material.file_name
            )
            _rag_process(material)
        else:
            logger.warning(
                "process_material: RAG keys missing, using legacy text-only for %s",
                material.file_name,
            )
            _legacy_process(material)

        material.status = "ready"
        material.save(update_fields=["page_count", "status"])

        _notify_material_ready(material)
        logger.info("process_material: %s is ready.", material.file_name)

    except Exception as exc:
        logger.error(
            "process_material: failed for %s — %s",
            material_id, exc, exc_info=True,
        )
        try:
            material.status = "failed"
            material.save(update_fields=["status"])
        except Exception:
            pass
        raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────────────────────
# RAG Path — full PyMuPDF + Gemini + Pinecone pipeline
# ─────────────────────────────────────────────────────────────────────────────

def _rag_process(material) -> None:
    """Bridge sync Celery task into async RAG pipeline."""
    asyncio.run(_async_rag_process(material))


async def _async_rag_process(material) -> None:
    """
    Full async RAG ingestion pipeline:
      parse → (wiki compile) → chunk → embed → Pinecone upsert → dual DB write
    """
    from .models import MaterialChunk
    from rag.config import get_settings
    from rag.ingestion.parser import parse_pdf, PDFParseError
    from rag.ingestion.chunker import chunk_pages
    from rag.ingestion.embedder import embed_and_upsert

    settings = get_settings()

    # Pinecone namespace = course code (stable, unique, URL-safe)
    course_id = material.course.code.lower().replace(" ", "-")
    uploaded_by = str(material.uploaded_by_id) if material.uploaded_by_id else "system"

    # ── Write file to a temp path (works for local disk and S3/R2 FileField) ──
    with material.file.open("rb") as fh:
        file_bytes = fh.read()

    tmp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    try:
        tmp_file.write(file_bytes)
        tmp_file.close()
        tmp_path = tmp_file.name

        # ── 1. Parse ────────────────────────────────────────────────────────
        try:
            parsed_pages = parse_pdf(tmp_path)
        except PDFParseError as exc:
            logger.error(
                "PDF parse error for %s: %s — falling back to legacy.", material.file_name, exc
            )
            _legacy_process(material)
            return

        material.page_count = len(parsed_pages)

        # ── 2. Multimodal image extraction (non-fatal) ──────────────────────
        mm_pages = None
        if settings.multimodal_enabled:
            try:
                from rag.ingestion.multimodal_parser import extract_multimodal_pages
                mm_pages = extract_multimodal_pages(
                    file_path=tmp_path,
                    parsed_pages=parsed_pages,
                    min_image_px=settings.multimodal_min_image_px,
                    context_chars=settings.multimodal_context_chars,
                )
                image_count = sum(len(getattr(p, "images", [])) for p in (mm_pages or []))
                if image_count:
                    logger.info(
                        "Multimodal: extracted %d images from %s", image_count, material.file_name
                    )
            except Exception as exc:
                logger.warning(
                    "Multimodal extraction failed for %s (using text-only): %s",
                    material.file_name, exc,
                )
                mm_pages = None

        # ── 3. Wiki compilation for core/syllabus documents ────────────────
        is_core = getattr(material, "is_core", False)
        if is_core:
            try:
                from rag.ingestion.wiki_compiler import compile_wiki_from_text
                from rag.evaluation.interaction_logger import upsert_wiki
                full_text = "\n\n".join(
                    getattr(p, "text", "") for p in parsed_pages
                )
                wiki_md = await compile_wiki_from_text(
                    course_id=course_id, raw_text=full_text
                )
                if wiki_md:
                    await upsert_wiki(course_id=course_id, markdown_content=wiki_md)
                    logger.info(
                        "Wiki compiled for course %s (%d chars)", course_id, len(wiki_md)
                    )
            except Exception as exc:
                logger.warning(
                    "Wiki compilation failed for %s (non-fatal): %s", material.file_name, exc
                )

        # ── 4. Chunk ─────────────────────────────────────────────────────────
        if mm_pages:
            try:
                from rag.ingestion.chunker import chunk_multimodal_pages
                chunks = chunk_multimodal_pages(
                    multimodal_pages=mm_pages,
                    course_id=course_id,
                    uploaded_by=uploaded_by,
                )
            except Exception as exc:
                logger.warning(
                    "Multimodal chunking failed for %s, falling back to text chunks: %s",
                    material.file_name, exc,
                )
                chunks = chunk_pages(
                    pages=parsed_pages, course_id=course_id, uploaded_by=uploaded_by
                )
        else:
            chunks = chunk_pages(
                pages=parsed_pages, course_id=course_id, uploaded_by=uploaded_by
            )

        if not chunks:
            logger.warning(
                "No chunks produced for %s — material stored as empty.", material.file_name
            )
            return

        # ── 5. Embed + upsert to Pinecone ────────────────────────────────────
        try:
            if mm_pages:
                from rag.ingestion.embedder import embed_and_upsert_multimodal
                result = await embed_and_upsert_multimodal(
                    chunks=chunks, course_id=course_id
                )
            else:
                result = await embed_and_upsert(chunks=chunks, course_id=course_id)

            logger.info(
                "Pinecone upsert for %s: %d/%d chunks (%d failed batches)",
                material.file_name,
                result.get("upserted", 0),
                result.get("total_chunks", 0),
                result.get("failed_batches", 0),
            )
        except Exception as exc:
            logger.error(
                "Pinecone upsert failed for %s: %s — chunks saved to DB only.",
                material.file_name, exc,
            )

        # ── 6. Dual-write: keep MaterialChunk rows for keyword fallback ───────
        material.chunks.all().delete()
        db_chunks = []
        for c in chunks:
            text = getattr(c, "text", None) or (
                c.get("text") if isinstance(c, dict) else ""
            )
            page = (
                getattr(c, "metadata", {}).get("page_number", 0)
                if hasattr(c, "metadata")
                else (c.get("metadata", {}).get("page_number", 0) if isinstance(c, dict) else 0)
            )
            if text:
                db_chunks.append(
                    MaterialChunk(
                        material=material,
                        page=page,
                        content=text[:2000],
                    )
                )
        if db_chunks:
            MaterialChunk.objects.bulk_create(db_chunks, batch_size=500)
            logger.info(
                "MaterialChunk fallback: %d rows written for %s",
                len(db_chunks), material.file_name,
            )

    finally:
        try:
            os.unlink(tmp_file.name)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Legacy Path — text-only extraction (original stub, kept as fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _legacy_process(material) -> None:
    """Original pdfplumber/pypdf extraction + DB-only chunk storage."""
    extracted = _extract_text(material)
    material.page_count = extracted.get("page_count", 0)
    chunks = _chunk_text(extracted.get("pages", []))
    _embed_and_store_chunks(material, chunks)


def _extract_text(material) -> dict:
    """Extract page-by-page text from the file. Falls back to simulated text if parsing fails."""
    pages = []
    page_count = 0

    # Try pdfplumber
    try:
        import pdfplumber
        with material.file.open("rb") as f:
            with pdfplumber.open(f) as pdf:
                page_count = len(pdf.pages)
                for idx, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    pages.append({"page": idx + 1, "text": text})
    except Exception:
        # Try pypdf
        try:
            import pypdf
            with material.file.open("rb") as f:
                reader = pypdf.PdfReader(f)
                page_count = len(reader.pages)
                for idx, page in enumerate(reader.pages):
                    text = page.extract_text() or ""
                    pages.append({"page": idx + 1, "text": text})
        except Exception:
            pass

    # Fallback to simulated content if extraction failed
    has_text = any(p["text"].strip() for p in pages)
    if not has_text:
        title = material.course.title
        code = material.course.code

        simulated_paragraphs = [
            f"Welcome to {code} — {title}. This course material covers introductory concepts and foundational theories.",
            "Chapter 1 introduces key definitions, core methodologies, and historical context relevant to the subject.",
            "Research methods, experimental design, and analytical frameworks are explored in Chapter 2.",
            "Recent advancements, case studies, and practical applications are discussed in Chapter 3.",
            "Conclusion and future outlook: summary of main takeaways and potential research directions.",
        ]
        page_count = len(simulated_paragraphs)
        pages = [{"page": i + 1, "text": p} for i, p in enumerate(simulated_paragraphs)]

    return {"page_count": page_count, "pages": pages}


def _chunk_text(pages: list, chunk_size: int = 800, chunk_overlap: int = 100) -> list:
    """Generate overlapping text chunks from extracted pages."""
    chunks = []
    for p in pages:
        text = p["text"]
        page_num = p["page"]

        if not text:
            continue

        start = 0
        while start < len(text):
            end = start + chunk_size
            content = text[start:end]
            chunks.append({"page": page_num, "content": content})
            start += chunk_size - chunk_overlap

    if not chunks:
        for p in pages:
            chunks.append({"page": p["page"], "content": p["text"]})

    return chunks


def _embed_and_store_chunks(material, chunks: list) -> None:
    """Store chunks in the Django DB only (no vector embeddings — legacy mode)."""
    from .models import MaterialChunk

    material.chunks.all().delete()
    MaterialChunk.objects.bulk_create([
        MaterialChunk(
            material=material,
            page=chunk["page"],
            content=chunk["content"],
        )
        for chunk in chunks
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Notification (backend team's code — untouched)
# ─────────────────────────────────────────────────────────────────────────────

def _notify_material_ready(material) -> None:
    if not material.uploaded_by:
        return
    try:
        from apps.notifications.models import Notification

        Notification.create_and_push(
            user=material.uploaded_by,
            title="Material Ready",
            body=f"{material.file_name} has been processed and is ready for study.",
            notification_type="material_ready",
            data={
                "material_id": str(material.id),
                "course_id": str(material.course.id),
            },
        )
    except Exception as e:
        logger.warning("_notify_material_ready: Could not send notification — %s", e)
