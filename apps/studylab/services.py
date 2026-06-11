from django.conf import settings
from django.db.models import F
from pgvector.django import CosineDistance
from apps.courses.models import MaterialChunk
from .models import ChatMessage, MessageSource

SYSTEM_PROMPT = """You are Acadexis, an academic AI tutor.
ONLY answer using the provided course context. Cite page numbers.
If the context lacks the answer, say so plainly."""


def get_openai_client():
    try:
        from openai import OpenAI
        return OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else OpenAI()
    except TypeError:
        import openai as openai_module
        if settings.OPENAI_API_KEY:
            openai_module.api_key = settings.OPENAI_API_KEY
        return openai_module


def retrieve(course_id, question, k=5):
    """
    Search MaterialChunks using keyword string overlap matching.
    Avoids pgvector requirements to support SQLite and local development.
    """
    chunks = MaterialChunk.objects.filter(
        material__course_id=course_id,
        material__status="ready"
    ).select_related("material")
    
    if not chunks.exists():
        return []

    # Clean query into lowercase keywords of significant length
    words = [w.lower() for w in question.split() if len(w) > 2]
    if not words:
        # Fallback to returning the first k chunks if query has no keywords
        return list(chunks[:k])

    # Rank chunks by overlap score
    ranked_chunks = []
    for chunk in chunks:
        content_lower = chunk.content.lower()
        score = sum(1 for word in words if word in content_lower)
        if score > 0:
            ranked_chunks.append((score, chunk))

    # Sort by score descending
    ranked_chunks.sort(key=lambda x: x[0], reverse=True)

    return [chunk for score, chunk in ranked_chunks[:k]]


def answer_question(session, question: str) -> ChatMessage:
    """
    Retrieves context chunks, queries OpenAI if key is present,
    otherwise generates a high-quality simulated response citing chunks.
    """
    chunks = retrieve(session.course_id, question)
    context = "\n\n".join(
        f"[{c.material.file_name} p.{c.page}]\n{c.content}" for c in chunks
    )

    answer = None
    if settings.OPENAI_API_KEY:
        try:
            client = get_openai_client()
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}"},
                ],
                temperature=0.2,
            )
            answer = completion.choices[0].message.content
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"OpenAI chat completion failed: {e}. Falling back to mock response.")

    if not answer:
        # Generate a premium, friendly mock response grounded in retrieved chunks
        if chunks:
            citations = ", ".join(f"{c.material.file_name} (Page {c.page})" for c in chunks[:2])
            answer = (
                f"Hello! I am Acadexis, your academic AI tutor. "
                f"Based on the course materials in **{citations}**, "
                f"here is what I found regarding your question *\"{question}\"*:\n\n"
            )
            for c in chunks[:2]:
                snippet = c.content.strip()
                if snippet:
                    answer += f"> ... {snippet} ...\n\n"
            answer += "Is there anything specific from these pages you would like me to explain further?"
        else:
            answer = (
                f"I am Acadexis, your AI tutor. I couldn't find any specific matches for your question "
                f"in the course materials. Could you please rephrase or try another query?"
            )

    msg = ChatMessage.objects.create(session=session, role="assistant", content=answer)
    MessageSource.objects.bulk_create([
        MessageSource(message=msg, material=c.material, page=c.page,
                      snippet=c.content[:240])
        for c in chunks
    ])
    return msg