"""
Security package — Sprint 4
Exports: mask_pii, check_guardrails, wrap_with_sandwich, run_security_pipeline
"""
from rag.security.pii_masker import mask_pii, is_safe_for_llm, PIIMaskResult
from rag.security.guardrails import check_guardrails, check_guardrails_sync, wrap_with_sandwich
from rag.security.middleware import run_security_pipeline, run_security_pipeline_sync

__all__ = [
    "mask_pii",
    "is_safe_for_llm",
    "PIIMaskResult",
    "check_guardrails",
    "check_guardrails_sync",
    "wrap_with_sandwich",
    "run_security_pipeline",
    "run_security_pipeline_sync",
]
