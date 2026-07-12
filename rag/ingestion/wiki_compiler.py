"""
Acadexis — Wiki Compiler (Sprint 9)
===================================
Uses Gemini 1.5 Pro to "compile" raw core documents (syllabus, rules)
into a dense, interlinked Markdown Wiki for system prompt injection.
"""

import logging
from typing import List

from google import genai
from google.genai import types as genai_types

from rag.config import get_settings
from rag.ingestion.embedder import _get_gemini_client

logger = logging.getLogger(__name__)

_WIKI_COMPILER_SYSTEM_PROMPT = """\
You are the ACADEXIS KNOWLEDGE COMPILER. 
Your task is to transform raw academic document text (syllabi, grading rubrics, course rules) into a dense, interlinked Markdown Wiki.

This Wiki will be injected directly into an AI Tutor's system prompt to ensure 100% recall of foundational course rules.

════════════════════════════════════════════════════════════════
 COMPILATION RULES
════════════════════════════════════════════════════════════════

1. EXTRACT HARD FACTS: 
   - Grading scales (e.g., A=70+, B=60-69).
   - Deadlines and submission rules.
   - Attendance requirements and late penalties.
   - Prerequisite knowledge and software requirements.
   - Pedagogical goals and learning outcomes.

2. RESOLVE AMBIGUITIES: 
   - If a rule is mentioned multiple times with different phrasing, consolidate it into a single, authoritative statement.

3. DENSE INTERLINKING: 
   - Use Markdown internal links [Concept Name](#concept-name) to connect related sections.

4. STRUCTURE: 
   - Use H1 for the Course Title.
   - Use H2 for major categories (e.g., ## Grading Policy, ## Course Rules, ## Learning Objectives).
   - Use tables for grading scales or structured data.

5. ABSOLUTELY NO FLUFF: 
   - Do not include introductory greetings, filler text, or decorative elements.
   - Every word must be useful for a Socratic tutor guiding a student.

6. FORMAT: 
   - Valid GitHub Flavored Markdown.
   - Max 5,000 words (aim for density over length).
"""

async def compile_wiki_from_text(
    course_id: str,
    raw_text: str,
) -> str:
    """
    Compile raw text into a structured Markdown Wiki using Gemini 1.5 Pro.
    """
    settings = get_settings()
    client = _get_gemini_client()

    logger.info("WikiCompiler: Compiling wiki for course %s (%d chars)", course_id, len(raw_text))

    user_prompt = (
        f"COURSE ID: {course_id}\n\n"
        f"RAW DOCUMENT TEXT:\n{raw_text}\n\n"
        "Compile the above into a dense Markdown Wiki."
    )

    try:
        import asyncio
        loop = asyncio.get_event_loop()

        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=settings.gemini_pro_model,
                contents=user_prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=_WIKI_COMPILER_SYSTEM_PROMPT,
                    temperature=0.0,  # Deterministic for "compilation"
                    max_output_tokens=8192,
                ),
            ),
        )

        wiki_markdown = response.text.strip() if response.text else ""
        
        if not wiki_markdown:
            logger.error("WikiCompiler: Gemini returned empty wiki for course %s", course_id)
            return ""

        logger.info("WikiCompiler: Successfully compiled wiki for %s (%d chars)", course_id, len(wiki_markdown))
        return wiki_markdown

    except Exception as exc:
        logger.exception("WikiCompiler: Failed to compile wiki for course %s: %s", course_id, exc)
        return ""
