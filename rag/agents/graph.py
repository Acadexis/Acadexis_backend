"""
Acadexis — LangGraph Tutor Graph (Sprint 3 + Sprint 4)
========================================================
Compiles the multi-agent tutoring pipeline into an executable LangGraph graph.

Graph Topology:
---------------
                    ┌────────────────────────────────┐
                    │         START                  │
                    └───────────────┬────────────────┘
                                    │
                    ┌───────────────▼────────────────┐
                    │       retriever_agent           │  Node 1
                    │  (embed query → Pinecone ANN   │
                    │   → Cohere rerank → chunks)    │
                    └───────────────┬────────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │  (parallel fan-out) │                      │
              │  LangGraph runs nodes 2 and 2b in parallel │
              │  (profiler is independent of retriever     │
              │   output, so we fan-out for speed)         │
    ┌─────────▼──────────┐         │         ┌────────────▼────────────┐
    │   profiler_agent   │         │         │   [future: router node] │  Node 2b
    │  (inject student   │         │         │   (Sprint 4)            │
    │   profile + Bloom) │         │         └─────────────────────────┘
    └─────────┬──────────┘         │
              │                    │
              └──────────┬─────────┘
                         │
           ┌─────────────▼──────────────┐
           │     pedagogical_agent       │  Node 3
           │  (Gemini 1.5 Pro + strict  │
           │   Socratic system prompt)  │
           └─────────────┬──────────────┘
                         │
               ┌──────────▼──────────────────┐
               │      verifier_agent          │  Node 4 (Sprint 4)
               │  (Gemini Flash: hallucination│
               │   audit + Socratic check)    │
               └──────┬───────────────────────┘
                      │
               ┌──────▼──────┐
               │route_or_err?│  Conditional edge
               └──────┬──────┘
                ok    │    error
               ┌──────▼─┐  ┌─▼───────────────┐
               │  END   │  │  error_handler  │
               └────────┘  └─────────────────┘

Implementation Notes:
---------------------
1. Parallel execution: ProfilerAgent and RetrieverAgent can run concurrently
   because they are INDEPENDENT (profiler doesn't need retrieval results).
   LangGraph handles this with multiple edges FROM START.
   This reduces total latency by ~Profiler.time (usually < 10ms in Sprint 3
   since it's hardcoded, but ~50ms in Sprint 5 when it's a DB query).

2. State merging: LangGraph does NOT replace the state on each node return.
   It deep-merges the returned dict into the existing state. This means:
   - RetrieverAgent returns {"context_chunks": [...]} → merged into state
   - ProfilerAgent returns {"student_profile": {...}} → merged into state
   - PedagogicalAgent receives state with BOTH fields populated

3. Error routing: Any node can set state["error"]. The conditional edge after
   the PedagogicalAgent checks for this and routes to error_handler if set.
   In production, error_handler logs the error and returns a friendly message.

4. Checkpointing: LangGraph supports sub-graph checkpointing via the
   `MemorySaver` (in-memory) or `SqliteSaver` (persistent). We use MemorySaver
   in Sprint 3. Sprint 5 will swap to PostgresCheckpointer for persistence
   across sessions (enables multi-session conversational context).

5. Why LangGraph over plain async functions:
   - State management: no manual passing of context between functions.
   - Observability: LangSmith tracing hooks into the graph natively.
   - Fault isolation: node boundaries create natural failure points.
   - Future extensibility: adding a new node (e.g., Quiz Generator) requires
     only adding a node and edge, not refactoring all function signatures.
"""

import logging
from functools import lru_cache

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from rag.agents.pedagogical_agent import pedagogical_agent
from rag.agents.profiler_agent import profiler_agent
from rag.agents.retriever_agent import retriever_agent
from rag.agents.state import TutorState
from rag.agents.verifier_agent import verifier_agent
from rag.agents.wiki_manager import wiki_loader  # Sprint 9

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error Handler Node
# ---------------------------------------------------------------------------

async def error_handler(state: TutorState) -> TutorState:
    """
    Fallback node — activated when any upstream node sets state["error"].

    Returns a student-friendly error message without leaking internal details.
    The actual error is already logged by the node that set it.

    In Sprint 4, this node will also trigger an alert to the platform's
    monitoring dashboard (e.g., Datadog / Uptime Robot).
    """
    error = state.get("error", "An unexpected error occurred.")
    error_node = state.get("error_node", "unknown")

    logger.error(
        "TutorGraph: error_handler activated (from_node='%s', error='%s')",
        error_node,
        error,
    )

    # Student-facing message — never expose internal error details
    fallback_response = (
        "I'm having a little trouble accessing your course materials right now. "
        "Could you try rephrasing your question, or ask again in a moment? "
        "If the problem persists, your lecturer can help investigate."
    )

    return {
        "response": fallback_response,
        "citations": [],
        "reasoning_trace": f"[Error in {error_node}]: {error}",
    }


# ---------------------------------------------------------------------------
# Conditional Edge — Route after PedagogicalAgent
# ---------------------------------------------------------------------------

def _route_after_verifier(state: TutorState) -> str:
    """
    Conditional edge function (Sprint 4: routes AFTER the VerifierAgent).
    If any node set state["error"], route to the error handler.
    Otherwise, the graph is complete — route to END.

    Returns:
        "error_handler" | "end"
    """
    if state.get("error"):
        return "error_handler"
    return "end"


# Backward-compatible alias — Sprint 3 tests import this name directly.
# Sprint 4 renamed it to _route_after_verifier (same logic, different insertion point).
_route_after_pedagogical = _route_after_verifier


# ---------------------------------------------------------------------------
# Graph Factory
# ---------------------------------------------------------------------------

def build_tutor_graph() -> StateGraph:
    """
    Construct and compile the LangGraph tutoring pipeline.

    This function is called once at startup (cached via @lru_cache on
    get_tutor_graph()). The compiled graph is reused for every student request.

    Architecture decisions:
      - RetrieverAgent runs first (it has network I/O and is the critical path).
      - ProfilerAgent runs in parallel with RetrieverAgent (no dependency).
      - PedagogicalAgent runs after both complete (it needs their outputs).
      - ErrorHandler is a fallback node reachable from the pedagogical node only
        (upstream nodes stop the graph immediately via LangGraph's error routing).

    Returns:
        A compiled LangGraph StateGraph ready to invoke.
    """
    # ---- Create the graph with our TypedDict state -------------------------
    graph = StateGraph(TutorState)

    # ---- Register nodes -------------------------------------------------------
    # Node names must be unique strings. They appear in LangSmith traces.
    graph.add_node("retriever_agent", retriever_agent)
    graph.add_node("profiler_agent", profiler_agent)
    graph.add_node("wiki_loader", wiki_loader)  # Sprint 9
    graph.add_node("pedagogical_agent", pedagogical_agent)
    graph.add_node("verifier_agent", verifier_agent)  # Sprint 4
    graph.add_node("error_handler", error_handler)

    # ---- Define edges ---------------------------------------------------------

    # START fans out to retriever, profiler, and wiki_loader simultaneously.
    # LangGraph executes all three concurrently and waits for all to finish
    # before running pedagogical_agent.
    graph.add_edge(START, "retriever_agent")
    graph.add_edge(START, "profiler_agent")
    graph.add_edge(START, "wiki_loader")  # Sprint 9

    # All three nodes feed into the pedagogical agent.
    # LangGraph auto-merges their state dicts before invoking pedagogical_agent.
    graph.add_edge("retriever_agent", "pedagogical_agent")
    graph.add_edge("profiler_agent", "pedagogical_agent")
    graph.add_edge("wiki_loader", "pedagogical_agent")  # Sprint 9

    # Sprint 4: PedagogicalAgent → VerifierAgent (hallucination audit)
    graph.add_edge("pedagogical_agent", "verifier_agent")

    # Conditional edge: check for errors AFTER verification
    graph.add_conditional_edges(
        "verifier_agent",
        _route_after_verifier,
        {
            "error_handler": "error_handler",
            "end": END,
        },
    )

    # Error handler always terminates
    graph.add_edge("error_handler", END)

    # ---- Compile with in-memory checkpointer ----------------------------------
    # MemorySaver stores state snapshots in RAM.
    # Each `thread_id` (= session_id) gets its own isolated conversation state.
    # This enables multi-turn conversations within a session.
    # Sprint 5 will replace this with PostgresCheckpointer for persistence.
    checkpointer = MemorySaver()
    compiled = graph.compile(checkpointer=checkpointer)

    logger.info("TutorGraph compiled successfully.")
    return compiled


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_tutor_graph():
    """
    Return the compiled TutorGraph singleton.

    The graph is built once and reused for every request. LangGraph compiled
    graphs are thread-safe and support concurrent `ainvoke()` calls from
    multiple requests.

    In tests, call `get_tutor_graph.cache_clear()` to force a rebuild if needed.
    """
    return build_tutor_graph()
