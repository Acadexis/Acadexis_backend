"""
Acadexis — Gemini Context Cache Manager (Sprint 5)
===================================================
Responsibility: Manage the lifecycle of Gemini server-side context caches
for course documents, reducing repeated token costs by up to 96%.

Background — Why Caching Matters Here
--------------------------------------
A typical 200-page textbook, when chunked and injected into the Pedagogical
Agent's prompt, costs approximately 150,000–400,000 input tokens per request.
At $3.50 per million tokens (Gemini 1.5 Pro), serving 100 simultaneous
students asking questions about the same textbook without caching costs:

  100 students × 200,000 tokens × $3.50/M = $0.07 per question round

With Gemini Context Caching (storage cost: $1.00/M tokens/hour), those same
100 students share ONE cached copy of the document:

  Cache cost: 200,000 tokens × $1.00/M × 24h ≈ $0.005/day
  Per-request cost: just the student query tokens (< 1,000) per student

This is the 96% cost reduction cited in the Sprint spec.

API Constraints (DO NOT REMOVE THIS SECTION)
---------------------------------------------
  1. Minimum tokens: 32,768 — the API REJECTS smaller documents with a 400.
     We enforce this via `_count_tokens()` before attempting to create a cache.

  2. Minimum TTL: 1 minute. Our default is 24 hours (aligned with lecture day).

  3. Gemini 1.5 Pro supports caching. gemini-2.0-flash also supports it.
     The cache is model-scoped: a Pro cache cannot be used with Flash.

  4. Cache names are alphanumeric slugs returned by the API after creation.
     We derive a deterministic lookup key from (course_id, filename, model)
     to avoid re-uploading identical documents.

  5. The cache stores `system_instruction` + `contents` together. We cache
     the Socratic system prompt + document context block (the expensive part).
     The student query (cheap) remains as a dynamic per-request input.

Architecture Decision: In-Process Cache Registry
-------------------------------------------------
We maintain an in-process Python dict `_CACHE_REGISTRY` that maps:
    (course_id, filename, model) → {"name": str, "expires_at": datetime}

Rationale:
  - For a single Uvicorn process (current stage), in-process is sufficient.
  - Sprint 5 scope explicitly excludes database persistence for cache metadata.
  - Sprint 7/9 will migrate this to Redis or PostgreSQL for multi-process/pod.
  - The registry has a safe fallback: if an entry is missing or expired, the
    manager creates a new cache transparently.

Known Limitation:
  - Process restart loses the registry → cold start until caches rebuild.
    Acceptable for MVP: the cost impact is one missed cache per restart event.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

from google import genai
from google.genai import types as genai_types

from rag.config import get_settings
from rag.ingestion.embedder import _get_gemini_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-Process Cache Registry
# Maps: cache_key → {"name": str, "expires_at": datetime}
# Thread-safety: asyncio single-thread model makes this safe for Uvicorn.
# ---------------------------------------------------------------------------
_CACHE_REGISTRY: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Public Interface
# ---------------------------------------------------------------------------

async def create_or_get_cache(
    course_id: str,
    filename: str,
    document_text: str,
    *,
    model: str | None = None,
) -> Optional[str]:
    """
    Create a Gemini context cache for a course document, or return the
    name of an existing, still-valid cache.

    This is the primary entry point called by the PedagogicalAgent before
    generating a response. On a cache HIT the agent passes the cache name
    to Gemini, which reads the document server-side (no re-upload cost).
    On a cache MISS it uploads the document and stores the name.

    Args:
        course_id:     Course identifier (e.g. "csc501"). Used as cache key.
        filename:      PDF filename (e.g. "lecture_03.pdf"). Used as cache key.
        document_text: Full document text to cache (must be ≥ 32,768 tokens).
        model:         Gemini model name. Defaults to settings.gemini_pro_model.
                       IMPORTANT: cache is model-scoped.

    Returns:
        Cache resource name (str) if caching succeeded or cache was reused.
        None if:
          - caching is disabled (settings.cache_enabled = False)
          - document is below the 32,768 token minimum
          - the Gemini API call fails (fail-open: caller falls back to direct)

    Design: Fail-Open
        On any error we log and return None. The PedagogicalAgent must handle
        None by falling back to direct (uncached) generation. This keeps the
        tutor available even if the cache API is down.
    """
    settings = get_settings()

    if not settings.cache_enabled:
        logger.debug("Context caching disabled via settings.cache_enabled=False.")
        return None

    _model = model or settings.gemini_pro_model

    # Check if we already have a live cache for this document+model
    existing = _get_live_cache(course_id, filename, _model)
    if existing:
        logger.info(
            "Cache HIT — course=%s file=%s model=%s name=%s",
            course_id, filename, _model, existing,
        )
        return existing

    # Count tokens before attempting to cache — avoids wasted API call
    client: genai.Client = _get_gemini_client()
    token_count = await _count_tokens(client, _model, document_text)

    if token_count < settings.cache_min_tokens:
        logger.info(
            "Document too small to cache: %d tokens < %d minimum (course=%s file=%s). "
            "Falling back to direct generation.",
            token_count, settings.cache_min_tokens, course_id, filename,
        )
        return None

    # Create the cache
    try:
        cache_name = await _create_cache(
            client=client,
            model=_model,
            document_text=document_text,
            ttl_hours=settings.cache_ttl_hours,
        )
    except Exception as exc:
        logger.warning(
            "Cache creation failed for course=%s file=%s: %s. "
            "Falling back to direct generation.",
            course_id, filename, exc,
        )
        return None

    # Register the new cache
    expires_at = datetime.now(UTC) + timedelta(hours=settings.cache_ttl_hours)
    cache_key = _make_key(course_id, filename, _model)
    _CACHE_REGISTRY[cache_key] = {"name": cache_name, "expires_at": expires_at}

    logger.info(
        "Cache CREATED — course=%s file=%s model=%s tokens=%d "
        "name=%s expires_at=%s",
        course_id, filename, _model, token_count, cache_name,
        expires_at.isoformat(),
    )
    return cache_name


async def delete_cache(cache_name: str) -> bool:
    """
    Delete a named cache from the Gemini API and remove it from the registry.

    Used when course content is updated by the lecturer and the old cache
    must be invalidated before re-uploading.

    Args:
        cache_name: Resource name returned by the API (e.g. "cachedContents/xyz").

    Returns:
        True if deleted successfully, False on error.
    """
    client: genai.Client = _get_gemini_client()
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: client.caches.delete(name=cache_name),
        )
        # Remove from local registry
        _evict_by_name(cache_name)
        logger.info("Cache deleted: %s", cache_name)
        return True
    except Exception as exc:
        logger.warning("Failed to delete cache %s: %s", cache_name, exc)
        return False


async def list_active_caches() -> list[dict]:
    """
    List all currently active caches from the Gemini API.

    Used by the admin endpoint (Sprint 7+) and for diagnostics.

    Returns:
        List of dicts: [{name, model, create_time, expire_time, usage_metadata}]
    """
    client: genai.Client = _get_gemini_client()
    try:
        loop = asyncio.get_event_loop()
        caches_page = await loop.run_in_executor(
            None,
            lambda: list(client.caches.list()),
        )
        return [
            {
                "name": c.name,
                "model": getattr(c, "model", "unknown"),
                "create_time": str(getattr(c, "create_time", "")),
                "expire_time": str(getattr(c, "expire_time", "")),
                "token_count": getattr(
                    getattr(c, "usage_metadata", None), "total_token_count", 0
                ),
            }
            for c in caches_page
        ]
    except Exception as exc:
        logger.warning("Failed to list caches: %s", exc)
        return []


def get_registry_snapshot() -> dict[str, dict]:
    """
    Return a copy of the in-process registry. Used in tests and diagnostics.

    Returns:
        Dict mapping cache_key → {name, expires_at}
    """
    return {k: dict(v) for k, v in _CACHE_REGISTRY.items()}


def clear_registry() -> None:
    """
    Clear the in-process cache registry (does NOT delete API-side caches).
    Intended for testing only.
    """
    _CACHE_REGISTRY.clear()


# ---------------------------------------------------------------------------
# Private Helpers
# ---------------------------------------------------------------------------

def _make_key(course_id: str, filename: str, model: str) -> str:
    """
    Derive a deterministic registry key.

    Key format: "{course_id}::{filename}::{model}"
    The double-colon separator avoids collisions with single-colon in filenames.
    """
    return f"{course_id}::{filename}::{model}"


def _get_live_cache(
    course_id: str, filename: str, model: str
) -> Optional[str]:
    """
    Return the cache name if a live (non-expired) registry entry exists.

    We add a 5-minute grace buffer before expiry to avoid a race condition
    where the cache expires between the registry check and the API call.
    """
    key = _make_key(course_id, filename, model)
    entry = _CACHE_REGISTRY.get(key)
    if not entry:
        return None

    grace_buffer = timedelta(minutes=5)
    if datetime.now(UTC) >= entry["expires_at"] - grace_buffer:
        # Expired or about to expire — evict and return None
        del _CACHE_REGISTRY[key]
        logger.debug("Cache entry expired for key=%s, evicted from registry.", key)
        return None

    return entry["name"]


def _evict_by_name(cache_name: str) -> None:
    """Remove a registry entry by its cache name (used after API-side deletion)."""
    keys_to_remove = [k for k, v in _CACHE_REGISTRY.items() if v["name"] == cache_name]
    for k in keys_to_remove:
        del _CACHE_REGISTRY[k]


async def _count_tokens(
    client: genai.Client, model: str, text: str
) -> int:
    """
    Count the token length of the document text using the Gemini token counter.

    Why use the API counter and not tiktoken/estimate?
    Gemini uses SentencePiece tokenization which differs from BPE. A character-
    based estimate (text_length / 4) would have ~20% error on non-English text
    and technical content. The API counter is exact and fast (sub-50ms).

    Args:
        client: Initialized Gemini client.
        model:  Model name (token count is model-specific for multi-modal models).
        text:   Document text to count.

    Returns:
        Total token count (int).
    """
    loop = asyncio.get_event_loop()
    try:
        response = await loop.run_in_executor(
            None,
            lambda: client.models.count_tokens(
                model=model,
                contents=text,
            ),
        )
        return response.total_tokens
    except Exception as exc:
        # Estimation fallback: ~4 chars per token (rough but safe)
        estimated = len(text) // 4
        logger.warning(
            "Token count API failed (%s). Using char-based estimate: %d tokens.",
            exc, estimated,
        )
        return estimated


async def _create_cache(
    client: genai.Client,
    model: str,
    document_text: str,
    ttl_hours: int,
) -> str:
    """
    Upload document_text to Gemini as a context cache.

    We cache:
      - system_instruction: the Socratic system prompt (static, expensive)
      - contents: the document text block (static per course, expensive)

    The student query (dynamic, cheap) is NOT cached — it's sent per-request.

    Args:
        client:        Initialized Gemini client.
        model:         Model to scope the cache to.
        document_text: Full document text (must be ≥ 32,768 tokens).
        ttl_hours:     Cache lifetime in hours.

    Returns:
        Cache resource name string (e.g. "cachedContents/abc123").

    Raises:
        Exception: Re-raised from the Gemini API on creation failure.
                   Caller (create_or_get_cache) handles this with fail-open.
    """
    # Import here to avoid circular import with pedagogical_agent
    from agents.pedagogical_agent import _SOCRATIC_SYSTEM_PROMPT  # noqa: PLC0415

    ttl_seconds = ttl_hours * 3600
    loop = asyncio.get_event_loop()

    cached_content = await loop.run_in_executor(
        None,
        lambda: client.caches.create(
            model=model,
            config=genai_types.CreateCachedContentConfig(
                system_instruction=_SOCRATIC_SYSTEM_PROMPT,
                contents=[document_text],
                ttl=f"{ttl_seconds}s",
            ),
        ),
    )

    if not cached_content or not cached_content.name:
        raise ValueError(
            "Gemini API returned a cache object with no name. "
            "This is unexpected and likely a transient API error."
        )

    return cached_content.name
