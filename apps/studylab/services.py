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
    client = get_openai_client()
    qvec = client.embeddings.create(
        model="text-embedding-3-small", input=[question]
    ).data[0].embedding

    return list(
        MaterialChunk.objects
        .filter(material__course_id=course_id, material__status="ready")
        .annotate(distance=CosineDistance("embedding", qvec))
        .order_by("distance")[:k]
        .select_related("material")
    )


def answer_question(session, question: str) -> ChatMessage:
    chunks = retrieve(session.course_id, question)
    context = "\n\n".join(
        f"[{c.material.file_name} p.{c.page}]\n{c.content}" for c in chunks
    )

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

    msg = ChatMessage.objects.create(session=session, role="assistant", content=answer)
    MessageSource.objects.bulk_create([
        MessageSource(message=msg, material=c.material, page=c.page,
                      snippet=c.content[:240])
        for c in chunks
    ])
    return msg