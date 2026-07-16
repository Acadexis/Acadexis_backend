"""
Acadexis — LangGraph State Schema (Sprint 3)
=============================================
Defines the TypedDict that flows through the entire agent graph.

Design Philosophy:
------------------
In LangGraph, the "State" is the single source of truth for the entire
conversation. Every node reads from and writes to this dict. Nothing is
stored outside of it during a graph run.

This is analogous to Redux State in frontend development:
  - Unidirectional data flow
  - Immutable updates (LangGraph merges diffs, not full replacements)
  - Full observability: the state at any step can be printed for debugging

State Field Ownership:
----------------------
  query          → set by the API caller; read by RetrieverAgent
  context_chunks → set by RetrieverAgent; read by PedagogicalAgent
  student_profile → set by ProfilerAgent; read by PedagogicalAgent
  response       → set by PedagogicalAgent; returned to the API caller
  route          → set by the router (optional); controls conditional edges
  error          → set by any node on failure; triggers error edge

Why TypedDict over Pydantic:
  - LangGraph State MUST be a TypedDict (or dataclass).
  - Pydantic models are not natively supported as LangGraph state containers.
  - We keep Pydantic for the API layer (FastAPI request/response models).
  - The state boundary is: TypedDict inside the graph, Pydantic at the edges.
"""

from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict

from rag.schemas.retrieve import RetrievedChunk


class StudentProfile(TypedDict, total=False):
    """
    Represents a student's academic profile used by the ProfilerAgent.

    Fields are optional (total=False) so the ProfilerAgent can populate
    only what it knows, and downstream nodes receive sensible defaults.

    In Sprint 3 this data comes from a hardcoded profile injected by the
    ProfilerAgent for each session. In Sprint 5, this will be fetched
    from PostgreSQL using the authenticated student's user_id.
    """
    student_id: str
    name: str
    course_id: str

    # ---- Learning Level -------------------------------------------------------
    # Bloom's taxonomy level (1=Remember, 2=Understand, 3=Apply, 4=Analyse,
    # 5=Evaluate, 6=Create). Used by the PedagogicalAgent to calibrate questions.
    bloom_level: int

    # Plain language label corresponding to bloom_level (for prompt injection).
    # e.g. "beginner", "intermediate", "advanced"
    learning_level: str

    # Self-reported or assessed learning style
    learning_style: str  # "visual" | "kinesthetic" | "auditory" | "reading-writing"

    # Number of sessions completed in this course
    sessions_completed: int

    # List of topic tags the student has already mastered.
    # The PedagogicalAgent uses this to avoid re-explaining mastered concepts.
    mastered_topics: list[str]

    # List of topic tags where the student needs reinforcement.
    weak_topics: list[str]

    # Language preference for responses
    response_language: str  # "en" | "yo" (Yoruba) | "ig" (Igbo) | "ha" (Hausa)


class TutorState(TypedDict, total=False):
    """
    The shared state flowing through the LangGraph tutoring pipeline.

    All fields are optional (total=False) — nodes only populate the fields
    they are responsible for. LangGraph merges partial dicts, so unset fields
    are not overwritten.

    Field lifecycle:
        [Caller] → query, course_id, conversation_history
        [RetrieverAgent] → context_chunks, retrieval_metadata
        [ProfilerAgent] → student_profile
        [PedagogicalAgent] → response, citations, reasoning_trace
        [Any node on error] → error, error_node
    """

    # ---- Input (set by API caller) -------------------------------------------
    query: str
    """The student's original question."""

    course_id: str
    """Course namespace for Pinecone retrieval (e.g. 'csc501-dsa')."""

    conversation_history: list[dict[str, str]]
    """
    Previous turns in the conversation: [{"role": "student"|"tutor", "content": "..."}]
    Used by the PedagogicalAgent to maintain Socratic continuity across turns.
    Passed in by the caller; the agent appends to it.
    """

    # ---- Retriever output (set by RetrieverAgent) ----------------------------
    context_chunks: list[RetrievedChunk]
    """Top-k reranked chunks from Pinecone. Fed to PedagogicalAgent."""

    retrieval_metadata: dict[str, Any]
    """Stats from retrieval: total_retrieved, reranked, latency_ms."""

    # ---- Profiler output (set by ProfilerAgent) ------------------------------
    student_profile: StudentProfile
    """Injected academic profile. Fed to PedagogicalAgent."""

    # ---- Pedagogical output (set by PedagogicalAgent) -----------------------
    response: str
    """The Socratic guiding response from the AI Tutor."""

    citations: list[dict[str, Any]]
    """
    Source citations for the response.
    Format: [{"filename": str, "page": int, "excerpt": str}]
    Used by Sprint 6 Source Badge system.
    """

    reasoning_trace: str
    """
    Internal chain-of-thought (NOT shown to student). Stored for debugging
    and for RAGAS evaluation in Sprint 7.
    """

    # ---- Control flow --------------------------------------------------------
    route: str
    """
    Set by the router node. Controls conditional edges.
    Values: "socratic" | "clarify" | "out_of_scope"
    """

    # ---- Error handling ------------------------------------------------------
    error: Optional[str]
    """Populated by any node on failure. Triggers the error edge."""

    error_node: Optional[str]
    """Which node produced the error (for logging and debugging)."""

    # ---- Sprint 4: Security layer --------------------------------------------
    pii_detected: bool
    """True if PII was detected and masked in the student's query."""

    pii_entities: list[str]
    """List of PII entity types found (e.g. ['PERSON', 'EMAIL_ADDRESS'])."""

    guardrail_triggered: bool
    """True if the jailbreak/guardrail check flagged this query."""

    guardrail_category: Optional[str]
    """Which jailbreak category triggered the guardrail (if any)."""

    verifier_passed: bool
    """True if the VerifierAgent approved the PedagogicalAgent's response."""

    verifier_score: float
    """Aggregate verification confidence score (0.0–1.0)."""

    verifier_flags: list[str]
    """Specific failure reasons from the VerifierAgent (empty if passed)."""

    # ---- Sprint 5: Context Caching -------------------------------------------
    cache_name: Optional[str]
    """
    Gemini context cache resource name for this course document.
    Populated by the /api/cache/warm endpoint or the ingestion pipeline.
    When set, the PedagogicalAgent uses cached generation (cheaper).
    None means direct (uncached) generation.
    """

    cache_used: bool
    """
    True if the PedagogicalAgent used a context cache for this response.
    Used for cost tracking and observability dashboards (Sprint 7).
    """

    # ---- Sprint 6: Structured Output -----------------------------------------
    follow_up_questions: list[str]
    """
    1–3 Socratic follow-up questions generated by the PedagogicalAgent.
    Populated from the structured JSON output (response_schema).
    Displayed as suggestion chips in the student chat UI.
    Empty list if structured output failed and fallback was used.
    """

    bloom_level_used: str
    """
    Bloom's Taxonomy level of the student's question as classified by the LLM.
    One of: remember | understand | apply | analyze | evaluate | create.
    Defaults to 'understand' if structured output is unavailable.
    """

    # ---- Sprint 7: RAGAS Evaluation ------------------------------------------
    ragas_scores: dict
    """
    RAG Triad evaluation scores computed asynchronously after the response.
    Shape: {"context_precision": float|None, "context_recall": float|None,
            "faithfulness": float|None, "answer_relevancy": float|None}

    Populated by the background log_and_score task — NOT set synchronously
    within the graph run. Defaults to an empty dict during the graph execution.
    Written to the DB by the interaction logger.

    None values mean scoring is unavailable (RAGAS_ENABLED=false, timeout,
    or ragas not installed). The system works normally without scores.
    """

    # ---- Sprint 9: Hybrid Wiki & RAG -----------------------------------------
    wiki_content: Optional[str]
    """
    Compiled Markdown Wiki for the current course (Sprint 9).
    Injected into the Pedagogical Agent's prompt for 100% recall of
    core rules (syllabus, grading rubrics, deadlines).
    None when no Wiki has been compiled for this course.
    """
