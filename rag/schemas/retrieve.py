"""
Acadexis — Retrieval Schemas (Sprint 2)
=======================================
Pydantic v2 models for the /api/retrieve request and response.

Why separate schemas from routes:
  - Routes stay thin and readable; all validation logic lives here.
  - Schemas can be shared between the REST endpoint and the LangGraph agent
    in Sprint 3 without duplication.
  - OpenAPI docs are generated automatically from these models.
"""

from typing import Any
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class RetrieveRequest(BaseModel):
    """POST /api/retrieve request body."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="The student's question or search query.",
        examples=["What is the time complexity of merge sort?"],
    )
    course_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description=(
            "Course namespace to search within. "
            "Must match the course_id used during ingestion."
        ),
        examples=["csc501-dsa"],
    )
    top_k_retrieve: int = Field(
        default=100,
        ge=10,
        le=200,
        description="Number of candidates fetched from Pinecone before reranking.",
    )
    top_k_rerank: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Final number of results returned after Cohere reranking.",
    )
    raptor_levels: list[int] = Field(
        default=[0, 1, 2, 3],
        description=(
            "RAPTOR levels to include in the search. "
            "0=leaf chunks, 1-3=summary nodes. "
            "Include all levels for full-tree retrieval."
        ),
    )
    include_metadata: bool = Field(
        default=True,
        description="Whether to include chunk metadata in the response.",
    )


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class RetrievedChunk(BaseModel):
    """A single retrieved and reranked document chunk."""

    chunk_id: str = Field(description="Deterministic chunk ID from Sprint 1.")
    text: str = Field(description="The chunk text used for answer generation.")
    relevance_score: float = Field(
        description=(
            "Cohere rerank relevance score (0.0-1.0). "
            "Higher is more relevant to the query."
        )
    )
    rank: int = Field(description="Final rank after reranking (1 = most relevant).")
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Source metadata for citation (filename, page_number, etc.).",
    )


class RetrieveResponse(BaseModel):
    """POST /api/retrieve response body."""

    query: str = Field(description="The original query string.")
    course_id: str
    results: list[RetrievedChunk] = Field(
        description="Reranked chunks, ordered by relevance (most relevant first)."
    )
    total_retrieved: int = Field(
        description="Number of candidates fetched from Pinecone before reranking."
    )
    total_returned: int = Field(
        description="Number of results returned after reranking."
    )
    reranked: bool = Field(
        description=(
            "True if Cohere reranking was applied. "
            "False if Cohere API key is absent (falls back to cosine order)."
        )
    )
