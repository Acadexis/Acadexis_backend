"""
Acadexis — Wiki Manager (Sprint 9)
====================================
Provides a LangGraph node that loads the compiled Wiki for a course
and injects it into the agent state before the PedagogicalAgent runs.

Design:
  - Reads state["course_id"]
  - Queries SQLite for the compiled Markdown Wiki
  - Writes state["wiki_content"] (str or None)
  - Non-fatal: if the Wiki is missing or the DB query fails,
    state["wiki_content"] is set to None and the pipeline continues
    with RAG-only knowledge (fail-safe, same as Sprint 1-8 behavior).
"""

import logging

from rag.agents.state import TutorState
from rag.evaluation.interaction_logger import get_wiki

logger = logging.getLogger(__name__)

# Maximum wiki size to inject into the system prompt.
# ~50,000 tokens ≈ ~200,000 chars. We cap at 150,000 chars
# to leave headroom for context chunks and conversation history.
_MAX_WIKI_CHARS = 150_000


async def wiki_loader(state: TutorState) -> TutorState:
    """
    LangGraph node — loads the compiled Wiki for the current course.

    Runs in parallel with RetrieverAgent and ProfilerAgent.
    The PedagogicalAgent reads state["wiki_content"] to inject
    foundational knowledge into its system prompt.

    Returns:
        State update with "wiki_content" (str or None).
    """
    course_id = state.get("course_id", "")

    if not course_id:
        logger.warning("WikiLoader: no course_id in state — skipping.")
        return {"wiki_content": None}

    try:
        wiki = await get_wiki(course_id)
    except Exception as exc:
        logger.error("WikiLoader: DB query failed: %s", exc)
        return {"wiki_content": None}

    if not wiki:
        logger.debug("WikiLoader: no Wiki found for course '%s'.", course_id)
        return {"wiki_content": None}

    # Truncate if the wiki is too large for the context window
    if len(wiki) > _MAX_WIKI_CHARS:
        logger.warning(
            "WikiLoader: Wiki for '%s' is %d chars — truncating to %d.",
            course_id, len(wiki), _MAX_WIKI_CHARS,
        )
        wiki = wiki[:_MAX_WIKI_CHARS]

    logger.info(
        "WikiLoader: loaded Wiki for course '%s' (%d chars).",
        course_id, len(wiki),
    )
    return {"wiki_content": wiki}
