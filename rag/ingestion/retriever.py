"""
Acadexis — Two-Stage Retriever (Sprint 2, Step 2.1 + 2.2)
==========================================================
Implements the two-stage retrieval pipeline:

  Stage 1 — Bi-Encoder (Pinecone ANN):
    Embed the query with Gemini (task_type=RETRIEVAL_QUERY) and fetch the
    top_k_retrieve (default 100) nearest neighbours from Pinecone using
    cosine similarity. This is fast but imprecise — ANN search trades
    some accuracy for sub-millisecond latency.

  Stage 2 — Cross-Encoder (Cohere Rerank 4 Pro):
    Pass the query + all 100 candidate texts to Cohere's rerank-v3.5 model.
    The cross-encoder reads BOTH query and document together, producing a
    much more accurate relevance score. We keep only the top_k_rerank
    (default 10) results.

Why two-stage instead of reranking everything upfront?
  - Reranking 1M+ vectors with a cross-encoder would be prohibitively slow.
  - ANN retrieval narrows the space to ~100 plausible candidates in < 50ms.
  - The cross-encoder then applies full attention over those 100 candidates.
  - The combined latency is typically 50-200ms total vs. 10s+ for direct rerank.

Why Cohere Rerank specifically?
  - rerank-v3.5 is a multilingual cross-encoder — important for Yoruba/English
    bilingual academic content in Nigerian universities.
  - It understands context better than BM25 keyword matching.
  - It has a generous free tier and predictable per-request pricing.

Fallback Behaviour:
  If COHERE_API_KEY is empty or blank, Stage 2 is skipped and results are
  returned in Pinecone cosine-score order. This allows the system to functionally
  work during development without a Cohere key.

Known Limitations (documented in lesson.txt):
  - Pinecone `query` is not true ANN for serverless — it uses a "pod-less"
    index that routes to the nearest region. Latency can vary (50-200ms).
  - Gemini embedding is synchronous; we use run_in_executor because the
    google-genai SDK does not have an async client yet (as of 2026).
"""

import asyncio
import logging
from dataclasses import dataclass

import cohere
from google import genai
from google.genai import types as genai_types

from rag.config import get_settings
from rag.ingestion.embedder import _get_gemini_client, get_pinecone_index
from rag.schemas.retrieve import RetrievedChunk

logger = logging.getLogger(__name__)

# Task type for embedding queries (DIFFERENT from document indexing).
# Using RETRIEVAL_DOCUMENT for queries silently degrades accuracy.
_QUERY_TASK_TYPE = "RETRIEVAL_QUERY"

# Cohere model identifier for the latest multilingual cross-encoder
COHERE_RERANK_MODEL = "rerank-v3.5"


# ---------------------------------------------------------------------------
# Cohere Client — Lazy Singleton
# ---------------------------------------------------------------------------

_cohere_client: cohere.ClientV2 | None = None


def _get_cohere_client() -> cohere.ClientV2 | None:
    """
    Return a cached Cohere ClientV2, or None if no API key is configured.

    Returns None gracefully so callers can implement a sensible fallback
    (return results in Pinecone cosine order) rather than raising an error.
    """
    global _cohere_client
    if _cohere_client is not None:
        return _cohere_client

    settings = get_settings()
    if not settings.cohere_api_key:
        logger.warning(
            "COHERE_API_KEY is not set. Reranking will be skipped. "
            "Results will be returned in raw Pinecone cosine order."
        )
        return None

    _cohere_client = cohere.ClientV2(api_key=settings.cohere_api_key)
    logger.info("Cohere ClientV2 initialised (model=%s).", COHERE_RERANK_MODEL)
    return _cohere_client


# ---------------------------------------------------------------------------
# Stage 1: Bi-Encoder Retrieval (Pinecone ANN)
# ---------------------------------------------------------------------------

async def _embed_query(query: str) -> list[float]:
    """
    Embed a single query string using Gemini with task_type=RETRIEVAL_QUERY.

    CRITICAL: This MUST use RETRIEVAL_QUERY not RETRIEVAL_DOCUMENT.
    The two task types produce different vector spaces optimised for their roles:
      - RETRIEVAL_DOCUMENT: vectors cluster by topic.
      - RETRIEVAL_QUERY:    vectors are oriented toward finding relevant docs.
    Using RETRIEVAL_DOCUMENT here halves effective retrieval accuracy.

    Returns:
        list[float]: The embedding vector with length = gemini_embedding_dimension.
    """
    settings = get_settings()
    client: genai.Client = _get_gemini_client()

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.models.embed_content(
            model=settings.gemini_embedding_model,
            contents=[query],
            config=genai_types.EmbedContentConfig(
                task_type=_QUERY_TASK_TYPE,
                output_dimensionality=settings.gemini_embedding_dimension,
            ),
        ),
    )
    return response.embeddings[0].values


async def _pinecone_ann_search(
    query_vector: list[float],
    course_id: str,
    top_k: int,
    raptor_levels: list[int],
) -> list[dict]:
    """
    Query Pinecone for the top_k most similar vectors in the course namespace.

    Filters by raptor_level to allow searching only specific tree levels
    (e.g., leaf nodes only, or summaries only).

    Args:
        query_vector:  The embedded query vector.
        course_id:     Pinecone namespace (course isolation from Sprint 1).
        top_k:         Number of candidates to retrieve (default 100).
        raptor_levels: List of RAPTOR levels to include in the search.

    Returns:
        List of Pinecone match dicts:
        [{id, score, metadata: {text, filename, page_number, ...}}]
    """
    index = get_pinecone_index()

    # Build the RAPTOR level filter:
    # Pinecone metadata filters use MongoDB-style operators.
    # {"raptor_level": {"$in": [0, 1, 2]}} matches vectors at any of those levels.
    raptor_filter = {"raptor_level": {"$in": raptor_levels}}

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: index.query(
            vector=query_vector,
            top_k=top_k,
            namespace=course_id,
            filter=raptor_filter,
            include_metadata=True,   # We need text + metadata for Stage 2
            include_values=False,    # Don't return the raw vectors (wasteful)
        ),
    )

    matches: list[dict] = []
    for match in response.matches:
        matches.append(
            {
                "id": match.id,
                "score": match.score,          # Cosine similarity (0-1)
                "metadata": dict(match.metadata) if match.metadata else {},
            }
        )

    logger.info(
        "Pinecone ANN search: %d candidates retrieved for course='%s'.",
        len(matches),
        course_id,
    )
    return matches


# ---------------------------------------------------------------------------
# Stage 2: Cross-Encoder Reranking (Cohere Rerank 4 Pro)
# ---------------------------------------------------------------------------

async def _cohere_rerank(
    query: str,
    candidates: list[dict],
    top_n: int,
) -> tuple[list[dict], bool]:
    """
    Apply Cohere cross-encoder reranking over Stage 1 candidates.

    The cross-encoder reads the concatenation of query + document text together,
    using full self-attention. This is far more accurate than cosine similarity
    but too slow to run over the entire index.

    Args:
        query:      Original user query string.
        candidates: List of Pinecone match dicts from Stage 1.
        top_n:      Number of results to return after reranking.

    Returns:
        Tuple of (reranked_candidates, reranked_flag).
        reranked_flag is False if Cohere is unavailable (graceful fallback).

    Cohere API Notes:
        - `model`: rerank-v3.5 — multilingual, 512-token context per doc.
        - `documents`: can be strings or {"text": "..."} dicts.
        - Response: list of RerankResult with index (into original list)
          and relevance_score (0.0-1.0).
        - Pricing: per 1K tokens; ~100 chunks at 200 tokens avg = ~0.4¢.
    """
    co = _get_cohere_client()

    if co is None:
        # Graceful degradation: return top_n from Pinecone cosine order
        logger.debug("Cohere not available. Returning top %d in cosine order.", top_n)
        return candidates[:top_n], False

    # Extract the text for each candidate.
    # Cohere rerank accepts list[str] directly.
    documents = [c["metadata"].get("text", "") for c in candidates]

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: co.rerank(
                model=COHERE_RERANK_MODEL,
                query=query,
                documents=documents,
                top_n=top_n,
                # return_documents=False: do NOT re-send doc text in response
                # (we already have it in candidates; saves bandwidth).
                return_documents=False,
            ),
        )

        # Reconstruct in reranked order using the returned index references
        reranked: list[dict] = []
        for result in response.results:
            original = candidates[result.index]
            reranked.append(
                {
                    **original,
                    "relevance_score": result.relevance_score,
                    "rank": len(reranked) + 1,
                }
            )

        logger.info(
            "Cohere reranking: %d candidates → top %d returned.",
            len(candidates),
            len(reranked),
        )
        return reranked, True

    except Exception as exc:
        # Log but don't re-raise — fall back to cosine order
        logger.error(
            "Cohere rerank failed: %s. Falling back to cosine score order.", exc
        )
        return candidates[:top_n], False


# ---------------------------------------------------------------------------
# Public API: Full Two-Stage Retrieval Pipeline
# ---------------------------------------------------------------------------

async def retrieve(
    query: str,
    course_id: str,
    top_k_retrieve: int = 100,
    top_k_rerank: int = 10,
    raptor_levels: list[int] | None = None,
    include_metadata: bool = True,
) -> tuple[list[RetrievedChunk], bool]:
    """
    Execute the full two-stage retrieval pipeline.

    Pipeline:
        1. Embed query with task_type=RETRIEVAL_QUERY (Gemini)
        2. ANN search Pinecone for top_k_retrieve candidates
        3. Rerank with Cohere Rerank 4 Pro for top_k_rerank results
        4. Package into RetrievedChunk response objects

    Args:
        query:           Student's question.
        course_id:       Pinecone namespace (course scope).
        top_k_retrieve:  Pinecone candidate count (default 100).
        top_k_rerank:    Final result count after reranking (default 10).
        raptor_levels:   RAPTOR levels to search ([0,1,2,3] = all).
        include_metadata: Whether to include metadata in response.

    Returns:
        Tuple of (List[RetrievedChunk], reranked_flag).
        Chunks are ordered by relevance (most relevant first).
    """
    if raptor_levels is None:
        raptor_levels = [0, 1, 2, 3]

    logger.info(
        "Retrieve: query='%s...', course='%s', k_retrieve=%d, k_rerank=%d",
        query[:60],
        course_id,
        top_k_retrieve,
        top_k_rerank,
    )

    # ---- Stage 1: Embed Query -----------------------------------------------
    query_vector = await _embed_query(query)

    # ---- Stage 2: ANN Search -------------------------------------------------
    candidates = await _pinecone_ann_search(
        query_vector=query_vector,
        course_id=course_id,
        top_k=top_k_retrieve,
        raptor_levels=raptor_levels,
    )

    if not candidates:
        logger.warning(
            "No candidates found in Pinecone for course='%s'. "
            "Has any content been ingested for this course?",
            course_id,
        )
        return [], False

    # ---- Stage 3: Cross-Encoder Reranking -----------------------------------
    reranked_candidates, did_rerank = await _cohere_rerank(
        query=query,
        candidates=candidates,
        top_n=top_k_rerank,
    )

    # ---- Stage 4: Pack into response objects --------------------------------
    results: list[RetrievedChunk] = []
    for i, candidate in enumerate(reranked_candidates):
        metadata = candidate.get("metadata", {})
        text = metadata.pop("text", "")   # Remove text from metadata (it's top-level)

        results.append(
            RetrievedChunk(
                chunk_id=candidate["id"],
                text=text,
                relevance_score=candidate.get(
                    "relevance_score",
                    candidate.get("score", 0.0),  # Cosine score fallback
                ),
                rank=candidate.get("rank", i + 1),
                metadata=metadata if include_metadata else None,
            )
        )

    return results, did_rerank
