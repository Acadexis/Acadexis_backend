"""
rag/startup.py — One-time RAG pipeline initialization.

Called from apps/studylab/apps.py StudylabConfig.ready() when Django starts.
Safe to call multiple times (idempotent). Non-fatal on any error so the
platform always comes up even without valid API keys.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


def initialize_rag() -> None:
    """
    Initialize:
      1. SQLite interaction log database (tables created if missing)
      2. Pinecone index (created if missing, no-op if it already exists)
      3. LangGraph tutor graph (compiled + cached as singleton)

    All steps are async and run in a temporary event loop.
    Errors are caught and logged as warnings — the Django app still starts.
    """
    logger.info("RAG: starting initialization...")

    try:
        _run_async_init()
    except Exception as exc:
        logger.warning("RAG: async init failed (non-fatal): %s", exc, exc_info=True)
        return

    try:
        _warm_graph()
    except Exception as exc:
        logger.warning("RAG: graph warm-up failed (non-fatal): %s", exc, exc_info=True)
        return

    logger.info("RAG: pipeline ready.")


# ── Private helpers ────────────────────────────────────────────────────────────

def _run_async_init() -> None:
    """Create a fresh event loop and run async init tasks."""
    from rag.evaluation.interaction_logger import init_db

    async def _async_steps():
        await init_db()
        logger.info("RAG: interaction log DB initialized.")

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_async_steps())
    finally:
        loop.close()

    # Pinecone index initialization is synchronous (uses SDK's create_if_not_exists)
    try:
        from rag.ingestion.embedder import get_pinecone_index
        get_pinecone_index()
        logger.info("RAG: Pinecone index ready.")
    except Exception as exc:
        logger.warning("RAG: Pinecone init failed (non-fatal): %s", exc)


def _warm_graph() -> None:
    """Pre-compile the LangGraph so first user request is fast."""
    from rag.agents.graph import get_tutor_graph
    get_tutor_graph()  # lru_cache singleton — compiles once
    logger.info("RAG: LangGraph compiled and cached.")
