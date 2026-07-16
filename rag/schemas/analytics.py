"""
Acadexis — Analytics Schemas (Sprint 7)
=======================================
Pydantic models for the analytics API layer.

Two-layer architecture (Kaizen/Standardised Work):
  - Pydantic at the HTTP boundary (request/response)
  - TypedDict inside the graph (TutorState)
  - Plain dicts in the DB layer (aiosqlite rows)

Schemas defined here:
  RagasScores           — 4-metric RAG Triad bundle
  HeatmapEntry          — one topic row in the struggle heatmap
  HeatmapResponse       — the full /analytics/heatmap payload
  InteractionRecord     — single logged chat turn (for admin view)
  InteractionListResponse — paginated /analytics/interactions payload
  RagasSummaryResponse  — aggregate RAGAS scores across a course
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# RAGAS Scores
# ─────────────────────────────────────────────────────────────────────────────

class RagasScores(BaseModel):
    """
    The RAG Triad evaluation scores from a single interaction.

    All four fields are Optional because:
      - RAGAS scoring is async background work; it may not yet be complete.
      - If RAGAS_ENABLED=false or scoring fails, scores remain None.
      - Frontend shows a loading/unavailable state for None scores.

    Interpretation:
      context_precision — are retrieved chunks relevant? (retriever quality)
      context_recall    — was all needed info retrieved? (coverage)
      faithfulness      — does the answer stay grounded? (anti-hallucination)
      answer_relevancy  — does the answer address the question?
    """
    context_precision: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Fraction of retrieved context that is relevant to the query.",
    )
    context_recall: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Fraction of ground-truth information covered by retrieved context.",
    )
    faithfulness: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Fraction of answer claims that are grounded in retrieved context.",
    )
    answer_relevancy: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="How directly the answer addresses the student's question.",
    )

    @property
    def is_complete(self) -> bool:
        """True only if all four scores were successfully computed."""
        return all(
            v is not None
            for v in [
                self.context_precision,
                self.context_recall,
                self.faithfulness,
                self.answer_relevancy,
            ]
        )

    @property
    def hallucination_risk(self) -> str:
        """
        Human-readable risk level derived from faithfulness score.
        Used by the lecturer dashboard for quick visual triage.
        """
        if self.faithfulness is None:
            return "unknown"
        if self.faithfulness >= 0.85:
            return "low"
        if self.faithfulness >= 0.60:
            return "medium"
        return "high"


# ─────────────────────────────────────────────────────────────────────────────
# Struggle Heatmap
# ─────────────────────────────────────────────────────────────────────────────

class HeatmapEntry(BaseModel):
    """One topic row in the Struggle Heatmap."""
    topic: str = Field(
        description="Topic label (bloom_level_used in Sprint 7; full topic in Sprint 8+)."
    )
    failure_rate: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of interactions with faithfulness < 0.5 (proxy for struggle).",
    )
    total_attempts: int = Field(
        ge=0,
        description="Total number of student interactions for this topic.",
    )
    students_affected: int = Field(
        ge=0,
        description="Number of distinct sessions that touched this topic.",
    )


class HeatmapResponse(BaseModel):
    """Full response payload for GET /api/analytics/heatmap."""
    course_id: str
    total_interactions: int = Field(ge=0)
    heatmap: list[HeatmapEntry] = Field(
        default_factory=list,
        description="Topics ranked by failure_rate descending.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Interaction Log
# ─────────────────────────────────────────────────────────────────────────────

class InteractionRecord(BaseModel):
    """
    A single logged interaction — the full audit record.
    Used by GET /api/analytics/interactions for the admin/debug view.
    """
    id: int
    session_id: str
    course_id: str
    query: str
    response: str
    bloom_level: str
    cache_used: bool
    verifier_passed: bool
    ragas_scores: RagasScores
    timestamp: datetime
    context_count: int = Field(
        ge=0,
        description="Number of context chunks used for this interaction.",
    )


class InteractionListResponse(BaseModel):
    """Paginated response for GET /api/analytics/interactions."""
    course_id: str
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)
    interactions: list[InteractionRecord] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# RAGAS Aggregate Summary
# ─────────────────────────────────────────────────────────────────────────────

class RagasSummaryResponse(BaseModel):
    """
    Course-level aggregate RAGAS scores.
    Used by GET /api/analytics/ragas_summary for the lecturer dashboard.
    """
    course_id: str
    interaction_count: int = Field(ge=0)
    scored_count: int = Field(
        ge=0,
        description="Interactions where RAGAS scoring completed successfully.",
    )
    mean_context_precision: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    mean_context_recall: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    mean_faithfulness: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    mean_answer_relevancy: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    hallucination_risk: str = Field(
        default="unknown",
        description="Aggregate risk level: low | medium | high | unknown.",
    )
