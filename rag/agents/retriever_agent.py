"""
Acadexis — Retriever Agent Node (Sprint 3, Node 1)
====================================================
Responsibility: Embed the student's query and retrieve relevant context chunks
from Pinecone using the two-stage pipeline built in Sprint 2.

Node contract:
  Reads:   state["query"], state["course_id"]
  Writes:  state["context_chunks"], state["retrieval_metadata"]

Why this is a separate node (not just calling retriever.retrieve() in the
PedagogicalAgent):
  - Separation of concerns: retrieval quality can be tuned independently.
  - LangGraph checkpointing: if the retrieval node is re-run (e.g. after
    a tool call), the agent doesn't need to re-read state it owns.
  - Observability: retrieval latency and reranking metadata are logged
    separately from generation latency, making performance debugging easier.
  - Future: a Routing node will decide WHETHER to call retrieval based on
    whether the question needs it (e.g., greetings skip this node).

Error handling:
  If retrieval fails (Pinecone down, embedding API error), the node writes
  state["error"] and returns early. The graph's conditional edge will route
  to the error handler instead of the PedagogicalAgent.
"""

import logging
import time

from rag.agents.state import TutorState
from rag.ingestion.retriever import retrieve

logger = logging.getLogger(__name__)

# Default retrieval parameters — can be overridden per-request in the future
_DEFAULT_TOP_K_RETRIEVE = 100
_DEFAULT_TOP_K_RERANK = 10
_DEFAULT_RAPTOR_LEVELS = [0, 1, 2, 3]  # Search all RAPTOR tree levels


async def retriever_agent(state: TutorState) -> TutorState:
    """
    LangGraph node — Stage 1 of the tutoring pipeline.

    Executes the two-stage retrieval pipeline (Sprint 2):
      1. Embeds the query with Gemini RETRIEVAL_QUERY task type
      2. Fetches top 100 candidates from Pinecone ANN (scoped to course_id)
      3. Reranks to top 10 using Cohere rerank-v3.5

    Args:
        state: The current TutorState. Must have "query" and "course_id".

    Returns:
        Updated TutorState with "context_chunks" and "retrieval_metadata".
        On error, returns state with "error" and "error_node" set.

    LangGraph expects node functions to return a dict of UPDATES (not the
    full state). LangGraph merges the returned dict into the current state.
    """
    query = state.get("query", "")
    course_id = state.get("course_id", "")

    if not query:
        logger.error("RetrieverAgent: state['query'] is empty.")
        return {
            "error": "Query is required for retrieval.",
            "error_node": "retriever_agent",
        }

    if not course_id:
        logger.error("RetrieverAgent: state['course_id'] is empty.")
        return {
            "error": "course_id is required for retrieval.",
            "error_node": "retriever_agent",
        }

    logger.info(
        "RetrieverAgent: retrieving for query='%s...' in course='%s'",
        query[:60],
        course_id,
    )

    start_ms = time.monotonic()

    try:
        chunks, did_rerank = await retrieve(
            query=query,
            course_id=course_id,
            top_k_retrieve=_DEFAULT_TOP_K_RETRIEVE,
            top_k_rerank=_DEFAULT_TOP_K_RERANK,
            raptor_levels=_DEFAULT_RAPTOR_LEVELS,
            include_metadata=True,
        )
    except Exception as exc:
        logger.exception("RetrieverAgent: retrieval pipeline failed: %s", exc)
        return {
            "error": f"Retrieval failed: {exc}",
            "error_node": "retriever_agent",
        }

    latency_ms = int((time.monotonic() - start_ms) * 1000)

    if not chunks:
        logger.warning(
            "RetrieverAgent: no chunks found for course='%s'. "
            "Has content been ingested?",
            course_id,
        )
        # Return empty context — the PedagogicalAgent will handle this
        # gracefully (it will ask the student to rephrase or wait for content).
        return {
            "context_chunks": [],
            "retrieval_metadata": {
                "total_retrieved": 0,
                "reranked": False,
                "latency_ms": latency_ms,
                "course_id": course_id,
            },
        }

    logger.info(
        "RetrieverAgent: %d chunks retrieved (reranked=%s, latency=%dms)",
        len(chunks),
        did_rerank,
        latency_ms,
    )

    return {
        "context_chunks": chunks,
        "retrieval_metadata": {
            "total_retrieved": len(chunks),
            "reranked": did_rerank,
            "latency_ms": latency_ms,
            "course_id": course_id,
        },
    }
