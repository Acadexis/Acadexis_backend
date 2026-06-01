import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def process_material(self, material_id: str):
    from .models import CourseMaterial

    try:
        material = CourseMaterial.objects.get(id=material_id)
    except CourseMaterial.DoesNotExist:
        logger.error(f"process_material: CourseMaterial {material_id} not found.")
        return

    try:
        material.status = "processing"
        material.save(update_fields=["status"])

        extracted = _extract_text_stub(material)
        page_count = extracted.get("page_count", 0)
        chunks = _chunk_text_stub(extracted.get("pages", []))

        # TODO (AI team): Generate OpenAI embeddings per chunk and create MaterialChunk records.
        # _embed_and_store_chunks(material, chunks)

        material.page_count = page_count
        material.status = "ready"
        material.save(update_fields=["page_count", "status"])

        _notify_material_ready(material)
        logger.info(f"process_material: {material.file_name} ready.")

    except Exception as exc:
        logger.error(f"process_material: Failed for {material_id} — {exc}")
        material.status = "failed"
        material.save(update_fields=["status"])
        raise self.retry(exc=exc)


def _extract_text_stub(material) -> dict:
    """STUB — AI team replaces with real text extraction."""
    return {"page_count": 1, "pages": [{"page": 1, "text": ""}]}


def _chunk_text_stub(pages: list) -> list:
    """STUB — AI team replaces with sliding-window chunking."""
    return [{"page": p["page"], "content": p["text"]} for p in pages]


def _notify_material_ready(material):
    if not material.uploaded_by:
        return
    try:
        from apps.notifications.models import Notification

        Notification.create_and_push(
            user=material.uploaded_by,
            title="Material Ready",
            body=f"{material.file_name} has been processed and is ready for study.",
            notification_type="material_ready",
            data={
                "material_id": str(material.id),
                "course_id": str(material.course.id),
            },
        )
    except Exception as e:
        logger.warning(f"_notify_material_ready: Could not send notification — {e}")
