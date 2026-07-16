"""
Acadexis — Verifier Agent Node (Sprint 4, Step 4.3)
====================================================
Implements a "Verifier" LangGraph node that audits the PedagogicalAgent's
output for hallucinations and curriculum misalignment before the response
reaches the student.

Why a Verifier Agent?
---------------------
The PedagogicalAgent uses Gemini 1.5 Pro (high capability) but can still:
  1. Synthesise plausible-sounding but incorrect facts
  2. Reference concepts not present in the retrieved context
  3. Subtly violate the Socratic constraint (e.g. answer a question directly)

The VerifierAgent uses Gemini 1.5 Flash (fast, cheaper) to perform a
lightweight "hallucination audit" — comparing the generated response against
the retrieved context chunks to catch these failures BEFORE they reach students.

Verification Dimensions:
------------------------
  1. GROUNDEDNESS   — Is every factual claim supported by the context?
  2. SOCRATIC_COMPLIANCE — Does the response ask guiding questions? (no direct answers)
  3. CITATION_ACCURACY — Are cited sources real chunks in context?
  4. TOPIC_RELEVANCE — Is the response topically aligned with the query?

Output:
-------
The VerifierAgent writes to TutorState:
  - verifier_passed: bool
  - verifier_score: float (0.0–1.0, aggregate confidence)
  - verifier_flags: list[str] (failure reasons if any)
  - response: (may be REPLACED with a safe fallback if verification fails)

Graph Integration:
------------------
The VerifierAgent is inserted as a new node AFTER the PedagogicalAgent:

    pedagogical_agent → verifier_agent → [END | error_handler]

If the verifier detects a hallucination or Socratic violation:
  - The flawed response is discarded
  - A safe fallback message is written to state["response"]
  - The failure is logged with full details for RAGAS evaluation (Sprint 7)

Performance:
    Average verification latency: ~350ms (Gemini Flash)
    This is acceptable as it runs AFTER the main generation (~2s)
    and prevents hallucinations from reaching students.
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Verification Result (internal only — not part of TutorState)
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field


@dataclass
class VerificationResult:
    """Structured output from the verifier LLM call."""
    passed: bool
    score: float                            # 0.0 (definitely hallucinated) – 1.0 (fully grounded)
    flags: list[str] = field(default_factory=list)
    groundedness: float = 1.0
    socratic_compliance: float = 1.0
    topic_relevance: float = 1.0
    raw_verdict: str = ""


# ---------------------------------------------------------------------------
# Verifier Prompt
# ---------------------------------------------------------------------------

_VERIFIER_SYSTEM_PROMPT = """You are a strict hallucination auditor for an academic AI tutoring system.

Your job is to evaluate whether a generated AI response:
1. Is GROUNDED in the provided context (no invented facts)
2. COMPLIES with the Socratic method (asks guiding questions, does NOT give direct answers)
3. Is TOPICALLY RELEVANT to the student's question
4. Has ACCURATE CITATIONS (only cites sources that exist in the context)

Be strict. A response that answers a question directly (instead of guiding the student)
is a SOCRATIC VIOLATION even if all facts are correct.

You will receive:
- The student's question
- The retrieved context chunks (these are the ONLY allowed sources)
- The AI tutor's generated response

Return ONLY a JSON object with this exact structure:
{
  "passed": true or false,
  "score": 0.0 to 1.0,
  "groundedness": 0.0 to 1.0,
  "socratic_compliance": 0.0 to 1.0,
  "topic_relevance": 0.0 to 1.0,
  "flags": ["list of specific failure reasons, empty if passed"],
  "verdict": "PASS or FAIL with brief explanation"
}

Scoring thresholds:
  - groundedness < 0.7: FAIL (hallucination detected)
  - socratic_compliance < 0.6: FAIL (direct answer given)
  - topic_relevance < 0.5: FAIL (off-topic response)
  - Any single FAIL makes overall "passed" = false
"""

_VERIFIER_USER_TEMPLATE = """STUDENT QUESTION:
{query}

RETRIEVED CONTEXT (only these facts are allowed):
{context}

AI TUTOR RESPONSE TO AUDIT:
{response}

CITATIONS IN RESPONSE:
{citations}

Audit the response now. Return ONLY the JSON object."""


# ---------------------------------------------------------------------------
# Context Formatter (for verifier prompt)
# ---------------------------------------------------------------------------

def _format_context_for_verifier(context_chunks: list[dict[str, Any]]) -> str:
    """
    Format retrieved chunks into a compact representation for the verifier prompt.
    Truncates long chunks to conserve tokens (verifier doesn't need full text).
    """
    if not context_chunks:
        return "(no context retrieved)"

    lines = []
    for i, chunk in enumerate(context_chunks[:10], start=1):  # Cap at 10 chunks
        source = chunk.get("metadata", {}).get("filename", "unknown")
        page = chunk.get("metadata", {}).get("page_number", "?")
        text = chunk.get("text", chunk.get("content", ""))[:300]  # 300 chars max
        lines.append(f"[Chunk {i}] Source: {source}, Page {page}\n{text}...")

    return "\n\n".join(lines)


def _format_citations_for_verifier(citations: list[dict[str, Any]]) -> str:
    """Format citations list for inclusion in the verifier prompt."""
    if not citations:
        return "(no citations)"
    return "; ".join(
        f"{c.get('filename', 'unknown')} p.{c.get('page', '?')}"
        for c in citations
    )


# ---------------------------------------------------------------------------
# Core Verification Logic
# ---------------------------------------------------------------------------

async def _run_verification(
    query: str,
    response: str,
    context_chunks: list[dict[str, Any]],
    citations: list[dict[str, Any]],
) -> VerificationResult:
    """
    Call Gemini Flash to audit the generated response.

    Args:
        query:          The student's original question.
        response:       The PedagogicalAgent's generated response.
        context_chunks: Retrieved chunks (from RetrieverAgent).
        citations:      Citations emitted by the PedagogicalAgent.

    Returns:
        VerificationResult with pass/fail verdict and dimension scores.
    """
    if not response or not response.strip():
        return VerificationResult(
            passed=False,
            score=0.0,
            flags=["Empty response from PedagogicalAgent"],
        )

    # Build the verification prompt
    context_str = _format_context_for_verifier(context_chunks)
    citations_str = _format_citations_for_verifier(citations)

    user_message = _VERIFIER_USER_TEMPLATE.format(
        query=query,
        context=context_str,
        response=response[:2000],   # Cap response length for verifier
        citations=citations_str,
    )

    try:
        from google import genai as google_genai
        from rag.config import settings

        client = google_genai.Client(api_key=settings.google_api_key)

        full_prompt = f"{_VERIFIER_SYSTEM_PROMPT}\n\n{user_message}"
        api_response = client.models.generate_content(
            model="gemini-1.5-flash",  # Fast + cheap — appropriate for auditing
            contents=full_prompt,
        )

        raw = api_response.text.strip()
        # Strip markdown code fences
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        parsed = json.loads(raw)

        passed = bool(parsed.get("passed", True))
        score = float(parsed.get("score", 1.0))
        flags = parsed.get("flags", [])
        groundedness = float(parsed.get("groundedness", 1.0))
        socratic = float(parsed.get("socratic_compliance", 1.0))
        relevance = float(parsed.get("topic_relevance", 1.0))
        verdict = parsed.get("verdict", "")

        logger.info(
            "VerifierAgent: passed=%s score=%.2f groundedness=%.2f socratic=%.2f "
            "relevance=%.2f flags=%s",
            passed, score, groundedness, socratic, relevance, flags,
        )

        return VerificationResult(
            passed=passed,
            score=score,
            flags=flags if isinstance(flags, list) else [str(flags)],
            groundedness=groundedness,
            socratic_compliance=socratic,
            topic_relevance=relevance,
            raw_verdict=verdict,
        )

    except json.JSONDecodeError as exc:
        logger.warning("VerifierAgent: JSON parse error from LLM: %s. Defaulting to PASS.", exc)
        # Fail open on JSON parse error — don't block students
        return VerificationResult(passed=True, score=0.8, flags=["verifier_json_error"])

    except Exception as exc:
        logger.error("VerifierAgent: API call failed: %s. Defaulting to PASS.", exc)
        return VerificationResult(passed=True, score=0.5, flags=["verifier_api_error"])


# ---------------------------------------------------------------------------
# Fallback Response Generator
# ---------------------------------------------------------------------------

_VERIFICATION_FAILURE_RESPONSE = (
    "I want to make sure I give you the most accurate guidance possible. "
    "Let me approach this differently — rather than building on my previous response, "
    "could you tell me what specific aspect of this topic you're most confused about? "
    "Starting from what you already know will help me guide you more effectively."
)


# ---------------------------------------------------------------------------
# LangGraph Node
# ---------------------------------------------------------------------------

async def verifier_agent(state: dict) -> dict:
    """
    LangGraph node: audits the PedagogicalAgent's response for hallucinations
    and Socratic compliance violations.

    Reads from state:
        - query: str
        - response: str (from PedagogicalAgent)
        - context_chunks: list[RetrievedChunk]
        - citations: list[dict]
        - error: Optional[str]

    Writes to state:
        - verifier_passed: bool
        - verifier_score: float
        - verifier_flags: list[str]
        - response: str (replaced with fallback if verification fails)
        - reasoning_trace: str (appended with verification result)

    Design: Fail open — if the verifier itself fails (API error, timeout),
    the original response is preserved and the failure is logged. This prevents
    the verifier from becoming a single point of failure.
    """
    # ---- Skip if a previous error already occurred ----------------------------
    if state.get("error"):
        logger.debug("VerifierAgent: skipping — upstream error already set.")
        return {
            "verifier_passed": False,
            "verifier_score": 0.0,
            "verifier_flags": ["upstream_error"],
        }

    query = state.get("query", "")
    response = state.get("response", "")
    context_chunks = state.get("context_chunks", [])
    citations = state.get("citations", [])
    existing_trace = state.get("reasoning_trace", "")

    logger.info(
        "VerifierAgent: auditing response (query_len=%d, response_len=%d, chunks=%d)",
        len(query),
        len(response),
        len(context_chunks),
    )

    # Run the LLM-based audit
    result = await _run_verification(
        query=query,
        response=response,
        context_chunks=context_chunks,
        citations=citations,
    )

    # Build the state update
    verification_trace = (
        f"\n[VerifierAgent] passed={result.passed}, score={result.score:.2f}, "
        f"groundedness={result.groundedness:.2f}, socratic={result.socratic_compliance:.2f}, "
        f"topic_relevance={result.topic_relevance:.2f}, flags={result.flags}"
    )

    state_update: dict = {
        "verifier_passed": result.passed,
        "verifier_score": result.score,
        "verifier_flags": result.flags,
        "reasoning_trace": existing_trace + verification_trace,
    }

    if not result.passed:
        logger.warning(
            "VerifierAgent: FAILED — replacing response. Flags: %s",
            result.flags,
        )
        # Replace the flawed response with a safe fallback
        state_update["response"] = _VERIFICATION_FAILURE_RESPONSE

    return state_update
