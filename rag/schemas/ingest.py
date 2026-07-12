"""
Acadexis — Pydantic Schemas for /api/ingest (Sprint 1)
=======================================================
Defines the structured request/response models for the ingestion API.

Why we keep schemas separate from endpoint code:
- Reusable: the same IngestJobStatus schema will be used by a
  /api/ingest/{job_id}/status polling endpoint in Sprint 3.
- Testable: schema validation can be unit-tested without spinning up FastAPI.
- Documentation: Pydantic models automatically generate the OpenAPI spec
  that appears at /docs — crucial for the defense panel demo.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IngestStatus(str, Enum):
    """Valid states for an ingestion job."""
    ACCEPTED = "accepted"        # File received, processing queued
    PROCESSING = "processing"    # Actively embedding and upserting
    COMPLETED = "completed"      # All chunks in Pinecone
    PARTIAL = "partial"          # Some batches failed; others succeeded
    FAILED = "failed"            # Complete failure (parse error, etc.)


class IngestResponse(BaseModel):
    """
    Immediate response from POST /api/ingest.

    The client gets this immediately — before embedding is complete.
    Long-polling or WebSocket status updates (Sprint 3) use IngestJobStatus.
    """
    job_id: str = Field(
        ...,
        description="Unique UUID for this ingestion job. Use for status polling.",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    status: IngestStatus = Field(
        default=IngestStatus.ACCEPTED,
        description="Current job status.",
    )
    filename: str = Field(
        ...,
        description="Original filename as uploaded.",
        examples=["lecture_03_recursion.pdf"],
    )
    course_id: str = Field(
        ...,
        description="Course namespace the file was ingested into.",
        examples=["csc501-dsa"],
    )
    message: str = Field(
        ...,
        description="Human-readable status message.",
        examples=["Ingestion queued. Processing 24 pages in background."],
    )
    page_count: int | None = Field(
        default=None,
        description="Number of pages detected (available after parsing).",
    )
    images_extracted: int = Field(
        default=0,
        description=(
            "Number of images found in the PDF (Sprint 8). "
            "0 for text-only PDFs or when multimodal_enabled=False."
        ),
    )
    multimodal_chunks: int = Field(
        default=0,
        description=(
            "Number of multimodal (image+text) chunks queued for embedding. "
            "Each qualifying image produces one multimodal chunk."
        ),
    )
    uploaded_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp of receipt.",
    )


class IngestJobStatus(BaseModel):
    """
    Detailed job status for polling endpoint (Sprint 3).
    Returned by GET /api/ingest/{job_id}/status.
    """
    job_id: str
    status: IngestStatus
    filename: str
    course_id: str
    total_chunks: int | None = None
    upserted_chunks: int | None = None
    failed_batches: int | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ErrorDetail(BaseModel):
    """
    Standard error payload for all 4xx/5xx responses.

    Having a consistent error schema means the frontend can always parse
    the error body without branching on HTTP status code type.
    """
    error_code: str = Field(
        ...,
        description="Machine-readable error code.",
        examples=["PDF_PARSE_ERROR", "FILE_TOO_LARGE", "UNSUPPORTED_MIME"],
    )
    message: str = Field(
        ...,
        description="Human-readable error description.",
    )
    details: dict[str, Any] | None = Field(
        default=None,
        description="Optional structured details (e.g., field-level validation errors).",
    )
