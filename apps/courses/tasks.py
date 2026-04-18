import pdfplumber
from celery import shared_task
from openai import OpenAI
from django.conf import settings
from .models import CourseMaterial, MaterialChunk

client = OpenAI(api_key=settings.OPENAI_API_KEY if hasattr(settings, "OPENAI_API_KEY") else None)

CHUNK_SIZE = 800   # characters
CHUNK_OVERLAP = 100

def chunk_text(text: str):
    chunks, i = [], 0
    while i < len(text):
        chunks.append(text[i:i + CHUNK_SIZE])
        i += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks

def embed(texts):
    res = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [d.embedding for d in res.data]

@shared_task(bind=True, max_retries=3)
def process_material(self, material_id: str):
    m = CourseMaterial.objects.get(id=material_id)
    try:
        records = []
        with pdfplumber.open(m.file.path) as pdf:
            m.page_count = len(pdf.pages)
            for page_no, page in enumerate(pdf.pages, start=1):
                text = (page.extract_text() or "").strip()
                if not text: continue
                for chunk in chunk_text(text):
                    records.append((page_no, chunk))

        # Batch embed (100 at a time)
        for i in range(0, len(records), 100):
            batch = records[i:i+100]
            vectors = embed([c for _, c in batch])
            MaterialChunk.objects.bulk_create([
                MaterialChunk(material=m, page=p, content=c, embedding=v)
                for (p, c), v in zip(batch, vectors)
            ])

        m.status = CourseMaterial.Status.READY
        m.save()
    except Exception as exc:
        m.status = CourseMaterial.Status.FAILED
        m.save()
        raise self.retry(exc=exc, countdown=30)