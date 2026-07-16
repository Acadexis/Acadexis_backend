"""
Acadexis — RAGAS Scorer (Sprint 7)
===================================
Async wrapper for RAGAS evaluation of single chat interactions.

Design (AI Product skill + Kaizen):
  - RAGAS calls external LLMs → treat as untrusted, slow, fallible service
  - RAGAS_ENABLED=false → returns empty scores immediately (used in CI/tests)
  - All exceptions caught → scorer NEVER propagates to chat endpoint
  - Scores are advisory — the system works without them
  - Timeout: 30s max per scoring call (RAGAS can be slow)

RAGAS 0.2 API note:
  The implementation.md spec shows the RAGAS 0.1 API (ragas.evaluate + Dataset).
  RAGAS 0.2 (current) restructured significantly. We use the 0.2 API here.
  If ragas is not installed, RAGAS_ENABLED is treated as false automatically.

Environment Variables:
  RAGAS_ENABLED   — "true" (default) | "false"
  RAGAS_TIMEOUT   — seconds before scoring times out (default: 30)
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

def _ragas_enabled() -> bool:
    """
    Check if RAGAS scoring is enabled via env var.
    Defaults to True (enabled) in production.
    Set RAGAS_ENABLED=false in test environments for fast, offline testing.

    Also returns False if the ragas package is not installed — this lets the
    rest of the system function before ragas is added to pyproject.toml.
    """
    if os.getenv("RAGAS_ENABLED", "true").lower() == "false":
        return False

    try:
        import ragas  # noqa: F401
        return True
    except ImportError:
        logger.debug("ragas not installed — RAGAS scoring disabled.")
        return False


_RAGAS_TIMEOUT = int(os.getenv("RAGAS_TIMEOUT", "30"))


# ─────────────────────────────────────────────────────────────────────────────
# Core Scorer
# ─────────────────────────────────────────────────────────────────────────────

async def score_interaction(
    query: str,
    answer: str,
    contexts: list[str],
    ground_truth: Optional[str] = None,
) -> dict[str, Optional[float]]:
    """
    Score a single interaction using the RAGAS RAG Triad.

    Returns a dict compatible with RagasScores fields:
      {
        "context_precision": float | None,
        "context_recall":    float | None,
        "faithfulness":      float | None,
        "answer_relevancy":  float | None,
      }

    All values are None if:
      - RAGAS_ENABLED=false
      - ragas is not installed
      - Scoring times out (> RAGAS_TIMEOUT seconds)
      - Any exception occurs during scoring

    The caller (background task in chat.py) treats None scores as
    "not yet available" — they are stored as NULL in the DB and
    shown as "pending" in the lecturer dashboard.
    """
    _empty: dict[str, Optional[float]] = {
        "context_precision": None,
        "context_recall": None,
        "faithfulness": None,
        "answer_relevancy": None,
    }

    if not _ragas_enabled():
        logger.debug("RAGAS scoring skipped (RAGAS_ENABLED=false or not installed).")
        return _empty

    if not contexts:
        logger.debug("RAGAS scoring skipped: no context chunks provided.")
        return _empty

    if not query.strip() or not answer.strip():
        logger.debug("RAGAS scoring skipped: empty query or answer.")
        return _empty

    try:
        scores = await asyncio.wait_for(
            _run_ragas(query, answer, contexts, ground_truth or answer),
            timeout=_RAGAS_TIMEOUT,
        )
        logger.info(
            "RAGAS scores computed: cp=%.3f cr=%.3f fa=%.3f ar=%.3f",
            scores.get("context_precision") or 0,
            scores.get("context_recall") or 0,
            scores.get("faithfulness") or 0,
            scores.get("answer_relevancy") or 0,
        )
        return scores

    except asyncio.TimeoutError:
        logger.warning("RAGAS scoring timed out after %ds — scores set to None.", _RAGAS_TIMEOUT)
        return _empty

    except Exception as exc:
        # AI Product skill: never trust external evaluation to behave perfectly
        logger.error("RAGAS scoring failed (non-fatal): %s", exc)
        return _empty


async def _run_ragas(
    query: str,
    answer: str,
    contexts: list[str],
    ground_truth: str,
) -> dict[str, Optional[float]]:
    """
    Execute the RAGAS evaluation in a thread pool (CPU-bound blocking call).

    RAGAS 0.2 API — uses SingleTurnSample and EvaluationDataset.
    Falls back gracefully if the API shape changes in future RAGAS versions.
    """
    # Run blocking RAGAS call in a thread to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _blocking_ragas, query, answer, contexts, ground_truth)


def _blocking_ragas(
    query: str,
    answer: str,
    contexts: list[str],
    ground_truth: str,
) -> dict[str, Optional[float]]:
    """
    Synchronous RAGAS evaluation — runs in a thread pool worker.

    We support two RAGAS API variants:
      1. RAGAS 0.2+: SingleTurnSample + EvaluationDataset + evaluate()
      2. RAGAS 0.1.x (legacy): Dataset.from_dict() + evaluate()
    Both are wrapped in try/except to fail gracefully.
    """
    empty: dict[str, Optional[float]] = {
        "context_precision": None,
        "context_recall": None,
        "faithfulness": None,
        "answer_relevancy": None,
    }

    try:
        # ── RAGAS 0.2 API ──────────────────────────────────────────────────
        from ragas import EvaluationDataset, SingleTurnSample, evaluate  # type: ignore
        from ragas.metrics import (  # type: ignore
            AnswerRelevancy,
            ContextPrecision,
            ContextRecall,
            Faithfulness,
        )

        sample = SingleTurnSample(
            user_input=query,
            response=answer,
            retrieved_contexts=contexts,
            reference=ground_truth,
        )
        dataset = EvaluationDataset(samples=[sample])
        result = evaluate(
            dataset=dataset,
            metrics=[
                ContextPrecision(),
                ContextRecall(),
                Faithfulness(),
                AnswerRelevancy(),
            ],
        )

        # RAGAS 0.2 returns an EvaluationResult with a .to_pandas() or dict access
        scores_df = result.to_pandas()
        row = scores_df.iloc[0] if not scores_df.empty else {}

        return {
            "context_precision": _safe_float(row.get("context_precision")),
            "context_recall": _safe_float(row.get("context_recall")),
            "faithfulness": _safe_float(row.get("faithfulness")),
            "answer_relevancy": _safe_float(row.get("answer_relevancy")),
        }

    except ImportError:
        # RAGAS 0.2 not installed — try legacy 0.1 API
        pass
    except Exception as exc:
        logger.error("RAGAS 0.2 evaluate failed: %s", exc)
        return empty

    try:
        # ── RAGAS 0.1 legacy API ───────────────────────────────────────────
        from datasets import Dataset  # type: ignore
        from ragas import evaluate  # type: ignore
        from ragas.metrics import (  # type: ignore
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )

        dataset = Dataset.from_dict({
            "question": [query],
            "answer": [answer],
            "contexts": [contexts],
            "ground_truth": [ground_truth],
        })

        result = evaluate(
            dataset,
            metrics=[context_precision, context_recall, faithfulness, answer_relevancy],
        )

        return {
            "context_precision": _safe_float(result.get("context_precision")),
            "context_recall": _safe_float(result.get("context_recall")),
            "faithfulness": _safe_float(result.get("faithfulness")),
            "answer_relevancy": _safe_float(result.get("answer_relevancy")),
        }

    except Exception as exc:
        logger.error("RAGAS 0.1 legacy evaluate failed: %s", exc)
        return empty


def _safe_float(value: object) -> Optional[float]:
    """
    Safely convert a RAGAS result value to float in [0.0, 1.0].
    Returns None for NaN, None, or out-of-range values.
    """
    if value is None:
        return None
    try:
        f = float(value)
        if f != f:  # NaN check (NaN != NaN)
            return None
        return round(max(0.0, min(1.0, f)), 4)
    except (TypeError, ValueError):
        return None
