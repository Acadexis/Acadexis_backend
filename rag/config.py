"""
rag/config.py — Django-aware settings bridge for the RAG pipeline.

All RAG modules call get_settings() expecting a config object.
Instead of running a second .env parse (pydantic-settings), we read
from Django's already-loaded settings — single source of truth.

Usage:
    from rag.config import get_settings
    settings = get_settings()
    api_key = settings.google_api_key
"""
from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


class RAGSettings:
    """
    Duck-type compatible with the original FastAPI config.Settings.

    Every attribute the RAG modules access is defined as a property
    that reads from django.conf.settings at call time.
    This means Django settings changes (e.g. in tests) are reflected
    immediately without needing to clear the lru_cache on this class.
    """

    # ── Gemini ────────────────────────────────────────────────────────────────
    @property
    def google_api_key(self) -> str:
        return self._get("GOOGLE_API_KEY", "")

    @property
    def gemini_embedding_model(self) -> str:
        return self._get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2-preview")

    @property
    def gemini_embedding_dimension(self) -> int:
        return self._get("GEMINI_EMBEDDING_DIMENSION", 3072)

    @property
    def gemini_flash_model(self) -> str:
        return self._get("GEMINI_FLASH_MODEL", "gemini-2.0-flash")

    @property
    def gemini_pro_model(self) -> str:
        return self._get("GEMINI_PRO_MODEL", "gemini-1.5-pro")

    # ── Pinecone ──────────────────────────────────────────────────────────────
    @property
    def pinecone_api_key(self) -> str:
        return self._get("PINECONE_API_KEY", "")

    @property
    def pinecone_index_name(self) -> str:
        return self._get("PINECONE_INDEX_NAME", "acadexis-knowledge")

    @property
    def pinecone_cloud(self) -> str:
        return self._get("PINECONE_CLOUD", "aws")

    @property
    def pinecone_region(self) -> str:
        return self._get("PINECONE_REGION", "us-east-1")

    @property
    def pinecone_dimension(self) -> int:
        # Alias — embedder uses pinecone_dimension to set index dimensions
        return self._get("GEMINI_EMBEDDING_DIMENSION", 3072)

    @property
    def pinecone_metric(self) -> str:
        return "cosine"

    # ── Cohere ────────────────────────────────────────────────────────────────
    @property
    def cohere_api_key(self) -> str:
        return self._get("COHERE_API_KEY", "")

    # ── Upload limits ─────────────────────────────────────────────────────────
    @property
    def max_upload_size_mb(self) -> int:
        return self._get("RAG_MAX_UPLOAD_MB", 50)

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def allowed_mime_types(self) -> list[str]:
        return ["application/pdf"]

    # ── Multimodal image extraction ───────────────────────────────────────────
    @property
    def multimodal_enabled(self) -> bool:
        return self._get("RAG_MULTIMODAL_ENABLED", True)

    @property
    def multimodal_min_image_px(self) -> int:
        return self._get("RAG_MULTIMODAL_MIN_IMAGE_PX", 50)

    @property
    def multimodal_context_chars(self) -> int:
        return self._get("RAG_MULTIMODAL_CONTEXT_CHARS", 400)

    # ── Gemini Context Cache ──────────────────────────────────────────────────
    @property
    def cache_enabled(self) -> bool:
        return self._get("RAG_CACHE_ENABLED", True)

    @property
    def cache_ttl_hours(self) -> int:
        return self._get("RAG_CACHE_TTL_HOURS", 24)

    @property
    def cache_min_tokens(self) -> int:
        return self._get("RAG_CACHE_MIN_TOKENS", 32_768)

    # ── Chunking ──────────────────────────────────────────────────────────────
    @property
    def chunk_size(self) -> int:
        return self._get("RAG_CHUNK_SIZE", 800)

    @property
    def chunk_overlap(self) -> int:
        return self._get("RAG_CHUNK_OVERLAP", 200)

    # ── LangSmith observability (optional) ────────────────────────────────────
    @property
    def langchain_tracing_v2(self) -> bool:
        return self._get("LANGCHAIN_TRACING_V2", False)

    @property
    def langchain_api_key(self) -> str:
        return self._get("LANGCHAIN_API_KEY", "")

    @property
    def langchain_project(self) -> str:
        return self._get("LANGCHAIN_PROJECT", "acadexis-django")

    # ── CORS (kept for interface parity, unused in Django context) ────────────
    @property
    def cors_origins(self) -> list[str]:
        return ["*"]

    # ── Internal helper ───────────────────────────────────────────────────────
    @staticmethod
    def _get(key: str, default):
        """Read from Django settings, fall back to default."""
        try:
            from django.conf import settings as _dj
            return getattr(_dj, key, default)
        except Exception:
            return default


@lru_cache(maxsize=1)
def get_settings() -> RAGSettings:
    """
    Return the singleton RAGSettings instance.

    The lru_cache ensures the object is created once per process.
    Each property still reads from Django settings at call time,
    so test overrides work correctly.
    """
    return RAGSettings()
