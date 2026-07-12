"""
apps/studylab/services.py — AI-powered answer generation.

AI Integration: RAG LangGraph Socratic Tutor Pipeline
Security Integration: PII masking + multi-layer guardrails

Contract with views.py (DO NOT CHANGE THIS SIGNATURE):
    answer_question(session: StudySession, question: str) -> ChatMessage

The view calls this function synchronously and expects a saved ChatMessage back.
All async RAG operations are bridged via asgiref.sync.async_to_sync().
"""

from __future__ import annotations

import logging
import threading

from django.conf import settings as django_settings

from .models import ChatMessage, MessageSource

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Public API — called by views.py
# ─────────────────────────────────────────────────────────────────────────────

def answer_question(session, question: str) -> ChatMessage:
    """
    Generate a Socratic AI tutoring response.

    Routes to the full LangGraph pipeline when API keys are configured,
    otherwise falls back to the keyword-based mock (no external API calls).
    """
    if _rag_available():
        return _rag_answer(session, question)
    logger.warning(
        "RAG not configured (missing API keys). Using keyword fallback for session %s.",
        session.id,
    )
    return _fallback_answer(session, question)


# ─────────────────────────────────────────────────────────────────────────────
# RAG Path — LangGraph Socratic Tutor
# ─────────────────────────────────────────────────────────────────────────────

def _rag_answer(session, question: str) -> ChatMessage:
    """Full RAG pipeline: security → LangGraph → citation bridging → async log."""
    from asgiref.sync import async_to_sync

    from rag.agents.graph import get_tutor_graph
    from rag.security.middleware import run_security_pipeline

    graph = get_tutor_graph()

    # ── 1. Security pipeline: PII masking + guardrail check ──────────────────
    try:
        security = async_to_sync(run_security_pipeline)(
            query=question,
            course_id=session.course.code.lower(),
            use_llm_guardrail=True,
        )
    except Exception as exc:
        logger.error("Security pipeline error: %s — proceeding without masking.", exc)
        # Fail open: build a no-op result from the actual dataclass
        from rag.security.middleware import SecurityPipelineResult
        security = SecurityPipelineResult(
            blocked=False,
            block_message="",
            safe_query=question,
        )

    # ── 2. Return guardrail refusal immediately (no LLM call) ─────────────
    if security.blocked:
        logger.warning(
            "Query blocked by guardrails: session=%s category=%s",
            session.id, security.guardrail_category,
        )
        return ChatMessage.objects.create(
            session=session,
            role="assistant",
            content=security.block_message,
        )

    # ── 3. Retrieve conversation history from Django DB ────────────────────
    history = list(
        session.messages.order_by("created_at")
        .values("role", "content")[-10:]
    )

    # ── 4. Build Pinecone namespace (same formula used by ingestion) ────────
    course_id = session.course.code.lower().replace(" ", "-")

    # ── 5. Assemble initial TutorState ─────────────────────────────────────
    initial_state: dict = {
        "query": security.safe_query,
        "course_id": course_id,
        "conversation_history": history,
        "cache_name": None,
        **security.to_state_fields(),  # injects pii_detected, pii_entities, guardrail_triggered, guardrail_category
    }

    # ── 6. Invoke LangGraph (async → sync bridge) ──────────────────────────
    graph_config = {"configurable": {"thread_id": str(session.id)}}
    try:
        final_state = async_to_sync(graph.ainvoke)(
            initial_state, config=graph_config
        )
    except Exception as exc:
        logger.error(
            "LangGraph invocation failed for session %s: %s",
            session.id, exc, exc_info=True,
        )
        return ChatMessage.objects.create(
            session=session,
            role="assistant",
            content=(
                "I'm having a little trouble processing your question right now. "
                "Could you rephrase it or try again in a moment?"
            ),
        )

    response_text = final_state.get("response") or (
        "I couldn't generate a response. Please try again."
    )

    # ── 7. Persist assistant ChatMessage ───────────────────────────────────
    msg = ChatMessage.objects.create(
        session=session,
        role="assistant",
        content=response_text,
    )

    # ── 8. Bridge RAG citations → Django MessageSource records ─────────────
    _create_sources(msg, session, final_state.get("source_references", []))

    # ── 9. Fire-and-forget: RAGAS scoring + interaction logging ───────────
    _schedule_background_logging(
        session_id=str(session.id),
        course_id=course_id,
        safe_query=security.safe_query,
        response_text=response_text,
        final_state=final_state,
    )

    return msg


def _create_sources(msg: ChatMessage, session, source_refs: list) -> None:
    """
    Map RAG source_references back to Django CourseMaterial instances.

    source_refs format: [{"file_name": str, "page_number": int, "excerpt": str}]
    """
    if not source_refs:
        return

    sources_to_create = []
    for ref in source_refs:
        if not isinstance(ref, dict):
            continue

        file_name = ref.get("file_name", "")
        material = None

        if file_name:
            # Match by file_name (strip extension for robustness)
            stem = file_name.rsplit(".", 1)[0] if "." in file_name else file_name
            material = (
                session.course.materials
                .filter(status="ready", file_name__icontains=stem)
                .first()
            )

        sources_to_create.append(MessageSource(
            message=msg,
            material=material,           # None is acceptable (SET_NULL)
            page=int(ref.get("page_number") or ref.get("page") or 0),
            snippet=str(ref.get("excerpt", ""))[:240],
        ))

    if sources_to_create:
        MessageSource.objects.bulk_create(sources_to_create, ignore_conflicts=True)


def _schedule_background_logging(
    session_id: str,
    course_id: str,
    safe_query: str,
    response_text: str,
    final_state: dict,
) -> None:
    """Run RAGAS scoring + interaction logging in a daemon thread (never blocks response)."""

    context_chunks = final_state.get("context_chunks", [])
    bloom_level = final_state.get("bloom_level_used", "understand")
    cache_used = bool(final_state.get("cache_used", False))
    verifier_passed = bool(final_state.get("verifier_passed", True))

    def _run():
        try:
            import asyncio
            from rag.evaluation.ragas_scorer import score_interaction
            from rag.evaluation.interaction_logger import log_interaction

            context_texts = [
                (c.get("text", "") if isinstance(c, dict) else str(c))
                for c in context_chunks
            ]

            async def _async_run():
                scores = await score_interaction(
                    query=safe_query,
                    answer=response_text,
                    contexts=context_texts,
                )
                await log_interaction(
                    session_id=session_id,
                    course_id=course_id,
                    query=safe_query,
                    response=response_text,
                    context_count=len(context_chunks),
                    bloom_level=bloom_level,
                    cache_used=cache_used,
                    verifier_passed=verifier_passed,
                    ragas_scores=scores,
                )

            asyncio.run(_async_run())

        except Exception as exc:
            logger.warning("Background RAGAS/logging failed (non-fatal): %s", exc)

    t = threading.Thread(target=_run, daemon=True, name="rag-logging")
    t.start()


# ─────────────────────────────────────────────────────────────────────────────
# Fallback Path — Keyword-based mock (original stub, kept as safety net)
# ─────────────────────────────────────────────────────────────────────────────

def _rag_available() -> bool:
    return bool(
        getattr(django_settings, "GOOGLE_API_KEY", "")
        and getattr(django_settings, "PINECONE_API_KEY", "")
    )


def _fallback_answer(session, question: str) -> ChatMessage:
    """
    Keyword-overlap retrieval + template response.
    Used when API keys are absent or RAG is disabled.
    No external API calls — always works offline.
    """
    chunks = _retrieve_keywords(session.course_id, question)

    if chunks:
        citations = ", ".join(
            f"{c.material.file_name} (Page {c.page})" for c in chunks[:2]
        )
        answer = (
            f"Hello! I am Acadexis, your academic AI tutor. "
            f"Based on course materials in **{citations}**, "
            f"here is what I found for *\"{question}\"*:\n\n"
        )
        for c in chunks[:2]:
            snippet = c.content.strip()
            if snippet:
                answer += f"> ... {snippet} ...\n\n"
        answer += (
            "Is there anything specific from these pages you would like me to "
            "explain further?"
        )
    else:
        answer = (
            "I am Acadexis, your AI tutor. I couldn't find any specific matches "
            "for your question in the course materials. "
            "Could you please rephrase or try another query?"
        )

    msg = ChatMessage.objects.create(session=session, role="assistant", content=answer)
    MessageSource.objects.bulk_create([
        MessageSource(message=msg, material=c.material, page=c.page, snippet=c.content[:240])
        for c in chunks
    ])
    return msg


def _retrieve_keywords(course_id, question: str, k: int = 5) -> list:
    """Original keyword overlap retrieval — no pgvector required."""
    from apps.courses.models import MaterialChunk

    chunks = MaterialChunk.objects.filter(
        material__course_id=course_id,
        material__status="ready",
    ).select_related("material")

    if not chunks.exists():
        return []

    words = [w.lower() for w in question.split() if len(w) > 2]
    if not words:
        return list(chunks[:k])

    ranked = []
    for chunk in chunks:
        score = sum(1 for w in words if w in chunk.content.lower())
        if score > 0:
            ranked.append((score, chunk))

    ranked.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in ranked[:k]]