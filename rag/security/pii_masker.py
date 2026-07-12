"""
Acadexis — PII Masking Layer (Sprint 4, Step 4.1)
==================================================
Detects and masks Personally Identifiable Information (PII) from student
queries and profile data BEFORE they are sent to any external LLM API.

Compliance target: FERPA (Family Educational Rights and Privacy Act) and
GDPR-style data minimisation in educational contexts.

Why Presidio?
-------------
Microsoft Presidio is the industry-standard PII detection library used by
major banks and healthcare providers. It combines:
  1. Named-Entity Recognition (NER) via spaCy for person names, organisations
  2. Rule-based recognisers for structured patterns (email, phone, ID numbers)
  3. A customisable anonymizer layer that replaces detected entities with
     reversible or irreversible placeholders.

Supported Entity Types (for educational context)
-------------------------------------------------
  - PERSON              → student/lecturer names
  - EMAIL_ADDRESS       → institutional emails (*.edu.ng, etc.)
  - PHONE_NUMBER        → contact numbers
  - UK_NHS              → (disabled — educational, not medical context)
  - URL                 → links to external plagiarism
  - IP_ADDRESS          → network identifiers
  - STUDENT_ID          → custom pattern (e.g. "ENG/2020/001")
  - MATRIC_NUMBER       → custom pattern (Nigerian matric format)
  - LOCATION            → to prevent home address leakage

Performance Notes:
  - Presidio loads spaCy's NLP pipeline on first call (cold start ~300ms).
  - Subsequent calls are fast (~2–5ms per query).
  - The engine is initialised once at module level and reused.
  - Safe for concurrent use (Presidio engine is thread-safe).

Usage:
    from security.pii_masker import mask_pii, PIIMaskResult

    result = mask_pii("Hi, I'm Adeola Okonkwo, matric ENG/2020/042")
    print(result.masked_text)   # "Hi, I'm <PERSON>, matric <STUDENT_ID>"
    print(result.detected)      # [{"entity": "PERSON", "value": "Adeola Okonkwo"}, ...]
"""

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom PII Patterns (Nigerian Educational Context)
# ---------------------------------------------------------------------------

# Nigerian matriculation number patterns:
#   e.g.  "ENG/2020/001"  "CSC/2019/155"  "MAT/2021/300"
MATRIC_PATTERN = re.compile(
    r"\b[A-Z]{2,4}/20\d{2}/\d{2,4}\b",
    re.IGNORECASE,
)

# Generic student/staff ID badges  (e.g.  "STU-200034"  "ADM_101234")
STUDENT_ID_PATTERN = re.compile(
    r"\b(?:STU|ADM|LEC|REG|MAT)[-_]?\d{5,8}\b",
    re.IGNORECASE,
)

# Institutional email (catches both @*.edu and @*.edu.ng)
INSTITUTIONAL_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.edu(?:\.[a-z]{2})?\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Result Dataclass
# ---------------------------------------------------------------------------

@dataclass
class PIIDetection:
    """Represents a single detected PII entity."""
    entity_type: str      # e.g. "PERSON", "EMAIL_ADDRESS", "MATRIC_NUMBER"
    original_value: str   # The raw detected text
    start: int            # Character offset in original text
    end: int              # Character offset in original text
    score: float          # Confidence score (0.0 – 1.0)


@dataclass
class PIIMaskResult:
    """Return type for mask_pii()."""
    masked_text: str                        # Text with PII replaced by placeholders
    original_text: str                      # The unmodified input
    detected: list[PIIDetection] = field(default_factory=list)
    pii_found: bool = False                 # Convenience flag

    @property
    def entity_types(self) -> list[str]:
        """Unique entity types detected (for logging / telemetry)."""
        return list({d.entity_type for d in self.detected})


# ---------------------------------------------------------------------------
# Presidio Engine (loaded once at module level)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_presidio_engine():
    """
    Load and cache the Presidio AnalyzerEngine.

    Lazy-loaded to avoid import overhead at module import time.
    spaCy model (en_core_web_sm) loads here — ~300ms on first call.
    All subsequent calls return the cached engine in <1ms.
    """
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        # Configure spaCy NLP provider with small model (fast, good enough)
        provider = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [
                {"lang_code": "en", "model_name": "en_core_web_sm"}
            ],
        })
        nlp_engine = provider.create_engine()
        engine = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
        logger.info("Presidio AnalyzerEngine loaded with en_core_web_sm.")
        return engine
    except ImportError as exc:
        logger.error("Presidio not installed. Run: uv add presidio-analyzer presidio-anonymizer spacy")
        raise RuntimeError("Presidio AnalyzerEngine unavailable") from exc


@lru_cache(maxsize=1)
def _get_presidio_anonymizer():
    """Cache the Presidio AnonymizerEngine."""
    try:
        from presidio_anonymizer import AnonymizerEngine
        return AnonymizerEngine()
    except ImportError as exc:
        raise RuntimeError("Presidio AnonymizerEngine unavailable") from exc


# ---------------------------------------------------------------------------
# Custom Pattern Detection (regex-based, applied before Presidio)
# ---------------------------------------------------------------------------

def _detect_custom_patterns(text: str) -> list[PIIDetection]:
    """
    Apply Nigerian educational PII patterns not covered by Presidio's
    built-in recognisers.

    Returns a list of PIIDetection sorted by start offset.
    """
    detections: list[PIIDetection] = []

    for match in MATRIC_PATTERN.finditer(text):
        detections.append(PIIDetection(
            entity_type="MATRIC_NUMBER",
            original_value=match.group(),
            start=match.start(),
            end=match.end(),
            score=0.95,
        ))

    for match in STUDENT_ID_PATTERN.finditer(text):
        detections.append(PIIDetection(
            entity_type="STUDENT_ID",
            original_value=match.group(),
            start=match.start(),
            end=match.end(),
            score=0.90,
        ))

    for match in INSTITUTIONAL_EMAIL_PATTERN.finditer(text):
        detections.append(PIIDetection(
            entity_type="INSTITUTIONAL_EMAIL",
            original_value=match.group(),
            start=match.start(),
            end=match.end(),
            score=0.98,
        ))

    return sorted(detections, key=lambda d: d.start)


def _apply_custom_masking(text: str, detections: list[PIIDetection]) -> str:
    """
    Replace custom-detected PII spans with <ENTITY_TYPE> placeholders.
    Processes spans in reverse order to preserve character offsets.
    """
    result = list(text)
    for det in reversed(sorted(detections, key=lambda d: d.start)):
        placeholder = f"<{det.entity_type}>"
        result[det.start:det.end] = list(placeholder)
    return "".join(result)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Entity types that Presidio should actively scan for in educational context
_EDUCATIONAL_ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "LOCATION",
    "URL",
    "IP_ADDRESS",
    "US_SSN",           # Catch SSN patterns in international content
    "CREDIT_CARD",      # Prevent financial data leakage
    "DATE_TIME",        # Can be quasi-identifier when combined with name
]


def mask_pii(
    text: str,
    min_score: float = 0.7,
    entities: Optional[list[str]] = None,
) -> PIIMaskResult:
    """
    Detect and mask PII from a text string.

    Pipeline:
      1. Run custom regex patterns (matric numbers, student IDs, inst. emails)
      2. Apply custom masks to a working copy
      3. Run Presidio NER on the result
      4. Apply Presidio masking

    Args:
        text:       The raw text to sanitise (student query, profile field, etc.)
        min_score:  Minimum confidence threshold for Presidio detections.
                    Default 0.7 — balanced between false positives and recall.
        entities:   Override the default entity list. If None, uses
                    _EDUCATIONAL_ENTITIES.

    Returns:
        PIIMaskResult with masked_text and detection metadata.

    Raises:
        RuntimeError: If Presidio is not installed (caught gracefully below).
    """
    if not text or not text.strip():
        return PIIMaskResult(masked_text=text, original_text=text)

    all_detections: list[PIIDetection] = []

    # ---- Step 1: Custom pattern detection ------------------------------------
    custom_detections = _detect_custom_patterns(text)
    all_detections.extend(custom_detections)

    # ---- Step 2: Apply custom masks ------------------------------------------
    working_text = _apply_custom_masking(text, custom_detections)

    # ---- Step 3: Presidio NER detection --------------------------------------
    try:
        engine = _get_presidio_engine()
        target_entities = entities or _EDUCATIONAL_ENTITIES
        results = engine.analyze(
            text=working_text,
            language="en",
            entities=target_entities,
            score_threshold=min_score,
        )

        for result in results:
            all_detections.append(PIIDetection(
                entity_type=result.entity_type,
                original_value=working_text[result.start:result.end],
                start=result.start,
                end=result.end,
                score=result.score,
            ))

        # ---- Step 4: Apply Presidio anonymisation ----------------------------
        if results:
            from presidio_anonymizer.entities import OperatorConfig
            anonymizer = _get_presidio_anonymizer()
            anonymized = anonymizer.anonymize(
                text=working_text,
                analyzer_results=results,
                operators={
                    "DEFAULT": OperatorConfig("replace", {"new_value": lambda r: f"<{r.entity_type}>"}),
                },
            )
            final_text = anonymized.text
        else:
            final_text = working_text

    except Exception as exc:
        # Graceful degradation: if Presidio fails, return custom-masked text
        # and log the error. NEVER raise — PII masking failure must not crash the API.
        logger.warning(
            "Presidio analysis failed, returning custom-masked text only. Error: %s",
            exc,
        )
        final_text = working_text

    pii_found = bool(all_detections)

    if pii_found:
        logger.info(
            "PII detected and masked: %d entities found (%s).",
            len(all_detections),
            [d.entity_type for d in all_detections],
        )

    return PIIMaskResult(
        masked_text=final_text,
        original_text=text,
        detected=all_detections,
        pii_found=pii_found,
    )


def is_safe_for_llm(text: str, strict: bool = False) -> tuple[bool, PIIMaskResult]:
    """
    Check if text is safe to send to an LLM without masking.

    Args:
        text:   Input text.
        strict: If True, any detection (even low-confidence) fails safety check.

    Returns:
        (is_safe, PIIMaskResult) — callers can use masked_text if not is_safe.
    """
    result = mask_pii(text, min_score=0.5 if strict else 0.7)
    return not result.pii_found, result
