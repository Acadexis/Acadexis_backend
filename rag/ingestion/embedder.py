"""
Acadexis — Embedder & Pinecone Upserter (Sprint 1, Step 1.3)
=============================================================
Responsibility: Convert DocumentChunks into vectors using Gemini Embedding 2
and upsert them into Pinecone with full metadata.

Architecture:
-------------
This module has TWO exported functions:
  1. get_pinecone_index()  — singleton initialiser, called once at startup.
  2. embed_and_upsert()    — the main pipeline step: embed → upsert in batches.

Design Decisions:
-----------------
1.  google-genai SDK (NOT the deprecated google-generativeai):
    The unified `google-genai` package is the current standard as of 2026.
    We call `client.models.embed_content()` directly, not a LangChain wrapper,
    to avoid version drift and maintain precise control over API parameters.

2.  Task type: RETRIEVAL_DOCUMENT at index time, RETRIEVAL_QUERY at query time:
    Google's embedding models are task-optimised. Indexing with the wrong task
    type silently degrades retrieval accuracy. We enforce RETRIEVAL_DOCUMENT
    here; the retriever module (Sprint 2) must use RETRIEVAL_QUERY.

3.  Batch size of 100 chunks per Gemini API call:
    - Gemini embed_content returns a list of embeddings matching input count.
    - Pinecone recommends ≤1,000 vectors per upsert call.
    - 100 is a safe midpoint that avoids hitting both API rate limits and
      Gemini's per-request size limits (note: batch mode is not the same as
      sequential calls — this sends all 100 in ONE API request).

4.  Pinecone namespace per course:
    Using `course_id` as the Pinecone namespace provides:
    - Automatic isolation: course A cannot retrieve course B's chunks
    - Efficient filtered queries (no post-filter needed for course scoping)
    - Zero cost: namespaces are free in Pinecone serverless

5.  Idempotent upsert:
    Pinecone upsert is IDEMPOTENT by design. If a chunk_id already exists
    (from a previous upload of the same file), the vector is updated rather
    than duplicated. Our deterministic chunk_id system guarantees this.

6.  Error handling at the batch level:
    If one batch fails, we log the error and continue with remaining batches.
    This prevents a single Gemini timeout from losing all progress on a
    200-page textbook. Partially-indexed documents are flagged in the response.

Known Limitations:
------------------
- Embedding 100 chunks per call ≈ 0.5-2 seconds depending on text length.
  For a 200-page PDF with ~400 chunks this means ~4-8 Gemini API calls
  in sequence. The /api/ingest endpoint uses FastAPI BackgroundTasks so the
  client gets an immediate "accepted" response; processing continues async.
- Gemini free-tier has rate limits (RPM/TPM). If rate-limit errors occur,
  increase EMBED_BATCH_SIZE interval or add exponential backoff (see lesson.txt).
"""

import asyncio
import logging
import time
from typing import Any

from google import genai
from google.genai import types as genai_types
from pinecone import Pinecone, ServerlessSpec

from rag.config import get_settings
from rag.ingestion.chunker import DocumentChunk

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMBED_BATCH_SIZE = 100          # Chunks per Gemini API call
PINECONE_UPSERT_BATCH = 100    # Vectors per Pinecone upsert call
RETRY_MAX_ATTEMPTS = 3          # Max retries on transient API failures
RETRY_BACKOFF_SECONDS = 1.5     # Base for exponential backoff

# The task type that tells Gemini this embedding is for document indexing.
# CRITICAL: use RETRIEVAL_QUERY when embedding the *query* in Sprint 2.
_EMBED_TASK_TYPE = "RETRIEVAL_DOCUMENT"


# ---------------------------------------------------------------------------
# Pinecone Client — Singleton Pattern
# ---------------------------------------------------------------------------

_pinecone_client: Pinecone | None = None
_pinecone_index = None   # Type: pinecone.Index


def get_pinecone_index():
    """
    Return a cached Pinecone index object.

    Called once at application startup (in main.py lifespan event).
    Subsequent calls return the cached object — avoids repeated API calls
    to resolve the index host (important for production latency).

    If the index does not exist, it is created automatically with the
    correct dimension and cosine metric. This is safe for development;
    in production, pre-create the index via Pinecone console for safety.

    Returns:
        pinecone.Index: Ready-to-use index object.
    """
    global _pinecone_client, _pinecone_index

    if _pinecone_index is not None:
        return _pinecone_index

    settings = get_settings()
    _pinecone_client = Pinecone(api_key=settings.pinecone_api_key)

    existing_indexes = [idx.name for idx in _pinecone_client.list_indexes()]

    if settings.pinecone_index_name not in existing_indexes:
        logger.warning(
            "Pinecone index '%s' not found. Creating with dimension=%d, "
            "metric=cosine, cloud=%s, region=%s.",
            settings.pinecone_index_name,
            settings.pinecone_dimension,
            settings.pinecone_cloud,
            settings.pinecone_region,
        )
        _pinecone_client.create_index(
            name=settings.pinecone_index_name,
            dimension=settings.pinecone_dimension,
            metric="cosine",
            spec=ServerlessSpec(
                cloud=settings.pinecone_cloud,
                region=settings.pinecone_region,
            ),
        )
        # Wait for the index to be ready before returning
        _wait_for_index_ready(settings.pinecone_index_name)

    # Cache the index reference with explicit name — avoids re-resolving host
    _pinecone_index = _pinecone_client.Index(settings.pinecone_index_name)
    logger.info(
        "Pinecone index '%s' connected.", settings.pinecone_index_name
    )

    return _pinecone_index


def _wait_for_index_ready(index_name: str, timeout_seconds: int = 120) -> None:
    """Poll until the index status is 'Ready' or we time out."""
    global _pinecone_client
    start = time.time()
    while time.time() - start < timeout_seconds:
        desc = _pinecone_client.describe_index(index_name)
        if desc.status.get("ready", False):
            logger.info("Pinecone index '%s' is ready.", index_name)
            return
        logger.debug("Waiting for Pinecone index '%s' to be ready...", index_name)
        time.sleep(5)
    raise TimeoutError(
        f"Pinecone index '{index_name}' did not become ready within "
        f"{timeout_seconds} seconds."
    )


# ---------------------------------------------------------------------------
# Gemini Embedding Client — Singleton Pattern
# ---------------------------------------------------------------------------

_gemini_client: genai.Client | None = None


def _get_gemini_client() -> genai.Client:
    """Return a cached Gemini genai.Client."""
    global _gemini_client
    if _gemini_client is None:
        settings = get_settings()
        _gemini_client = genai.Client(api_key=settings.google_api_key)
        logger.debug("Gemini genai.Client initialised.")
    return _gemini_client


# ---------------------------------------------------------------------------
# Core Pipeline: Embed + Upsert
# ---------------------------------------------------------------------------

async def embed_and_upsert(
    chunks: list[DocumentChunk],
    course_id: str,
) -> dict[str, Any]:
    """
    Embed a list of DocumentChunks and upsert them into Pinecone.

    This is the main pipeline step for Sprint 1. It runs in a FastAPI
    BackgroundTask so the HTTP response is not blocked.

    Args:
        chunks:     Output of ingestion.chunker.chunk_pages().
        course_id:  Used as the Pinecone namespace for course isolation.

    Returns:
        A summary dict:
        {
            "total_chunks": int,
            "upserted": int,         # Successfully embedded + upserted
            "failed_batches": int,   # Batches that failed after all retries
        }

    Errors:
        Individual batch failures are logged but not re-raised — other
        batches continue processing. The caller inspects `failed_batches`.
    """
    if not chunks:
        logger.warning("embed_and_upsert called with empty chunks list.")
        return {"total_chunks": 0, "upserted": 0, "failed_batches": 0}

    settings = get_settings()
    client = _get_gemini_client()
    index = get_pinecone_index()

    total = len(chunks)
    upserted = 0
    failed_batches = 0

    logger.info(
        "Starting embed+upsert: %d chunks into namespace='%s'.",
        total,
        course_id,
    )

    # ---- Process in batches -------------------------------------------------
    for batch_start in range(0, total, EMBED_BATCH_SIZE):
        batch = chunks[batch_start : batch_start + EMBED_BATCH_SIZE]
        texts = [c.text for c in batch]

        # ---- Step A: Generate embeddings ------------------------------------
        embeddings = await _embed_with_retry(
            client=client,
            texts=texts,
            model=settings.gemini_embedding_model,
            output_dimensionality=settings.gemini_embedding_dimension,
        )

        if embeddings is None:
            # All retries exhausted for this batch
            failed_batches += 1
            logger.error(
                "Batch %d-%d: Skipping after all retry attempts.",
                batch_start,
                batch_start + len(batch),
            )
            continue

        # ---- Step B: Build Pinecone vector records --------------------------
        vectors = _build_pinecone_vectors(
            batch=batch,
            embeddings=embeddings,
        )

        # ---- Step C: Upsert into Pinecone -----------------------------------
        success = await _upsert_with_retry(
            index=index,
            vectors=vectors,
            namespace=course_id,
        )

        if success:
            upserted += len(batch)
            logger.debug(
                "Batch %d-%d: %d vectors upserted.",
                batch_start,
                batch_start + len(batch),
                len(batch),
            )
        else:
            failed_batches += 1

    logger.info(
        "embed_and_upsert complete: %d/%d chunks upserted, "
        "%d batch(es) failed.",
        upserted,
        total,
        failed_batches,
    )

    return {
        "total_chunks": total,
        "upserted": upserted,
        "failed_batches": failed_batches,
    }


# ---------------------------------------------------------------------------
# Helpers: Embedding with Retry
# ---------------------------------------------------------------------------

async def _embed_with_retry(
    client: genai.Client,
    texts: list[str],
    model: str,
    output_dimensionality: int,
) -> list | None:
    """
    Call Gemini embed_content with exponential backoff retry.

    Returns:
        List of embedding value arrays, or None if all retries failed.
    """
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            # google-genai SDK: embed_content is a synchronous call.
            # We run it in a thread executor to avoid blocking the async loop.
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.models.embed_content(
                    model=model,
                    contents=texts,
                    config=genai_types.EmbedContentConfig(
                        task_type=_EMBED_TASK_TYPE,
                        output_dimensionality=output_dimensionality,
                    ),
                ),
            )
            # response.embeddings is a list of ContentEmbedding objects
            # each with a .values attribute (list[float])
            return [emb.values for emb in response.embeddings]

        except Exception as exc:
            wait = RETRY_BACKOFF_SECONDS ** attempt
            logger.warning(
                "Gemini embed_content attempt %d/%d failed: %s. "
                "Retrying in %.1fs.",
                attempt,
                RETRY_MAX_ATTEMPTS,
                exc,
                wait,
            )
            if attempt < RETRY_MAX_ATTEMPTS:
                await asyncio.sleep(wait)

    return None


# ---------------------------------------------------------------------------
# Helpers: Build Pinecone Vectors
# ---------------------------------------------------------------------------

def _build_pinecone_vectors(
    batch: list[DocumentChunk],
    embeddings: list[list[float]],
) -> list[dict[str, Any]]:
    """
    Pair DocumentChunks with their embedding vectors into Pinecone format.

    Pinecone upsert expects a list of dicts with:
      - "id":       string (our deterministic chunk_id)
      - "values":   list[float] (the embedding vector)
      - "metadata": dict (arbitrary filterable metadata)

    Metadata stored in Pinecone:
      IMPORTANT: Pinecone metadata has a 40KB limit per vector.
      We store only fields needed for retrieval filtering and Source Badge
      display. The full chunk text is stored as "text" (for reranking in
      Sprint 2 which needs the raw text to pass to Cohere Rerank).
    """
    vectors = []
    for chunk, embedding in zip(batch, embeddings):
        # Build the metadata dict
        # Key: "text" is stored alongside filtering fields so the retriever
        # can return the chunk text without a second lookup.
        metadata = {
            **chunk.metadata,    # Inherits all fields from chunker.py
            "text": chunk.text,  # Full text for reranking and Source Badge
        }
        vectors.append(
            {
                "id": chunk.chunk_id,
                "values": embedding,
                "metadata": metadata,
            }
        )
    return vectors


# ---------------------------------------------------------------------------
# Helpers: Pinecone Upsert with Retry
# ---------------------------------------------------------------------------

async def _upsert_with_retry(
    index,
    vectors: list[dict],
    namespace: str,
) -> bool:
    """
    Upsert vectors into Pinecone with exponential backoff retry.

    Returns:
        True if upsert succeeded, False if all retries exhausted.
    """
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: index.upsert(
                    vectors=vectors,
                    namespace=namespace,
                ),
            )
            return True

        except Exception as exc:
            wait = RETRY_BACKOFF_SECONDS ** attempt
            logger.warning(
                "Pinecone upsert attempt %d/%d failed: %s. Retrying in %.1fs.",
                attempt,
                RETRY_MAX_ATTEMPTS,
                exc,
                wait,
            )
            if attempt < RETRY_MAX_ATTEMPTS:
                await asyncio.sleep(wait)

    return False


# ---------------------------------------------------------------------------
# Sprint 8: Multimodal Embedding
# ---------------------------------------------------------------------------

async def embed_and_upsert_multimodal(
    chunks: list,    # list[DocumentChunk | MultimodalChunk]
    course_id: str,
) -> dict:
    """
    Embed and upsert a mixed list of text and multimodal chunks into Pinecone.

    Routing strategy:
      - DocumentChunk (text-only):   → fast batch path (100 at a time, 1 API call)
      - MultimodalChunk (image+text): → per-chunk path (1 API call per chunk)

    The separation is necessary because Gemini's embed_content API cannot batch
    heterogeneous inputs — each multimodal chunk has a unique [text, image_bytes]
    structure that cannot be combined with other chunks in a single call.

    After embedding, image_bytes are discarded. Only the vector and text metadata
    are upserted to Pinecone (respecting the 40KB per-vector metadata limit).

    Args:
        chunks:     Output of ingestion.chunker.chunk_multimodal_pages().
        course_id:  Pinecone namespace identifier.

    Returns:
        {
            "total_chunks": int,
            "upserted": int,
            "failed_batches": int,
            "multimodal_embedded": int,   # Count of image chunks embedded
            "text_embedded": int,         # Count of text-only chunks embedded
        }
    """
    # Avoid circular import — MultimodalChunk is in chunker.py
    from ingestion.chunker import MultimodalChunk

    if not chunks:
        logger.warning("embed_and_upsert_multimodal called with empty chunks list.")
        return {
            "total_chunks": 0,
            "upserted": 0,
            "failed_batches": 0,
            "multimodal_embedded": 0,
            "text_embedded": 0,
        }

    # Split into two groups
    text_chunks = [c for c in chunks if not isinstance(c, MultimodalChunk)]
    mm_chunks = [c for c in chunks if isinstance(c, MultimodalChunk)]

    logger.info(
        "embed_and_upsert_multimodal: %d text chunk(s) + %d multimodal chunk(s) "
        "→ namespace='%s'.",
        len(text_chunks), len(mm_chunks), course_id,
    )

    total_upserted = 0
    total_failed_batches = 0

    # --- Path A: Text-only batch embedding (existing fast path) ---
    if text_chunks:
        result = await embed_and_upsert(chunks=text_chunks, course_id=course_id)
        total_upserted += result["upserted"]
        total_failed_batches += result["failed_batches"]

    # --- Path B: Multimodal per-chunk embedding ---
    mm_upserted = 0
    if mm_chunks:
        settings = get_settings()
        client = _get_gemini_client()
        index = get_pinecone_index()

        for mm_chunk in mm_chunks:
            embedding = await _embed_multimodal_chunk(
                client=client,
                chunk=mm_chunk,
                model=settings.gemini_embedding_model,
                output_dimensionality=settings.gemini_embedding_dimension,
            )

            if embedding is None:
                total_failed_batches += 1
                logger.error(
                    "Multimodal chunk '%s': embedding failed after all retries.",
                    mm_chunk.chunk_id,
                )
                continue

            # Build Pinecone vector — image_bytes are NOT included in metadata
            metadata = {
                **mm_chunk.metadata,
                "text": mm_chunk.text,
                # image_bytes deliberately excluded — 40KB Pinecone metadata limit
            }
            vector = {
                "id": mm_chunk.chunk_id,
                "values": embedding,
                "metadata": metadata,
            }

            success = await _upsert_with_retry(
                index=index,
                vectors=[vector],
                namespace=course_id,
            )

            if success:
                mm_upserted += 1
                logger.debug(
                    "Multimodal chunk '%s' upserted (%s, %dx%dpx).",
                    mm_chunk.chunk_id,
                    mm_chunk.metadata.get("image_format", "?"),
                    mm_chunk.metadata.get("image_width_px", 0),
                    mm_chunk.metadata.get("image_height_px", 0),
                )
            else:
                total_failed_batches += 1

        total_upserted += mm_upserted

    logger.info(
        "embed_and_upsert_multimodal complete: "
        "%d/%d total upserted (%d text, %d multimodal), %d batch(es) failed.",
        total_upserted,
        len(chunks),
        len(text_chunks),
        mm_upserted,
        total_failed_batches,
    )

    return {
        "total_chunks": len(chunks),
        "upserted": total_upserted,
        "failed_batches": total_failed_batches,
        "multimodal_embedded": mm_upserted,
        "text_embedded": total_upserted - mm_upserted,
    }


async def _embed_multimodal_chunk(
    client: genai.Client,
    chunk,   # MultimodalChunk
    model: str,
    output_dimensionality: int,
) -> list[float] | None:
    """
    Embed a single MultimodalChunk using Gemini Embedding 2's multimodal API.

    Passes an interleaved [text_part, image_part] to embed_content.
    The model generates ONE aggregated embedding capturing combined semantics.

    Returns:
        List of floats (embedding vector), or None if all retries exhausted.
    """
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            loop = asyncio.get_event_loop()

            # Capture chunk locals for the lambda (closure safety)
            chunk_text = chunk.text
            chunk_image_bytes = chunk.image_bytes
            chunk_mime_type = chunk.mime_type

            response = await loop.run_in_executor(
                None,
                lambda: client.models.embed_content(
                    model=model,
                    contents=[
                        # Text part — the surrounding contextual paragraphs
                        chunk_text,
                        # Image part — raw bytes with correct MIME type
                        genai_types.Part.from_bytes(
                            data=chunk_image_bytes,
                            mime_type=chunk_mime_type,
                        ),
                    ],
                    config=genai_types.EmbedContentConfig(
                        task_type=_EMBED_TASK_TYPE,
                        output_dimensionality=output_dimensionality,
                    ),
                ),
            )

            # Single chunk → single embedding in response.embeddings[0]
            if response.embeddings:
                return response.embeddings[0].values

            logger.warning(
                "Multimodal embed attempt %d/%d: empty response for chunk '%s'.",
                attempt, RETRY_MAX_ATTEMPTS, chunk.chunk_id,
            )

        except Exception as exc:
            wait = RETRY_BACKOFF_SECONDS ** attempt
            logger.warning(
                "Multimodal embed attempt %d/%d failed for chunk '%s': %s. "
                "Retrying in %.1fs.",
                attempt, RETRY_MAX_ATTEMPTS, chunk.chunk_id, exc, wait,
            )
            if attempt < RETRY_MAX_ATTEMPTS:
                await asyncio.sleep(wait)

    return None
