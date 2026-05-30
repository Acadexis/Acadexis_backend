# Copilot Prompt — Acadexis Backend: Course Materials

---

## Context

This is the Django REST Framework backend (`Django 5.1.7`, `djangorestframework 3.16.1`) for **Acadexis**. This prompt covers the `courses` app extension for `CourseMaterial` and `MaterialChunk` models, file upload handling, and the Celery-based document ingestion pipeline.

Auth, User/Profile, Institutions, and the core Course models are already working from previous prompts. The AI/RAG integration (OpenAI embeddings, pgvector search) is handled by a separate team member — this prompt only covers the **storage, ingestion trigger, and status tracking** side. Leave any OpenAI or vector embedding logic as a clearly marked stub.

Files in scope:
- `courses/models.py` — add `CourseMaterial` and `MaterialChunk`
- `courses/serializers.py` — add material serializers
- `courses/views.py` — add material views
- `courses/tasks.py` — Celery task stub for ingestion
- `courses/urls.py` — add material URL routes
- `settings.py` — file upload and Celery config
- `Acadexis_backend/celery.py` — Celery app configuration

Do not touch `studylab/`, `accounts/`, or `institutions/`.

---

## Fix 1: Confirm Celery and Redis are configured in `settings.py`

Add the following to `settings.py` if not already present:

```python
# settings.py

# Celery
CELERY_BROKER_URL        = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND    = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT    = ["json"]
CELERY_TASK_SERIALIZER   = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE          = "UTC"

# File upload size limit — 100 MB for course materials
DATA_UPLOAD_MAX_MEMORY_SIZE = 104857600   # 100 MB in bytes
FILE_UPLOAD_MAX_MEMORY_SIZE = 104857600

# Media files
MEDIA_URL  = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
```

Also confirm `django.contrib.staticfiles` is in `INSTALLED_APPS` and that `media/` URLs are served in development by adding this to the root `urls.py`:

```python
# Acadexis_backend/urls.py (development only)
from django.conf import settings
from django.conf.urls.static import static

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

---

## Fix 2: Create the Celery app in `Acadexis_backend/celery.py`

```python
# Acadexis_backend/celery.py
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Acadexis_backend.settings")

app = Celery("Acadexis_backend")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

Update `Acadexis_backend/__init__.py` to load Celery on Django startup:

```python
# Acadexis_backend/__init__.py
from .celery import app as celery_app

__all__ = ("celery_app",)
```

---

## Fix 3: Add `CourseMaterial` and `MaterialChunk` models to `courses/models.py`

Add these two models below the existing `CourseModule` model. Do not remove or modify any existing model:

```python
# courses/models.py (append below existing models)

import os


def material_upload_path(instance, filename):
    """Store materials in a folder per course: materials/<course_id>/<filename>"""
    return f"materials/{instance.course.id}/{filename}"


class CourseMaterial(models.Model):
    STATUS_CHOICES = [
        ("processing", "Processing"),
        ("ready",      "Ready"),
        ("failed",     "Failed"),
    ]
    FILE_TYPE_CHOICES = [
        ("pdf",  "PDF"),
        ("docx", "DOCX"),
        ("pptx", "PPTX"),
    ]

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course      = models.ForeignKey(
        "Course",
        on_delete=models.CASCADE,
        related_name="materials",
    )
    file        = models.FileField(upload_to=material_upload_path)
    file_name   = models.CharField(max_length=255)
    file_type   = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES, default="pdf")
    file_size   = models.BigIntegerField()           # Bytes
    page_count  = models.IntegerField(null=True, blank=True)   # Set after processing
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default="processing")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_materials",
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.file_name} ({self.course.code}) — {self.status}"


class MaterialChunk(models.Model):
    """
    Stores text chunks extracted from a CourseMaterial.
    The `embedding` field is populated by the AI team's ingestion pipeline.
    Do NOT populate this model from the upload view — it is written by the Celery task only.
    """
    id        = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    material  = models.ForeignKey(
        CourseMaterial,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    page      = models.IntegerField()
    content   = models.TextField()          # Up to 800 characters per chunk
    # NOTE: The `embedding` VectorField (pgvector, 1536-dim) is added by the AI team.
    # Do not add it here — it requires the pgvector extension and the AI integration prompt.
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["material", "page"]

    def __str__(self):
        return f"Chunk p.{self.page} — {self.material.file_name}"
```

Run `python manage.py makemigrations courses` and `python manage.py migrate`.

---

## Fix 4: Add material serializers to `courses/serializers.py`

```python
# courses/serializers.py (append below existing serializers)

class CourseMaterialSerializer(serializers.ModelSerializer):
    file        = serializers.SerializerMethodField()
    course_id   = serializers.UUIDField(source="course.id", read_only=True)
    file_name   = serializers.CharField(read_only=True)
    file_type   = serializers.CharField(read_only=True)
    file_size   = serializers.IntegerField(read_only=True)
    page_count  = serializers.IntegerField(read_only=True, allow_null=True)
    uploaded_by = serializers.UUIDField(source="uploaded_by.id", read_only=True)
    uploaded_at = serializers.DateTimeField(source="created_at", read_only=True)  # camelCase alias

    class Meta:
        model  = CourseMaterial
        fields = [
            "id", "course_id", "file", "file_name", "file_type",
            "file_size", "page_count", "status",
            "uploaded_by", "uploaded_at", "created_at",
        ]
        read_only_fields = fields

    def get_file(self, obj):
        if obj.file:
            request = self.context.get("request")
            return request.build_absolute_uri(obj.file.url) if request else obj.file.url
        return None


class CourseMaterialUploadSerializer(serializers.Serializer):
    """Write-only serializer — used only for the POST /api/materials/ upload."""
    course = serializers.PrimaryKeyRelatedField(
        queryset=__import__("courses.models", fromlist=["Course"]).Course.objects.all()
    )
    file   = serializers.FileField()

    def validate_file(self, value):
        allowed_extensions = [".pdf", ".docx", ".pptx"]
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in allowed_extensions:
            raise serializers.ValidationError(
                f"Unsupported file type '{ext}'. Allowed: pdf, docx, pptx."
            )
        max_size = 100 * 1024 * 1024  # 100 MB
        if value.size > max_size:
            raise serializers.ValidationError("File size exceeds the 100 MB limit.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        course  = attrs.get("course")
        if request and request.user.role not in ("lecturer", "admin"):
            raise serializers.ValidationError(
                {"course": "Only lecturers can upload course materials."}
            )
        if request and course.lecturer != request.user and request.user.role != "admin":
            raise serializers.ValidationError(
                {"course": "You can only upload materials to your own courses."}
            )
        return attrs
```

---

## Fix 5: Add material views to `courses/views.py`

```python
# courses/views.py (append below existing views)

from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework import status as status_module
from .models import CourseMaterial
from .serializers import CourseMaterialSerializer, CourseMaterialUploadSerializer
from .tasks import process_material


class CourseMaterialListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/materials/?course=<uuid>&status=<status>&page=<n>
    POST /api/materials/  (multipart/form-data: course + file)
    """
    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CourseMaterialUploadSerializer
        return CourseMaterialSerializer

    def get_queryset(self):
        qs        = CourseMaterial.objects.select_related("course", "uploaded_by").all()
        course_id = self.request.query_params.get("course")
        status    = self.request.query_params.get("status")
        if course_id:
            qs = qs.filter(course__id=course_id)
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def create(self, request, *args, **kwargs):
        upload_serializer = CourseMaterialUploadSerializer(
            data=request.data,
            context={"request": request},
        )
        upload_serializer.is_valid(raise_exception=True)

        file      = upload_serializer.validated_data["file"]
        course    = upload_serializer.validated_data["course"]
        ext       = os.path.splitext(file.name)[1].lower().lstrip(".")
        file_type = ext if ext in ("pdf", "docx", "pptx") else "pdf"

        material = CourseMaterial.objects.create(
            course      = course,
            file        = file,
            file_name   = file.name,
            file_type   = file_type,
            file_size   = file.size,
            status      = "processing",
            uploaded_by = request.user,
        )

        process_material.delay(str(material.id))

        response_serializer = CourseMaterialSerializer(
            material,
            context={"request": request},
        )
        return Response(response_serializer.data, status=status_module.HTTP_201_CREATED)


class CourseMaterialDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/materials/<id>/
    PATCH  /api/materials/<id>/   — rename only; no re-upload
    DELETE /api/materials/<id>/   — removes file + DB record + chunks
    """
    queryset           = CourseMaterial.objects.select_related("course", "uploaded_by").all()
    serializer_class   = CourseMaterialSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT", "DELETE"):
            return [IsLecturerOrAdmin()]
        return [IsAuthenticated()]

    def get_object(self):
        obj = super().get_object()
        if self.request.method in ("PATCH", "PUT", "DELETE"):
            if (
                self.request.user.role != "admin"
                and obj.uploaded_by != self.request.user
            ):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("You can only modify materials you uploaded.")
        return obj

    def perform_destroy(self, instance):
        if instance.file:
            instance.file.delete(save=False)
        instance.chunks.all().delete()
        instance.delete()

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        new_name = request.data.get("file_name")
        if new_name:
            instance.file_name = new_name
            instance.save(update_fields=["file_name"])
        serializer = CourseMaterialSerializer(instance, context={"request": request})
        return Response(serializer.data)
```

---

## Fix 6: Create `courses/tasks.py` — Celery ingestion task stub

```python
# courses/tasks.py
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def process_material(self, material_id: str):
    """
    Celery task: processes an uploaded course material file.

    Steps (stubs marked TODO are for the AI integration team):
    1. Confirm status = "processing"
    2. Extract text + page count from the file
    3. Split into 800-char chunks with 100-char overlap
    4. [TODO AI] Generate OpenAI embeddings per chunk
    5. [TODO AI] Store MaterialChunk records with embedding vectors
    6. Mark status = "ready", set page_count
    7. Send "material_ready" notification to uploader
    On failure: mark status = "failed"
    """
    from courses.models import CourseMaterial

    try:
        material = CourseMaterial.objects.get(id=material_id)
    except CourseMaterial.DoesNotExist:
        logger.error(f"process_material: CourseMaterial {material_id} not found.")
        return

    try:
        material.status = "processing"
        material.save(update_fields=["status"])

        # STEP 1: Extract text
        # TODO (AI team): replace with real pypdf / python-docx / python-pptx extraction
        extracted = _extract_text_stub(material)
        page_count = extracted.get("page_count", 0)

        # STEP 2: Chunk
        # TODO (AI team): replace with real 800-char sliding-window chunking
        chunks = _chunk_text_stub(extracted.get("pages", []))

        # STEP 3+4: Embed and store
        # TODO (AI team): call OpenAI text-embedding-3-small and create MaterialChunk records
        # _embed_and_store_chunks(material, chunks)

        # STEP 5: Mark ready
        material.page_count = page_count
        material.status     = "ready"
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
    """Send in-app notification when processing completes."""
    try:
        from notifications.models import Notification
        Notification.objects.create(
            user              = material.uploaded_by,
            title             = "Material Ready",
            body              = f"{material.file_name} has been processed and is ready for study.",
            notification_type = "material_ready",
            data              = {
                "material_id": str(material.id),
                "course_id":   str(material.course.id),
            },
        )
    except Exception as e:
        logger.warning(f"_notify_material_ready: Could not create notification — {e}")
```

---

## Fix 7: Add material URL routes to `courses/urls.py`

```python
# courses/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"courses", views.CourseViewSet, basename="course")

urlpatterns = [
    path("", include(router.urls)),
    path("modules/",             views.CourseModuleListView.as_view(),       name="module-list"),
    path("modules/<uuid:pk>/",   views.CourseModuleDetailView.as_view(),     name="module-detail"),
    path("recommendations/",     views.CourseRecommendationsView.as_view(),  name="recommendations"),
    path("materials/",           views.CourseMaterialListCreateView.as_view(), name="material-list"),
    path("materials/<uuid:pk>/", views.CourseMaterialDetailView.as_view(),     name="material-detail"),
]
```

Final route table for materials:

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/materials/` | Required | List materials (filter by `course`, `status`) |
| POST | `/api/materials/` | Lecturer+ | Upload new material |
| GET | `/api/materials/{id}/` | Required | Get material detail + status |
| PATCH | `/api/materials/{id}/` | Lecturer+ | Rename material |
| DELETE | `/api/materials/{id}/` | Lecturer+ | Delete material, file, and chunks |

---

## Fix 8: Material response shape

Every material endpoint returns records in this exact shape:

```json
{
  "id": "uuid",
  "course_id": "uuid",
  "file": "http://localhost:8000/media/materials/<course_id>/lecture01.pdf",
  "file_name": "lecture01.pdf",
  "file_type": "pdf",
  "file_size": 2048576,
  "page_count": null,
  "status": "processing",
  "uploaded_by": "uuid",
  "uploaded_at": "2024-05-27T10:30:00Z",
  "created_at": "2024-05-27T10:30:00Z"
}
```

- `file` is always an absolute URL
- `page_count` is `null` while processing, integer once ready
- `uploaded_at` and `created_at` are both present (same value, different keys — frontend references both)

---

## Fix 9: S3 configuration for production

```python
# settings.py
USE_S3 = os.environ.get("USE_S3", "False") == "True"

if USE_S3:
    DEFAULT_FILE_STORAGE    = "storages.backends.s3boto3.S3Boto3Storage"
    AWS_ACCESS_KEY_ID       = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY   = os.environ.get("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME", "acadexis-media")
    AWS_S3_REGION_NAME      = os.environ.get("AWS_S3_REGION_NAME", "us-east-1")
    AWS_S3_FILE_OVERWRITE   = False
    AWS_DEFAULT_ACL         = None
    MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/"
```

---

## General Rules

- Do not import or call any OpenAI, pgvector, or embedding library. Those are stubs for the AI team.
- `process_material` must always set `status = "ready"` or `status = "failed"` — never leave a record permanently on `"processing"`.
- When a material is deleted, both the physical file and all `MaterialChunk` records must be removed.
- All serializer output uses `snake_case`. Never return camelCase.
- `file` URLs in responses must always be absolute (`request.build_absolute_uri`).
- Use the global `{ count, next, previous, results }` pagination envelope on the list endpoint.
