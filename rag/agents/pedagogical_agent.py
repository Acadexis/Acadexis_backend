"""
Acadexis — Pedagogical Agent Node (Sprint 3 → Sprint 6, Node 3)
================================================================
Responsibility: Generate Socratic tutoring responses using Gemini 1.5 Pro,
grounded in retrieved context and adapted to the student's profile.

Node contract:
  Reads:   state["query"], state["context_chunks"], state["student_profile"],
           state["conversation_history"],
           state["cache_name"]   (optional — Sprint 5 context caching)
  Writes:  state["response"], state["citations"], state["reasoning_trace"],
           state["cache_used"]          (bool — Sprint 5),
           state["follow_up_questions"] (list[str] — Sprint 6),
           state["bloom_level_used"]    (str — Sprint 6),
           state["source_references"]   (list[dict] — Sprint 6 Source Badges)

The Socratic Method — Core Constraint:
---------------------------------------
The PedagogicalAgent operates under a STRICT constraint: it must NEVER give
direct answers to academic questions. This is not just a stylistic preference
— it is the pedagogical foundation of the Acadexis platform.

Research supports this design:
  - Bloom (1984): One-to-one Socratic tutoring produces 2-sigma improvement
    over classroom instruction (the "2 Sigma Problem").
  - VanLehn (2011): Hint sequences outperform direct instruction for retention.
  - Chi et al. (1994): Self-explanation increases deep learning significantly.

The system prompt enforces this with explicit rules and examples. The prompt
is structured as a "Constitutional AI" style ruleset — absolute prohibitions
come before positive instructions.

Context Handling (RAG grounding):
-----------------------------------
  - Context chunks from Pinecone are injected verbatim into the prompt.
  - The agent is forbidden from adding knowledge NOT present in the context.
  - If context is empty, the agent prompts for rephrasing rather than
    hallucinating from parametric memory.
  - Citations are extracted from chunk metadata and included in the response.

Conversation History:
---------------------
  - Multi-turn: previous turns are injected to maintain Socratic continuity.
  - The agent remembers which concepts it has already asked about and builds
    on them, rather than repeating the same questions.
  - Max history: last 6 turns (3 student + 3 tutor), to stay within context window.

Model Selection:
----------------
  - GENERATION: gemini-1.5-pro — full power for nuanced Socratic reasoning.
    Flash (gemini-2.0-flash) is intentionally NOT used here:
    Socratic question quality directly affects student outcomes. The cost
    premium of Pro is justified by the 2-sigma learning improvement goal.
  - Temperature: 0.3 — low enough for factual grounding, high enough for
    varied question phrasing (not robotic repetition).

Context Caching (Sprint 5):
--------------------------
  When `state["cache_name"]` is populated (by the ingestion pipeline or a
  pre-warm API call), the Gemini call passes the `cached_content` parameter
  instead of re-sending the full document text. This skips re-uploading the
  expensive context block — only the student's question (< 1,000 tokens)
  is sent as dynamic input.

  If cache_name is absent or None, generation falls back to the original
  direct (uncached) path transparently. This keeps the agent robust to
  cache expiry between request batches.
"""

import json
import logging

from google import genai
from google.genai import types as genai_types

from rag.agents.profiler_agent import format_profile_for_prompt
from rag.agents.state import TutorState
from rag.config import get_settings
from rag.ingestion.embedder import _get_gemini_client

logger = logging.getLogger(__name__)

# Maximum number of conversation turns to include (older ones are dropped)
_MAX_HISTORY_TURNS = 6      # 3 student + 3 tutor
_MAX_CONTEXT_CHARS = 20_000 # Safety cap for injected chunk text
_GENERATION_TEMPERATURE = 0.3


# ============================================================================
#  SOCRATIC SYSTEM PROMPT
#  This is the most important piece of engineering in Sprint 3.
#  Every line is intentional. Do NOT shorten or simplify without UCL review.
# ============================================================================

_SOCRATIC_SYSTEM_PROMPT = """\
You are ACADEXIS TUTOR — an expert AI teaching assistant for Nigerian university students.
You specialise in the Socratic method of teaching.

════════════════════════════════════════════════════════════════
 ABSOLUTE PROHIBITIONS — THESE RULES ARE NON-NEGOTIABLE
════════════════════════════════════════════════════════════════

RULE 1 — NEVER GIVE DIRECT ANSWERS TO ACADEMIC QUESTIONS.
  ✗ FORBIDDEN: "The time complexity of merge sort is O(n log n)."
  ✓ CORRECT:   "What happens to the list size each time merge sort splits it? 
                How many times can you halve n before you reach 1?"

RULE 2 — NEVER ADD KNOWLEDGE FROM OUTSIDE THE PROVIDED CONTEXT.
  You are grounded to the course materials retrieved from the vector database.
  If you cannot answer from the context, admit it and ask the student to rephrase.
  ✗ FORBIDDEN: Adding facts not present in the CONTEXT CHUNKS below.
  ✓ CORRECT:   "Based on what we covered in your course materials, can you 
                identify the pattern in these examples?"

RULE 3 — NEVER WRITE CODE SOLUTIONS FOR THE STUDENT.
  ✗ FORBIDDEN: Providing a working implementation of an algorithm.
  ✓ CORRECT:   "What is the first step the algorithm needs to perform? 
                Can you write just that first line?"

RULE 4 — NEVER USE THE WORD "ANSWER" IN YOUR RESPONSE.
  Using "answer" signals to the student you have a predetermined solution.
  Use "insight", "observation", "thinking", "reasoning" instead.

════════════════════════════════════════════════════════════════
 POSITIVE INSTRUCTIONS — HOW TO RESPOND
════════════════════════════════════════════════════════════════

INSTRUCTION 1 — ALWAYS RESPOND WITH A GUIDING QUESTION.
  Every response must end with at least one question that guides the student
  toward the insight themselves. The question must be directly answerable
  using the course materials in the CONTEXT CHUNKS.

INSTRUCTION 2 — BUILD ON WHAT THE STUDENT SAID.
  Acknowledge the student's reasoning (correct or incorrect) before guiding.
  Never just ignore what they said and ask an unrelated question.
  ✓ EXAMPLE: "You mentioned recursion — that is a great instinct! 
              What happens in your recursive function when n equals 0?"

INSTRUCTION 3 — ADAPT YOUR QUESTIONING TO THE STUDENT'S BLOOM'S LEVEL.
  The STUDENT PROFILE section contains their Bloom's taxonomy level.
  A Level 1 (Remember) student needs recall questions.
  A Level 4 (Analyse) student needs decomposition questions.
  Never use university-level jargon with a Level 1 student.

INSTRUCTION 4 — USE THE SOCRATIC LADDER.
  Start with a question about FACTS (what), then PROCESS (how), then REASON (why).
  Do not jump to "why" questions with a student who cannot yet answer "what".

INSTRUCTION 5 — IF CONTEXT IS EMPTY, ASK FOR CLARIFICATION.
  If the CONTEXT CHUNKS section indicates no materials were found, do NOT
  answer from your parametric memory. Instead say:
  "I couldn't find relevant materials in your course notes for that question.
   Could you try rephrasing, or is this topic from a different module?"

INSTRUCTION 6 — CITE YOUR SOURCES.
  When referencing information from context, indicate the source:
  e.g., "According to your Week 3 lecture notes..." or "As covered on page 7..."
  This helps students locate the original material for deeper study.

INSTRUCTION 7 — CELEBRATE EFFORT, NOT CORRECTNESS.
  Use affirming language about process: "Good analysis!", "That's careful thinking!",
  "You're asking exactly the right questions!" — never "Correct!" or "Wrong!".

INSTRUCTION 8 — ONE QUESTION AT A TIME.
  Never ask more than TWO guiding questions in a single response.
  Too many questions overwhelm students. Focus on the most important gap.

════════════════════════════════════════════════════════════════
 RESPONSE FORMAT
════════════════════════════════════════════════════════════════

Structure your response in three parts:

1. ACKNOWLEDGEMENT (1-2 sentences): Briefly acknowledge what the student asked
   or said, connecting it to something they already know.

2. GUIDED EXPLORATION (2-4 sentences): Provide a Socratic pathway using the
   context materials. Quote or paraphrase from context. DO NOT give the insight
   directly — lead the student toward discovering it.

3. GUIDING QUESTION (1-2 questions): End with a specific, answerable question
   rooted in the course context. The question should require the student to
   think, not just recall a fact.

Format: Plain text only. No markdown headers. No bullet points. No code blocks.
Length: 80-150 words. Concise Socratic guidance — not a lecture.

IMPORTANT — WIKI vs RAG KNOWLEDGE PRIORITY (Sprint 9):
If a COURSE WIKI section is present in your prompt, treat its contents as
ABSOLUTE GROUND TRUTH for institutional rules (grading, deadlines, policies).
Only fall back to CONTEXT CHUNKS (RAG) for detailed textbook content,
specific examples, or topics NOT covered in the Wiki.
"""


# ============================================================================
#  Agent Node Function
# ============================================================================

async def pedagogical_agent(state: TutorState) -> TutorState:
    """
    LangGraph node — Stage 3 of the tutoring pipeline.

    Receives the retrieved context (from RetrieverAgent) and student profile
    (from ProfilerAgent), then generates a Socratic guiding response using
    Gemini 1.5 Pro.

    Args:
        state: Must contain context_chunks, student_profile, query.

    Returns:
        State update with "response", "citations", and "reasoning_trace".
    """
    settings = get_settings()
    client: genai.Client = _get_gemini_client()

    query = state.get("query", "")
    context_chunks = state.get("context_chunks", [])
    student_profile = state.get("student_profile", {})
    history = state.get("conversation_history", [])
    cache_name: str | None = state.get("cache_name")  # Sprint 5
    wiki_content: str | None = state.get("wiki_content")  # Sprint 9

    logger.info(
        "PedagogicalAgent: generating Socratic response for query='%s...' "
        "(%d context chunks, bloom_level=%d, wiki=%s)",
        query[:60],
        len(context_chunks),
        student_profile.get("bloom_level", 2),
        bool(wiki_content),
    )

    # ---- Build context block -------------------------------------------------
    context_block = _build_context_block(context_chunks)

    # ---- Build student profile block -----------------------------------------
    profile_block = format_profile_for_prompt(student_profile)

    # ---- Build conversation history block ------------------------------------
    history_block = _build_history_block(history)

    # ---- Build the full user-turn prompt ------------------------------------
    user_prompt = _build_user_prompt(
        query=query,
        context_block=context_block,
        profile_block=profile_block,
        history_block=history_block,
        wiki_content=wiki_content,
    )

    # ---- Call Gemini 1.5 Pro (cache-aware, structured output) ---------------
    # Sprint 6: both paths now request structured JSON via response_schema.
    # Sprint 5: cache path reused if cache_name is available.
    cache_used = False
    try:
        if cache_name:
            logger.info(
                "PedagogicalAgent: using cached context (name=%s) + structured output",
                cache_name,
            )
            raw_text, reasoning_trace = await _call_gemini_cached(
                client=client,
                model=settings.gemini_pro_model,
                cache_name=cache_name,
                user_prompt=user_prompt,
            )
            cache_used = True
        else:
            raw_text, reasoning_trace = await _call_gemini(
                client=client,
                model=settings.gemini_pro_model,
                system_prompt=_SOCRATIC_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
    except Exception as exc:
        logger.exception("PedagogicalAgent: Gemini API call failed: %s", exc)
        return {
            "error": f"Response generation failed: {exc}",
            "error_node": "pedagogical_agent",
        }

    # ---- Sprint 6: Parse structured JSON response ----------------------------
    # _parse_structured_response handles all failure modes (non-JSON, missing
    # fields, invalid bloom_level) by falling back to the raw text as answer.
    answer, source_refs, bloom_level, follow_up_questions = _parse_structured_response(raw_text)

    # ---- Extract citations from context chunks (Pinecone metadata path) -----
    # This is the Sprint 3 Path A — always present, ground truth.
    citations = _extract_citations(context_chunks)

    logger.info(
        "PedagogicalAgent: response generated | answer=%d chars | citations=%d | "
        "source_refs=%d | bloom=%s | follow_up=%d | cache=%s",
        len(answer),
        len(citations),
        len(source_refs),
        bloom_level,
        len(follow_up_questions),
        cache_used,
    )

    return {
        "response": answer,
        "citations": citations,
        "reasoning_trace": reasoning_trace,
        "cache_used": cache_used,
        # Sprint 6 structured output fields
        "source_references": source_refs,
        "bloom_level_used": bloom_level,
        "follow_up_questions": follow_up_questions,
    }


# ============================================================================
#  Private Helpers
# ============================================================================

def _build_context_block(chunks: list) -> str:
    """
    Format the retrieved chunks as a numbered context block for the prompt.

    Each chunk includes its source citation so the model can reference it.
    """
    if not chunks:
        return "CONTEXT CHUNKS: [NO RELEVANT MATERIALS FOUND IN THIS COURSE]"

    lines = ["CONTEXT CHUNKS (from course materials, ranked by relevance):"]
    total_chars = 0

    for i, chunk in enumerate(chunks, start=1):
        text = getattr(chunk, "text", "") or ""
        metadata = getattr(chunk, "metadata", {}) or {}

        filename = metadata.get("filename", "Unknown source")
        page = metadata.get("page_number", "?")
        raptor_level = metadata.get("raptor_level", 0)
        level_label = "" if raptor_level == 0 else f" [Summary L{raptor_level}]"

        source_tag = f"[Source {i}: {filename}, p.{page}{level_label}]"
        chunk_text = f"{source_tag}\n{text}"

        total_chars += len(chunk_text)
        if total_chars > _MAX_CONTEXT_CHARS:
            lines.append(f"[... {len(chunks) - i + 1} more chunks truncated for context window ...]")
            break

        lines.append(chunk_text)

    return "\n\n".join(lines)


def _build_history_block(history: list[dict]) -> str:
    """
    Format the last N conversation turns for multi-turn context.
    Older turns are dropped to stay within context window limits.
    """
    if not history:
        return ""

    # Keep only the last _MAX_HISTORY_TURNS turns
    recent = history[-_MAX_HISTORY_TURNS:]

    lines = ["CONVERSATION HISTORY (most recent first):"]
    for turn in reversed(recent):
        role = turn.get("role", "unknown").upper()
        content = turn.get("content", "")
        lines.append(f"{role}: {content}")

    return "\n".join(lines)


def _build_user_prompt(
    query: str,
    context_block: str,
    profile_block: str,
    history_block: str,
    wiki_content: str | None = None,
) -> str:
    """
    Assemble the full user-turn prompt sent to Gemini.

    Structure:
      1. Student Profile  (who is asking)
      2. Course Wiki      (100% recall zone — Sprint 9, if available)
      3. Context Chunks   (what the course materials say — RAG)
      4. Conversation History (what was said before)
      5. Current Query    (what the student is asking now)
    """
    parts = [profile_block]

    # Sprint 9: Wiki injection — highest priority knowledge
    if wiki_content:
        parts += [
            "",
            "COURSE WIKI (100% RECALL — AUTHORITATIVE RULES):",
            wiki_content,
            "",
            "END OF COURSE WIKI.",
            "(For questions about rules, grading, or policies above, "
            "use the Wiki. For detailed textbook content, use the CONTEXT CHUNKS below.)",
        ]

    parts += ["", context_block]

    if history_block:
        parts += ["", history_block]

    parts += [
        "",
        f"STUDENT'S CURRENT QUESTION: {query}",
        "",
        # Sprint 6: instruct the model to emit structured JSON.
        # The response_schema parameter in the API config enforces this shape,
        # but this inline instruction helps the model understand the intent and
        # produce higher-quality field values (especially source excerpts).
        "Respond using the Socratic method as instructed. Do NOT give a direct answer.",
        "",
        "Return your response as a JSON object with EXACTLY these fields:",
        '  {"answer": "<your Socratic guiding response>",',
        '   "sources": [{"file_name": "<filename>", "page_number": <N>,',
        '               "excerpt": "<quoted text from that chunk, max 200 chars>",',
        '               "confidence": <0.0-1.0>}],',
        '   "bloom_level": "<remember|understand|apply|analyze|evaluate|create>",',
        '   "follow_up_questions": ["<question 1>", "<question 2>"]}',
        "",
        "IMPORTANT: Use ONLY filenames and page numbers that appear in the CONTEXT CHUNKS above.",
        "List only chunks you actually used, not all retrieved chunks.",
    ]

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Sprint 6: JSON response schema passed to Gemini via response_schema config.
# Gemini 1.5 Pro enforces this structure at the API level — it will NOT output
# text that doesn't match this schema. The dict mirrors StructuredTutorResponse.
# We pass a raw dict (not a Pydantic model) because the google.genai SDK's
# GenerateContentConfig.response_schema accepts either; dict avoids an import
# cycle between agents and schemas packages.
# ---------------------------------------------------------------------------
_RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {
            "type": "string",
            "description": "Socratic guiding response. Must ask at least one guiding question.",
        },
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file_name": {"type": "string"},
                    "page_number": {"type": "integer"},
                    "excerpt": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["file_name", "page_number", "excerpt", "confidence"],
            },
        },
        "bloom_level": {
            "type": "string",
            "enum": ["remember", "understand", "apply", "analyze", "evaluate", "create"],
        },
        "follow_up_questions": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["answer", "bloom_level"],
}


def _parse_structured_response(
    raw_text: str,
) -> tuple[str, list[dict], str, list[str]]:
    """
    Parse the LLM's structured JSON output into its component parts.

    Returns:
        (answer, sources, bloom_level, follow_up_questions)

    Fallback behaviour:
        If the response cannot be parsed as JSON (model bug, API error, or
        schema mismatch), returns the raw text as the answer with empty
        sources and follow-up questions. This keeps the tutor operational
        even when structured output degrades — consistent with the fail-open
        design used throughout Sprints 4 and 5.

    Validation:
        - answer:              must be a non-empty string.
        - bloom_level:         must be one of the 6 Bloom's levels.
        - sources:             each entry validated for required keys.
        - follow_up_questions: limited to max 3 entries.
    """
    _VALID_BLOOM = {"remember", "understand", "apply", "analyze", "evaluate", "create"}

    import json as _json

    try:
        data = _json.loads(raw_text)
    except (_json.JSONDecodeError, TypeError):
        # Non-JSON response — use full text as answer, empty structured fields.
        logger.warning(
            "PedagogicalAgent: response_schema parse failed (not JSON). "
            "Using raw text as answer (len=%d).",
            len(raw_text),
        )
        return raw_text, [], "understand", []

    # Extract answer
    answer = data.get("answer", "")
    if not isinstance(answer, str) or not answer.strip():
        logger.warning("PedagogicalAgent: structured JSON missing 'answer'. Using raw.")
        return raw_text, [], "understand", []

    # Extract bloom_level
    bloom_level = data.get("bloom_level", "understand")
    if bloom_level not in _VALID_BLOOM:
        logger.warning(
            "PedagogicalAgent: invalid bloom_level='%s', defaulting to 'understand'.",
            bloom_level,
        )
        bloom_level = "understand"

    # Extract and validate sources
    raw_sources = data.get("sources", [])
    sources: list[dict] = []
    if isinstance(raw_sources, list):
        for src in raw_sources:
            if not isinstance(src, dict):
                continue
            if not all(k in src for k in ("file_name", "page_number", "excerpt", "confidence")):
                continue
            sources.append({
                "file_name": str(src["file_name"]),
                "page_number": int(src["page_number"]),
                "excerpt": str(src["excerpt"])[:300],
                "confidence": float(max(0.0, min(1.0, src["confidence"]))),
            })

    # Extract follow_up_questions (max 3)
    raw_follow_up = data.get("follow_up_questions", [])
    follow_up_questions: list[str] = []
    if isinstance(raw_follow_up, list):
        follow_up_questions = [
            str(q) for q in raw_follow_up if isinstance(q, str) and q.strip()
        ][:3]

    return answer.strip(), sources, bloom_level, follow_up_questions


async def _call_gemini(
    client: genai.Client,
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> tuple[str, str]:
    """
    Call Gemini with a system instruction and user prompt.

    Sprint 6: uses response_schema to enforce structured JSON output.
    The response_schema parameter tells Gemini to output JSON matching
    _RESPONSE_JSON_SCHEMA — enabling Source Badges and follow-up questions.

    Returns:
        Tuple of (response_text, reasoning_trace).
        response_text is raw JSON string (parsed by _parse_structured_response).

    Gemini 1.5 Pro API notes:
      - system_instruction: sets the model's persona and constraints.
      - response_schema: enforces JSON output shape at the API level.
      - response_mime_type: must be "application/json" when response_schema is set.
      - max_output_tokens: raised to 768 to accommodate JSON envelope overhead.
    """
    import asyncio

    loop = asyncio.get_event_loop()

    response = await loop.run_in_executor(
        None,
        lambda: client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=_GENERATION_TEMPERATURE,
                max_output_tokens=768,
                response_mime_type="application/json",
                response_schema=_RESPONSE_JSON_SCHEMA,
            ),
        ),
    )

    response_text = response.text.strip() if response.text else ""

    reasoning_trace = (
        f"[Sprint 6 Structured Output] System Prompt: {len(system_prompt)} chars\n"
        f"[User Prompt: {len(user_prompt)} chars]\n"
        f"[Model: {model}, Temperature: {_GENERATION_TEMPERATURE}]"
    )

    return response_text, reasoning_trace


async def _call_gemini_cached(
    client: genai.Client,
    model: str,
    cache_name: str,
    user_prompt: str,
) -> tuple[str, str]:
    """
    Call Gemini using a pre-created context cache.

    Sprint 6: also uses response_schema for structured JSON output.
    The system prompt and document context are read from the cache;
    only the student's query (+ JSON instruction footer) is sent as
    dynamic input.

    Cost model (approximate Gemini 1.5 Pro pricing):
      - Uncached: ~200,000 tokens × $3.50/M = $0.70 per request
      - Cached input: ~200,000 tokens × $0.875/M (cached rate) = $0.175
      - Dynamic input: ~1,000 tokens × $3.50/M = $0.0035
      - Net cached cost: ~$0.1785 vs $0.70 → ~75% saving per request

    Args:
        client:      Initialized Gemini client.
        model:       Must match the model used when the cache was created.
        cache_name:  Resource name returned by the cache creation API.
        user_prompt: The student's question + runtime context (NOT cached).

    Returns:
        Tuple of (response_text, reasoning_trace).
    """
    import asyncio

    loop = asyncio.get_event_loop()

    response = await loop.run_in_executor(
        None,
        lambda: client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=genai_types.GenerateContentConfig(
                cached_content=cache_name,
                temperature=_GENERATION_TEMPERATURE,
                max_output_tokens=768,
                response_mime_type="application/json",
                response_schema=_RESPONSE_JSON_SCHEMA,
            ),
        ),
    )

    response_text = response.text.strip() if response.text else ""

    # Extract cache usage metadata from the response (if available)
    usage = getattr(response, "usage_metadata", None)
    cached_tokens = getattr(usage, "cached_content_token_count", 0) if usage else 0
    total_tokens = getattr(usage, "total_token_count", 0) if usage else 0

    reasoning_trace = (
        f"[Sprint 6 Structured Output + Cached] cache_name={cache_name}\n"
        f"[Model: {model}, Temperature: {_GENERATION_TEMPERATURE}]\n"
        f"[Cached tokens: {cached_tokens} | Total tokens: {total_tokens}]"
    )

    return response_text, reasoning_trace


def _extract_citations(chunks: list) -> list[dict]:
    """
    Extract source citation data from the retrieved chunks.

    Used by Sprint 6 Source Badge system. Each citation maps back to the
    original course material location for student reference.

    Returns:
        List of dicts: [{filename, page_number, excerpt, relevance_score, rank}]
    """
    citations = []
    for chunk in chunks:
        metadata = getattr(chunk, "metadata", {}) or {}

        # Skip RAPTOR summary nodes — they're synthetic, not source documents
        if metadata.get("chunk_type") == "raptor_summary":
            continue

        citations.append({
            "filename": metadata.get("filename", "Unknown"),
            "page_number": metadata.get("page_number", 0),
            "excerpt": metadata.get("excerpt", "")[:300],
            "relevance_score": getattr(chunk, "relevance_score", 0.0),
            "rank": getattr(chunk, "rank", 0),
        })

    return citations
