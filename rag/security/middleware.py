"""
Acadexis — Security Middleware (Sprint 4)
=========================================
FastAPI middleware / dependency that runs the Sprint 4 security pipeline
on every chat request:

  1. PII Masking   → masks student names, matric numbers, emails BEFORE LLM
  2. Guardrail Check → detects jailbreak/academic dishonesty BEFORE graph
  3. State enrichment → writes security metadata into TutorState

This module is imported by api/chat.py and called before invoking the
LangGraph tutoring pipeline.

Usage:
    from security.middleware import run_security_pipeline, SecurityPipelineResult

    result = await run_security_pipeline(query=query, course_id=course_id)
    if result.blocked:
        return ChatResponse(response=result.block_message, ...)

    # Use result.safe_query (PII-masked) for the graph invocation
    state_input["query"] = result.safe_query
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from rag.security.guardrails import GuardrailResult, check_guardrails, check_guardrails_sync
from rag.security.pii_masker import PIIMaskResult, mask_pii

logger = logging.getLogger(__name__)


@dataclass
class SecurityPipelineResult:
    """
    Result of the full security pipeline for a single chat request.
    Consumed by the API endpoint to decide whether to proceed or block.
    """
    # ---- Core decision -------------------------------------------------------
    blocked: bool                           # True → return block_message to student
    block_message: str = ""                 # Student-facing refusal message

    # ---- Sanitised query (PII-masked) ----------------------------------------
    safe_query: str = ""                    # Use this in LangGraph, not the raw query

    # ---- PII metadata (written to TutorState) --------------------------------
    pii_detected: bool = False
    pii_entities: list[str] = field(default_factory=list)

    # ---- Guardrail metadata (written to TutorState) -------------------------
    guardrail_triggered: bool = False
    guardrail_category: Optional[str] = None

    # ---- For LangGraph state population -------------------------------------
    def to_state_fields(self) -> dict:
        """
        Return a dict of TutorState fields that the security layer populates.
        Merge this into the initial state dict before graph.ainvoke().
        """
        return {
            "pii_detected": self.pii_detected,
            "pii_entities": self.pii_entities,
            "guardrail_triggered": self.guardrail_triggered,
            "guardrail_category": self.guardrail_category,
        }


async def run_security_pipeline(
    query: str,
    course_id: str = "",
    use_llm_guardrail: bool = True,
) -> SecurityPipelineResult:
    """
    Run the full Sprint 4 security pipeline on a student query.

    Steps:
      1. PII Masking (Presidio + custom patterns)
      2. Guardrail Check (pattern scan + optional Gemini Flash classifier)

    Args:
        query:            Raw student query (as received from API).
        course_id:        Used in guardrail context narrowing.
        use_llm_guardrail: Whether to call Gemini Flash for borderline inputs.

    Returns:
        SecurityPipelineResult — check .blocked before invoking LangGraph.
    """
    # ---- Step 1: PII Masking -------------------------------------------------
    pii_result: PIIMaskResult = mask_pii(query)
    safe_query = pii_result.masked_text

    if pii_result.pii_found:
        logger.info(
            "SecurityPipeline: PII masked from query (entities=%s)",
            pii_result.entity_types,
        )

    # ---- Step 2: Guardrail Check --------------------------------------------
    guardrail_result: GuardrailResult = await check_guardrails(
        text=safe_query,
        use_llm_fallback=use_llm_guardrail,
    )

    if guardrail_result.is_jailbreak:
        logger.warning(
            "SecurityPipeline: BLOCKED query (category=%s, confidence=%.2f, method=%s)",
            guardrail_result.category,
            guardrail_result.confidence,
            guardrail_result.detection_method,
        )
        return SecurityPipelineResult(
            blocked=True,
            block_message=guardrail_result.student_message,
            safe_query=safe_query,
            pii_detected=pii_result.pii_found,
            pii_entities=pii_result.entity_types,
            guardrail_triggered=True,
            guardrail_category=guardrail_result.category.value if guardrail_result.category else None,
        )

    # ---- All clear -----------------------------------------------------------
    return SecurityPipelineResult(
        blocked=False,
        safe_query=safe_query,
        pii_detected=pii_result.pii_found,
        pii_entities=pii_result.entity_types,
        guardrail_triggered=False,
        guardrail_category=None,
    )


def run_security_pipeline_sync(query: str) -> SecurityPipelineResult:
    """
    Synchronous variant — uses pattern-only guardrails (no LLM call).
    Use in middleware or request validation hooks where async is unavailable.
    """
    pii_result: PIIMaskResult = mask_pii(query)
    safe_query = pii_result.masked_text

    from security.guardrails import check_guardrails_sync
    guardrail_result = check_guardrails_sync(safe_query)

    if guardrail_result.is_jailbreak:
        return SecurityPipelineResult(
            blocked=True,
            block_message=guardrail_result.student_message,
            safe_query=safe_query,
            pii_detected=pii_result.pii_found,
            pii_entities=pii_result.entity_types,
            guardrail_triggered=True,
            guardrail_category=guardrail_result.category.value if guardrail_result.category else None,
        )

    return SecurityPipelineResult(
        blocked=False,
        safe_query=safe_query,
        pii_detected=pii_result.pii_found,
        pii_entities=pii_result.entity_types,
    )
