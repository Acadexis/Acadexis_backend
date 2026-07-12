"""
Acadexis — Profiler Agent Node (Sprint 3, Node 2)
==================================================
Responsibility: Inject the student's academic profile into the graph state.

Node contract:
  Reads:   state["course_id"] (to scope the profile lookup)
  Writes:  state["student_profile"]

What the profile contains:
  - Bloom's taxonomy level (bloom_level 1-6)
  - Learning level label (beginner/intermediate/advanced)
  - Learning style (visual/kinesthetic/auditory/reading-writing)
  - Mastered topics (avoids re-explaining known concepts)
  - Weak topics (PedagogicalAgent gives extra Socratic attention here)
  - Response language preference

Why this is a separate node:
  - Decouples profile data retrieval from generation logic.
  - Easy to swap the data source: currently hardcoded → Sprint 5 PostgreSQL fetch.
  - In the full production system, this node becomes async (DB I/O) — the node
    boundary makes it trivial to add async without touching other nodes.
  - A future "Adaptive Learning" sprint can make this node call an ML model
    that infers the Bloom's level from past quiz results.

Sprint 3 implementation (hardcoded for development/testing):
  Returns a sensible default profile for every student.
  The profile is intentionally detailed to test the PedagogicalAgent's ability
  to adapt its Socratic questioning style based on profile data.

Sprint 5 implementation (planned):
  Fetches the profile from the profiles table in PostgreSQL using student_id
  extracted from the JWT in the HTTP request headers.
"""

import logging

from rag.agents.state import StudentProfile, TutorState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default profile (Sprint 3 — hardcoded for development)
# ---------------------------------------------------------------------------

_DEFAULT_PROFILE: StudentProfile = {
    "student_id": "student-001",
    "name": "Demo Student",
    "course_id": "csc501",
    "bloom_level": 2,           # "Understand" — the most common entry level
    "learning_level": "beginner",
    "learning_style": "reading-writing",
    "sessions_completed": 3,
    "mastered_topics": ["basic I/O", "variables", "data types"],
    "weak_topics": ["recursion", "time complexity", "pointers"],
    "response_language": "en",
}

# ---------------------------------------------------------------------------
# Bloom's level → pedagogical guidance mapping
# ---------------------------------------------------------------------------
# This maps a numeric Bloom's level to plain English guidance for the
# PedagogicalAgent's system prompt. The agent uses this to calibrate
# vocabulary, question depth, and the amount of scaffolding it provides.

BLOOM_GUIDANCE: dict[int, str] = {
    1: (
        "The student is at the REMEMBER level (Bloom's Level 1). "
        "Use very simple vocabulary. Ask questions that help them recall "
        "definitions and basic facts. Avoid jargon."
    ),
    2: (
        "The student is at the UNDERSTAND level (Bloom's Level 2). "
        "Ask questions that check for comprehension. Use analogies and "
        "examples to connect new ideas to ones they already know."
    ),
    3: (
        "The student is at the APPLY level (Bloom's Level 3). "
        "Ask questions that require them to use a concept in a new context. "
        "Use 'what would happen if...' and 'how would you use...' questions."
    ),
    4: (
        "The student is at the ANALYSE level (Bloom's Level 4). "
        "Ask questions that require breaking down ideas into components. "
        "Use 'why does...', 'what is the relationship between...', and "
        "'compare and contrast...' questions."
    ),
    5: (
        "The student is at the EVALUATE level (Bloom's Level 5). "
        "Ask questions that require judgment and justification. "
        "Use 'which approach is better and why...' questions."
    ),
    6: (
        "The student is at the CREATE level (Bloom's Level 6). "
        "Ask questions that require design and synthesis. "
        "Use 'how would you design...', 'what would you build...' questions."
    ),
}


async def profiler_agent(state: TutorState) -> TutorState:
    """
    LangGraph node — Stage 2 of the tutoring pipeline.

    Injects the student's academic profile into the graph state.

    In Sprint 3 (development), this returns a hardcoded default profile.
    In Sprint 5 (production), this will fetch from PostgreSQL using the
    student_id from the JWT.

    Args:
        state: Current TutorState. "course_id" is used to scope the lookup.

    Returns:
        Dict update: {"student_profile": StudentProfile}
    """
    course_id = state.get("course_id", "unknown")

    # --- Sprint 3: Use hardcoded profile with course_id patched in ----------
    profile: StudentProfile = {
        **_DEFAULT_PROFILE,
        "course_id": course_id,
    }

    bloom_level = profile.get("bloom_level", 2)
    bloom_description = BLOOM_GUIDANCE.get(bloom_level, BLOOM_GUIDANCE[2])

    logger.info(
        "ProfilerAgent: profile injected for student='%s' (bloom=%d, level='%s')",
        profile.get("student_id"),
        bloom_level,
        profile.get("learning_level"),
    )

    return {"student_profile": profile}


# ---------------------------------------------------------------------------
# Public helper: Format profile as a compact string for system prompt injection
# ---------------------------------------------------------------------------

def format_profile_for_prompt(profile: StudentProfile) -> str:
    """
    Render the student profile as a concise block for inclusion in the
    PedagogicalAgent's system prompt.

    This function is called from within pedagogical_agent.py.
    Keeping it here maintains the "profile domain" ownership of its own
    presentation logic.

    Returns:
        A formatted multi-line string describing the student.
    """
    bloom_level = profile.get("bloom_level", 2)
    learning_level = profile.get("learning_level", "beginner")
    bloom_note = BLOOM_GUIDANCE.get(bloom_level, "")

    mastered = profile.get("mastered_topics", [])
    weak = profile.get("weak_topics", [])
    sessions = profile.get("sessions_completed", 0)
    language = profile.get("response_language", "en")

    mastered_str = (", ".join(mastered) if mastered else "none identified yet")
    weak_str = (", ".join(weak) if weak else "none identified yet")

    language_instruction = (
        "Respond in English."
        if language == "en"
        else f"Respond in {language.upper()} (the student's preferred language)."
    )

    return f"""--- STUDENT PROFILE ---
Name: {profile.get('name', 'Student')}
Course: {profile.get('course_id', 'Unknown')}
Sessions completed: {sessions}
Learning level: {learning_level} (Bloom's Taxonomy Level {bloom_level})
Pedagogical guidance: {bloom_note}
Mastered topics (do NOT re-explain these from scratch): {mastered_str}
Topics needing reinforcement (give extra Socratic attention here): {weak_str}
{language_instruction}
--- END STUDENT PROFILE ---"""
