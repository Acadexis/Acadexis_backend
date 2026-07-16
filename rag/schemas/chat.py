"""
Acadexis — Chat API Schemas (Sprint 3 → Sprint 6)
==================================================
Pydantic v2 models for POST /api/chat request and response.

Sprint 6 additions:
  - SourceReference: LLM-confirmed citation with confidence score.
  - StructuredTutorResponse: the exact JSON schema Gemini must output via
    response_schema (JSON mode). This is the "source badge payload".
  - ChatResponse extended: follow_up_questions, bloom_level_used, cache_used.

Design: Two citation paths coexist
-----------------------------------
  Path A (Sprints 1–5): CitationModel — built from Pinecone chunk metadata
    after retrieval. These are always present (no LLM required).
  Path B (Sprint 6):    SourceReference — emitted BY the LLM as part of its
    structured JSON output. The LLM explicitly names which chunks it used
    and provides a confidence score for each.

  Path A is the ground truth (metadata-derived). Path B adds LLM self-report
  for the "Source Badge" UI — giving students and lecturers proof that the
  AI is NOT hallucinating. Both are returned in ChatResponse.
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------

class ConversationTurn(BaseModel):
    """A single turn in the conversation history."""
    role: str = Field(
        description="'student' or 'tutor'.",
        pattern=r"^(student|tutor)$",
    )
    content: str = Field(min_length=1, max_length=4000)


# ---------------------------------------------------------------------------
# Sprint 3: retrieval-derived citation (still used in ChatResponse.citations)
# ---------------------------------------------------------------------------

class CitationModel(BaseModel):
    """
    A single source citation built from Pinecone chunk metadata.
    Populated by the RetrieverAgent — does NOT require LLM output.
    """
    filename: str
    page_number: int
    excerpt: str
    relevance_score: float


# ---------------------------------------------------------------------------
# Sprint 6: LLM-confirmed citation (SourceReference for Source Badge UI)
# ---------------------------------------------------------------------------

class SourceReference(BaseModel):
    """
    A source citation explicitly confirmed by the LLM in its structured output.

    The LLM is instructed to list ONLY the chunks it actually used to form
    its Socratic response — not all retrieved chunks. This is the "Source Badge"
    payload: each SourceReference maps directly to a clickable badge in the UI
    that opens the PDF viewer at the exact page.

    Fields:
        file_name:    Exact filename from Pinecone metadata (e.g. 'lecture_03.pdf').
        page_number:  Exact page number from Pinecone metadata.
        excerpt:      The specific sentence or phrase the LLM grounded its
                      response on. Max 300 chars to keep badges concise.
        confidence:   LLM self-reported confidence (0.0–1.0). Used to rank
                      badges and filter low-confidence citations (< 0.5).
    """
    file_name: str = Field(..., description="Name of the source document.")
    page_number: int = Field(..., ge=1, description="Exact page number (1-indexed).")
    excerpt: str = Field(
        ...,
        max_length=300,
        description="Relevant text excerpt from the source (max 300 chars).",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="LLM self-reported confidence that this source was used (0–1).",
    )


# ---------------------------------------------------------------------------
# Sprint 6: Structured LLM output schema
# ---------------------------------------------------------------------------

class StructuredTutorResponse(BaseModel):
    """
    The EXACT JSON structure Gemini must output when response_schema is used.

    This is the "compiled contract" between the LLM and the backend. Every
    field here maps directly to a feature in the frontend:

        answer              → Main chat message (Socratic, never direct)
        sources             → Source Badge array (each badge = one PDF page)
        bloom_level         → Shown in the student progress tracker
        follow_up_questions → Displayed as suggestion chips below the response

    Enforcement: Gemini 1.5 Pro's response_schema parameter forces the model
    to output valid JSON matching this schema. If parsing fails (model bug or
    API error), the PedagogicalAgent falls back to using the raw text string
    as the answer with empty sources/questions. This keeps the system robust.
    """
    answer: str = Field(
        ...,
        description=(
            "Socratic guiding response. NEVER a direct answer to academic questions. "
            "Must ask at least one guiding question."
        ),
    )
    sources: list[SourceReference] = Field(
        default_factory=list,
        description="Exact citations from course materials used in this response.",
    )
    bloom_level: str = Field(
        ...,
        description=(
            "Bloom's Taxonomy level of the student's question: "
            "remember | understand | apply | analyze | evaluate | create"
        ),
        pattern=r"^(remember|understand|apply|analyze|evaluate|create)$",
    )
    follow_up_questions: list[str] = Field(
        default_factory=list,
        max_length=3,
        description=(
            "1–3 Socratic follow-up questions to deepen the student's understanding. "
            "These appear as suggestion chips in the UI."
        ),
    )


# ---------------------------------------------------------------------------
# Request / Response
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    """POST /api/chat request body."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="The student's question.",
        examples=["Can you help me understand how merge sort works?"],
    )
    course_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description="Course namespace for retrieval (must match ingestion course_id).",
        examples=["csc501-dsa"],
    )
    session_id: str = Field(
        default="default-session",
        min_length=1,
        max_length=128,
        description=(
            "Unique session identifier for multi-turn memory. "
            "Each session maintains independent conversation history via LangGraph's "
            "MemorySaver checkpointer."
        ),
        examples=["student-001-session-20260414"],
    )
    conversation_history: list[ConversationTurn] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Previous conversation turns for multi-turn context. "
            "Ordered from oldest to newest. "
            "Maximum 20 turns (older turns are automatically truncated by the agent)."
        ),
    )
    # Sprint 5: optional cache_name for pre-warmed course documents
    cache_name: Optional[str] = Field(
        default=None,
        description=(
            "Gemini context cache resource name for this course document. "
            "If set, the PedagogicalAgent uses cached generation (cheaper). "
            "Obtain via POST /api/cache/warm before the first request."
        ),
    )


class ChatResponse(BaseModel):
    """POST /api/chat response body (Sprint 6)."""

    response: str = Field(description="The Socratic guiding response from the AI Tutor.")

    # Sprint 3: retrieval-derived citations (always present)
    citations: list[CitationModel] = Field(
        default_factory=list,
        description="Source citations derived from Pinecone chunk metadata.",
    )

    # Sprint 6: LLM-confirmed citations (Source Badge payload)
    source_references: list[SourceReference] = Field(
        default_factory=list,
        description=(
            "LLM-confirmed citations for Source Badge UI. "
            "Each entry maps to a clickable badge that opens the PDF at that page."
        ),
    )

    # Sprint 6: follow-up Socratic questions
    follow_up_questions: list[str] = Field(
        default_factory=list,
        description=(
            "1–3 Socratic follow-up questions suggested by the tutor. "
            "Displayed as suggestion chips below the response in the UI."
        ),
    )

    # Sprint 6: Bloom's Taxonomy level of the student's question
    bloom_level_used: str = Field(
        default="understand",
        description="Bloom's Taxonomy level detected for this question.",
    )

    session_id: str = Field(description="Echo of the session_id for client state management.")
    reranked: bool = Field(
        description="Whether Cohere reranking was applied to the retrieved context.",
    )
    retrieval_count: int = Field(
        description="Number of context chunks used for generation.",
    )

    # Sprint 5: whether cached generation was used
    cache_used: bool = Field(
        default=False,
        description="True if Gemini context caching was used for this response.",
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (retrieval latency, model used, etc.).",
    )
