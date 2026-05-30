# Acadexis — Django Backend Implementation Guide

A complete, copy‑paste ready blueprint for building the **Acadexis** backend (Institutional AI Knowledge Grounding SaaS) using **Django 5 + Django REST Framework + PostgreSQL + Celery + pgvector**.

This guide mirrors the existing React frontend (`src/services/api.ts`, `src/store/useAppStore.ts`, `src/App.tsx`) so endpoints, payloads, and field names line up 1:1.

---

## Table of Contents
1. [Tech Stack](#1-tech-stack)
2. [Project Structure](#2-project-structure)
3. [Environment & Settings](#3-environment--settings)
4. [Apps & Domain Models](#4-apps--domain-models)
5. [Authentication (JWT + Roles)](#5-authentication-jwt--roles)
6. [Serializers](#6-serializers)
7. [Views & Routing (matches frontend `api.ts`)](#7-views--routing)
8. [PDF Ingestion + RAG Pipeline (Celery)](#8-pdf-ingestion--rag-pipeline)
9. [Study Lab Chat (LLM + Citations)](#9-study-lab-chat)
10. [Heatmap Analytics](#10-heatmap-analytics)
11. [Notifications (Realtime)](#11-notifications-realtime)
12. [File Uploads & Storage](#12-file-uploads--storage)
13. [Permissions](#13-permissions)
14. [CORS, Pagination, Throttling](#14-cors-pagination-throttling)
15. [Testing](#15-testing)
16. [Deployment](#16-deployment)
17. [API Reference (Frontend ↔ Backend Map)](#17-api-reference)

---

## 1. Tech Stack

| Layer | Choice |
|---|---|
| Framework | Django 5.0 |
| API | Django REST Framework 3.15 |
| Auth | `djangorestframework-simplejwt` |
| DB | PostgreSQL 16 + `pgvector` |
| Async tasks | Celery 5 + Redis |
| Realtime | Django Channels + Redis |
| Storage | django‑storages + S3 (or local in dev) |
| LLM | OpenAI / Anthropic (configurable) |
| Embeddings | `text-embedding-3-small` |
| PDF parsing | `pypdf`, `pdfplumber` |
| CORS | `django-cors-headers` |

### `requirements.txt`
```txt
Django==5.0.6
djangorestframework==3.15.1
djangorestframework-simplejwt==5.3.1
django-cors-headers==4.3.1
django-filter==24.2
django-storages[boto3]==1.14.3
psycopg[binary]==3.1.19
pgvector==0.2.5
celery==5.4.0
redis==5.0.4
channels==4.1.0
channels-redis==4.2.0
daphne==4.1.2
pypdf==4.2.0
pdfplumber==0.11.0
openai==1.30.1
python-decouple==3.8
Pillow==10.3.0
gunicorn==22.0.0
```

---

## 2. Project Structure

```
acadexis_backend/
├── manage.py
├── requirements.txt
├── .env
├── acadexis/                    # project package
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   ├── wsgi.py
│   └── celery.py
└── apps/
    ├── accounts/                # User, Profile, JWT
    ├── institutions/            # University → Faculty → Department
    ├── courses/                 # Course, Enrollment, Material
    ├── studylab/                # StudySession, ChatMessage, Feedback
    ├── analytics/               # Heatmap, Aggregates, Bookmarks
    ├── notifications/           # Notification + Channels
    └── support/                 # Contact, Report, AdminRequest
```

Create with:
```bash
django-admin startproject acadexis .
mkdir apps && cd apps
for app in accounts institutions courses studylab analytics notifications support; do
  python ../manage.py startapp $app
  mv $app ../apps/
done
```

---

## 3. Environment & Settings

### `.env`
```env
DEBUG=True
SECRET_KEY=change-me
DATABASE_URL=postgres://acadexis:acadexis@localhost:5432/acadexis
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=sk-...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_STORAGE_BUCKET_NAME=acadexis-media
AWS_S3_REGION_NAME=us-east-1
FRONTEND_ORIGIN=http://localhost:8080
```

### `acadexis/settings.py`
```python
from pathlib import Path
from datetime import timedelta
from decouple import config, Csv
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="*", cast=Csv())

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # 3rd party
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_filters",
    "channels",
    "storages",

    # local
    "apps.accounts",
    "apps.institutions",
    "apps.courses",
    "apps.studylab",
    "apps.analytics",
    "apps.notifications",
    "apps.support",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "acadexis.urls"
ASGI_APPLICATION = "acadexis.asgi.application"
WSGI_APPLICATION = "acadexis.wsgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

DATABASES = {"default": dj_database_url.parse(config("DATABASE_URL"))}

AUTH_USER_MODEL = "accounts.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# CORS
CORS_ALLOWED_ORIGINS = [config("FRONTEND_ORIGIN")]
CORS_ALLOW_CREDENTIALS = True

# Channels
CHANNEL_LAYERS = {"default": {
    "BACKEND": "channels_redis.core.RedisChannelLayer",
    "CONFIG": {"hosts": [config("REDIS_URL")]},
}}

# Celery
CELERY_BROKER_URL = config("REDIS_URL")
CELERY_RESULT_BACKEND = config("REDIS_URL")
CELERY_TASK_SERIALIZER = "json"

# Storage (S3 in prod, local in dev)
if not DEBUG:
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME")
else:
    MEDIA_URL = "/media/"
    MEDIA_ROOT = BASE_DIR / "media"

STATIC_URL = "/static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
TIME_ZONE = "UTC"
USE_TZ = True
LANGUAGE_CODE = "en-us"
```

### `acadexis/celery.py`
```python
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "acadexis.settings")
app = Celery("acadexis")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

### `acadexis/__init__.py`
```python
from .celery import app as celery_app
__all__ = ("celery_app",)
```

### `acadexis/asgi.py`
```python
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from apps.notifications.routing import websocket_urlpatterns

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "acadexis.settings")

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
})
```

---

## 4. Apps & Domain Models

### 4.1 `apps/institutions/models.py`
```python
from django.db import models
import uuid

class TimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

class University(TimestampedModel):
    name = models.CharField(max_length=255, unique=True)
    def __str__(self): return self.name

class Faculty(TimestampedModel):
    name = models.CharField(max_length=255)
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name="faculties")
    class Meta: unique_together = ("name", "university")

class Department(TimestampedModel):
    name = models.CharField(max_length=255)
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name="departments")
    class Meta: unique_together = ("name", "faculty")
```

### 4.2 `apps/accounts/models.py`
```python
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from apps.institutions.models import TimestampedModel, University, Department
import uuid

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        if not email: raise ValueError("Email required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", User.Role.ADMIN)
        return self.create_user(email, password, **extra)

class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        LECTURER = "lecturer", "Lecturer"
        ADMIN = "admin", "Admin"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    university = models.ForeignKey(University, on_delete=models.SET_NULL, null=True, related_name="users")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

class Profile(TimestampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    identification_number = models.CharField(max_length=50, unique=True)
    level = models.CharField(max_length=50, blank=True)  # "3rd Year", "Professor"
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, related_name="profiles")
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
```

### 4.3 `apps/courses/models.py`
```python
from django.db import models
from pgvector.django import VectorField
from apps.institutions.models import TimestampedModel, Department
from apps.accounts.models import User

class Course(TimestampedModel):
    title = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField()
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="courses")
    lecturer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="courses_taught",
                                 limit_choices_to={"role": "lecturer"})
    thumbnail = models.ImageField(upload_to="courses/thumbnails/", null=True, blank=True)
    level = models.CharField(max_length=50, blank=True)
    lecturer_remark = models.TextField(blank=True)

class Enrollment(TimestampedModel):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    class Meta: unique_together = ("student", "course")

class CourseMaterial(TimestampedModel):
    class Status(models.TextChoices):
        PROCESSING = "processing"
        READY = "ready"
        FAILED = "failed"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="materials")
    file = models.FileField(upload_to="materials/")
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=20)
    file_size = models.BigIntegerField()
    page_count = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROCESSING)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

class MaterialChunk(TimestampedModel):
    """Vector chunks for RAG."""
    material = models.ForeignKey(CourseMaterial, on_delete=models.CASCADE, related_name="chunks")
    page = models.IntegerField()
    content = models.TextField()
    embedding = VectorField(dimensions=1536)  # text-embedding-3-small

class CourseRating(TimestampedModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="ratings")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    score = models.PositiveSmallIntegerField()  # 1-5
    reaction = models.CharField(max_length=10, blank=True)  # 'up' / 'down'
    class Meta: unique_together = ("course", "user")
```

### 4.4 `apps/studylab/models.py`
```python
from django.db import models
from apps.institutions.models import TimestampedModel
from apps.accounts.models import User
from apps.courses.models import Course, CourseMaterial

class StudySession(TimestampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="sessions")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    confidence_score = models.FloatField(default=0.0)  # 0-1

class ChatMessage(TimestampedModel):
    class Role(models.TextChoices):
        USER = "user"
        ASSISTANT = "assistant"
    session = models.ForeignKey(StudySession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=Role.choices)
    content = models.TextField()

class MessageSource(models.Model):
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name="sources")
    material = models.ForeignKey(CourseMaterial, on_delete=models.CASCADE)
    page = models.IntegerField()
    snippet = models.TextField()

class SessionFeedback(TimestampedModel):
    session = models.ForeignKey(StudySession, on_delete=models.CASCADE, related_name="feedback")
    rating = models.PositiveSmallIntegerField()  # 1-5
    note = models.TextField(blank=True)
```

### 4.5 `apps/analytics/models.py`
```python
from django.db import models
from apps.institutions.models import TimestampedModel
from apps.accounts.models import User
from apps.courses.models import Course, CourseMaterial
from apps.studylab.models import ChatMessage

class TopicStruggle(TimestampedModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="struggles")
    topic = models.CharField(max_length=255)
    questions_asked = models.IntegerField(default=0)
    avg_confidence = models.FloatField(default=0.0)
    struggling_students = models.IntegerField(default=0)

class Bookmark(TimestampedModel):
    class Kind(models.TextChoices):
        SNIPPET = "snippet"
        ANSWER = "answer"
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bookmarks")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    title = models.CharField(max_length=255)
    content = models.TextField()
    material = models.ForeignKey(CourseMaterial, on_delete=models.SET_NULL, null=True, blank=True)
    page = models.IntegerField(null=True, blank=True)
    message = models.ForeignKey(ChatMessage, on_delete=models.SET_NULL, null=True, blank=True)
```

### 4.6 `apps/notifications/models.py`
```python
from django.db import models
from apps.institutions.models import TimestampedModel
from apps.accounts.models import User

class Notification(TimestampedModel):
    class Type(models.TextChoices):
        INFO = "info"
        SUCCESS = "success"
        WARNING = "warning"
        COURSE = "course"
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=255)
    message = models.TextField()
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.INFO)
    read = models.BooleanField(default=False)
```

### 4.7 `apps/support/models.py`
```python
from django.db import models
from apps.institutions.models import TimestampedModel
from apps.accounts.models import User

class ContactMessage(TimestampedModel):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    email = models.EmailField()

class IssueReport(TimestampedModel):
    class Severity(models.TextChoices):
        LOW = "low"; MEDIUM = "medium"; HIGH = "high"; CRITICAL = "critical"
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    title = models.CharField(max_length=255)
    description = models.TextField()
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.MEDIUM)
    resolved = models.BooleanField(default=False)

class AdminRequest(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending"; APPROVED = "approved"; REJECTED = "rejected"
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="admin_requests")
    reason = models.TextField()
    document_proof = models.FileField(upload_to="admin_proofs/", null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
```

### Enable pgvector
Migration `apps/courses/migrations/0001_pgvector.py`:
```python
from django.db import migrations
class Migration(migrations.Migration):
    dependencies = []
    operations = [migrations.RunSQL("CREATE EXTENSION IF NOT EXISTS vector;")]
```

---

## 5. Authentication (JWT + Roles)

### `apps/accounts/serializers.py`
```python
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.db import transaction
from .models import User, Profile
from apps.institutions.models import University, Department

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ["first_name", "last_name", "identification_number",
                  "level", "department", "avatar"]

class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    class Meta:
        model = User
        fields = ["id", "email", "role", "university", "profile"]

class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    role = serializers.ChoiceField(choices=User.Role.choices)
    university = serializers.PrimaryKeyRelatedField(queryset=University.objects.all())
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    identification_number = serializers.CharField()
    level = serializers.CharField(required=False, allow_blank=True)
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.all())

    def create(self, validated):
        with transaction.atomic():
            user = User.objects.create_user(
                email=validated["email"],
                password=validated["password"],
                role=validated["role"],
                university=validated["university"],
            )
            Profile.objects.create(
                user=user,
                first_name=validated["first_name"],
                last_name=validated["last_name"],
                identification_number=validated["identification_number"],
                level=validated.get("level", ""),
                department=validated["department"],
            )
        return user

class CustomTokenSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["email"] = user.email
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data
```

### `apps/accounts/views.py`
```python
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import RegisterSerializer, CustomTokenSerializer, UserSerializer, ProfileSerializer

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = s.save()
        return Response({"success": True, "user": UserSerializer(user).data},
                        status=status.HTTP_201_CREATED)

class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenSerializer

class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    def get_object(self): return self.request.user

class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    def get_object(self): return self.request.user.profile
```

### `apps/accounts/urls.py`
```python
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import RegisterView, LoginView, MeView, ProfileView

urlpatterns = [
    path("register/", RegisterView.as_view()),
    path("login/", LoginView.as_view()),
    path("refresh/", TokenRefreshView.as_view()),
    path("me/", MeView.as_view()),
    path("profile/", ProfileView.as_view()),
]
```

---

## 6. Serializers (other apps — condensed)

### `apps/institutions/serializers.py`
```python
from rest_framework import serializers
from .models import University, Faculty, Department

class UniversitySerializer(serializers.ModelSerializer):
    class Meta: model = University; fields = ["id", "name"]

class FacultySerializer(serializers.ModelSerializer):
    class Meta: model = Faculty; fields = ["id", "name", "university"]

class DepartmentSerializer(serializers.ModelSerializer):
    class Meta: model = Department; fields = ["id", "name", "faculty"]
```

### `apps/courses/serializers.py`
```python
from rest_framework import serializers
from .models import Course, CourseMaterial, Enrollment, CourseRating

class CourseSerializer(serializers.ModelSerializer):
    lecturer_name = serializers.SerializerMethodField()
    materials_count = serializers.IntegerField(source="materials.count", read_only=True)
    students_enrolled = serializers.IntegerField(source="enrollments.count", read_only=True)

    class Meta:
        model = Course
        fields = ["id", "title", "code", "description", "department",
                  "lecturer", "lecturer_name", "thumbnail", "level",
                  "lecturer_remark", "materials_count", "students_enrolled",
                  "created_at"]

    def get_lecturer_name(self, obj):
        p = getattr(obj.lecturer, "profile", None)
        return f"{p.first_name} {p.last_name}" if p else obj.lecturer.email

class CourseMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseMaterial
        fields = ["id", "course", "file", "file_name", "file_type",
                  "file_size", "page_count", "status", "created_at"]
        read_only_fields = ["status", "page_count", "file_size", "file_type"]

class EnrollmentSerializer(serializers.ModelSerializer):
    class Meta: model = Enrollment; fields = ["id", "student", "course", "created_at"]

class CourseRatingSerializer(serializers.ModelSerializer):
    class Meta: model = CourseRating; fields = ["id", "course", "score", "reaction"]
```

### `apps/studylab/serializers.py`
```python
from rest_framework import serializers
from .models import StudySession, ChatMessage, MessageSource, SessionFeedback

class MessageSourceSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source="material.file_name", read_only=True)
    class Meta: model = MessageSource; fields = ["page", "snippet", "material_name"]

class ChatMessageSerializer(serializers.ModelSerializer):
    sources = MessageSourceSerializer(many=True, read_only=True)
    timestamp = serializers.DateTimeField(source="created_at", read_only=True)
    class Meta: model = ChatMessage; fields = ["id", "role", "content", "sources", "timestamp"]

class StudySessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudySession
        fields = ["id", "user", "course", "title", "description",
                  "confidence_score", "created_at"]
        read_only_fields = ["user", "confidence_score"]

class FeedbackSerializer(serializers.ModelSerializer):
    class Meta: model = SessionFeedback; fields = ["session", "rating", "note"]
```

### `apps/analytics/serializers.py`
```python
from rest_framework import serializers
from .models import TopicStruggle, Bookmark

class HeatmapSerializer(serializers.ModelSerializer):
    class Meta: model = TopicStruggle
    fields = ["topic", "questions_asked", "avg_confidence", "struggling_students"]

class BookmarkSerializer(serializers.ModelSerializer):
    class Meta: model = Bookmark
    fields = ["id", "kind", "title", "content", "material", "page", "message", "created_at"]
```

### `apps/notifications/serializers.py`
```python
from rest_framework import serializers
from .models import Notification

class NotificationSerializer(serializers.ModelSerializer):
    class Meta: model = Notification
    fields = ["id", "title", "message", "type", "read", "created_at"]
```

### `apps/support/serializers.py`
```python
from rest_framework import serializers
from .models import ContactMessage, IssueReport, AdminRequest

class ContactSerializer(serializers.ModelSerializer):
    class Meta: model = ContactMessage; fields = ["subject", "body", "email"]

class ReportSerializer(serializers.ModelSerializer):
    class Meta: model = IssueReport; fields = ["title", "description", "severity"]

class AdminRequestSerializer(serializers.ModelSerializer):
    class Meta: model = AdminRequest; fields = ["reason", "document_proof", "status"]
    read_only_fields = ["status"]
```

---

## 7. Views & Routing

### `apps/institutions/views.py`
```python
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import University, Faculty, Department
from .serializers import UniversitySerializer, FacultySerializer, DepartmentSerializer

class UniversityViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = University.objects.all()
    serializer_class = UniversitySerializer
    permission_classes = [permissions.AllowAny]

    @action(detail=True, methods=["get"])
    def faculties(self, request, pk=None):
        qs = Faculty.objects.filter(university_id=pk)
        return Response(FacultySerializer(qs, many=True).data)

class FacultyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Faculty.objects.all()
    serializer_class = FacultySerializer
    permission_classes = [permissions.AllowAny]

    @action(detail=True, methods=["get"])
    def departments(self, request, pk=None):
        qs = Department.objects.filter(faculty_id=pk)
        return Response(DepartmentSerializer(qs, many=True).data)

class DepartmentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [permissions.AllowAny]
```

### `apps/courses/views.py`
```python
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from .models import Course, CourseMaterial, Enrollment, CourseRating
from .serializers import (CourseSerializer, CourseMaterialSerializer,
                          EnrollmentSerializer, CourseRatingSerializer)
from .tasks import process_material
from .permissions import IsLecturerOrReadOnly

class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.select_related("lecturer", "department").all()
    serializer_class = CourseSerializer
    permission_classes = [permissions.IsAuthenticated, IsLecturerOrReadOnly]
    filterset_fields = ["department", "lecturer", "level"]
    search_fields = ["title", "code", "description"]

    def perform_create(self, serializer):
        serializer.save(lecturer=self.request.user)

    @action(detail=False, methods=["get"])
    def mine(self, request):
        if request.user.role == "lecturer":
            qs = self.queryset.filter(lecturer=request.user)
        else:
            qs = self.queryset.filter(enrollments__student=request.user)
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=True, methods=["post"])
    def enroll(self, request, pk=None):
        course = self.get_object()
        Enrollment.objects.get_or_create(student=request.user, course=course)
        return Response({"success": True})

    @action(detail=True, methods=["post"])
    def rate(self, request, pk=None):
        course = self.get_object()
        s = CourseRatingSerializer(data={**request.data, "course": course.id})
        s.is_valid(raise_exception=True)
        CourseRating.objects.update_or_create(
            user=request.user, course=course,
            defaults={"score": s.validated_data["score"],
                      "reaction": s.validated_data.get("reaction", "")},
        )
        return Response({"success": True})


class MaterialViewSet(viewsets.ModelViewSet):
    queryset = CourseMaterial.objects.all()
    serializer_class = CourseMaterialSerializer
    parser_classes = [MultiPartParser, FormParser]
    filterset_fields = ["course", "status"]

    def perform_create(self, serializer):
        f = self.request.FILES["file"]
        material = serializer.save(
            uploaded_by=self.request.user,
            file_name=f.name,
            file_type=f.name.split(".")[-1].lower(),
            file_size=f.size,
        )
        process_material.delay(str(material.id))
```

### `apps/courses/permissions.py`
```python
from rest_framework import permissions

class IsLecturerOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS: return True
        return request.user.is_authenticated and request.user.role == "lecturer"

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS: return True
        return obj.lecturer == request.user
```

### `apps/studylab/views.py`
```python
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import StudySession, ChatMessage, SessionFeedback
from .serializers import (StudySessionSerializer, ChatMessageSerializer,
                          FeedbackSerializer)
from .services import answer_question

class StudySessionViewSet(viewsets.ModelViewSet):
    serializer_class = StudySessionSerializer
    def get_queryset(self):
        return StudySession.objects.filter(user=self.request.user).order_by("-created_at")
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        msgs = ChatMessage.objects.filter(session_id=pk).prefetch_related("sources")
        return Response(ChatMessageSerializer(msgs, many=True).data)

    @action(detail=True, methods=["post"])
    def ask(self, request, pk=None):
        session = self.get_object()
        question = request.data.get("message", "").strip()
        if not question:
            return Response({"detail": "Empty"}, status=400)
        user_msg = ChatMessage.objects.create(session=session, role="user", content=question)
        assistant_msg = answer_question(session, question)
        return Response({
            "user": ChatMessageSerializer(user_msg).data,
            "assistant": ChatMessageSerializer(assistant_msg).data,
        })

    @action(detail=True, methods=["post"])
    def feedback(self, request, pk=None):
        s = FeedbackSerializer(data={**request.data, "session": pk})
        s.is_valid(raise_exception=True); s.save()
        return Response({"success": True})
```

### `apps/analytics/views.py`
```python
from rest_framework import viewsets
from rest_framework.response import Response
from .models import TopicStruggle, Bookmark
from .serializers import HeatmapSerializer, BookmarkSerializer

class HeatmapViewSet(viewsets.ViewSet):
    def list(self, request):
        course_id = request.query_params.get("course")
        qs = TopicStruggle.objects.filter(course_id=course_id) if course_id else TopicStruggle.objects.all()
        return Response(HeatmapSerializer(qs, many=True).data)

class BookmarkViewSet(viewsets.ModelViewSet):
    serializer_class = BookmarkSerializer
    def get_queryset(self):
        return Bookmark.objects.filter(user=self.request.user)
    def perform_create(self, s): s.save(user=self.request.user)
```

### `apps/notifications/views.py`
```python
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Notification
from .serializers import NotificationSerializer

class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by("-created_at")

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        n = self.get_object(); n.read = True; n.save()
        return Response({"success": True})

    @action(detail=False, methods=["post"])
    def read_all(self, request):
        self.get_queryset().update(read=True)
        return Response({"success": True})
```

### `apps/support/views.py`
```python
from rest_framework import generics, permissions
from rest_framework.parsers import MultiPartParser, FormParser
from .serializers import ContactSerializer, ReportSerializer, AdminRequestSerializer

class ContactView(generics.CreateAPIView):
    serializer_class = ContactSerializer
    permission_classes = [permissions.AllowAny]

class ReportView(generics.CreateAPIView):
    serializer_class = ReportSerializer
    def perform_create(self, s): s.save(user=self.request.user)

class AdminRequestView(generics.CreateAPIView):
    serializer_class = AdminRequestSerializer
    parser_classes = [MultiPartParser, FormParser]
    def perform_create(self, s): s.save(user=self.request.user)
```

### `acadexis/urls.py`
```python
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter

from apps.institutions.views import UniversityViewSet, FacultyViewSet, DepartmentViewSet
from apps.courses.views import CourseViewSet, MaterialViewSet
from apps.studylab.views import StudySessionViewSet
from apps.analytics.views import HeatmapViewSet, BookmarkViewSet
from apps.notifications.views import NotificationViewSet
from apps.support.views import ContactView, ReportView, AdminRequestView

router = DefaultRouter()
router.register("universities", UniversityViewSet)
router.register("faculties", FacultyViewSet)
router.register("departments", DepartmentViewSet)
router.register("courses", CourseViewSet)
router.register("materials", MaterialViewSet)
router.register("sessions", StudySessionViewSet, basename="sessions")
router.register("heatmap", HeatmapViewSet, basename="heatmap")
router.register("bookmarks", BookmarkViewSet, basename="bookmarks")
router.register("notifications", NotificationViewSet, basename="notifications")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include(router.urls)),
    path("api/support/contact/", ContactView.as_view()),
    path("api/support/report/", ReportView.as_view()),
    path("api/support/admin-request/", AdminRequestView.as_view()),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

---

## 8. PDF Ingestion + RAG Pipeline

### `apps/courses/tasks.py`
```python
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
```

---

## 9. Study Lab Chat

### `apps/studylab/services.py`
```python
from openai import OpenAI
from django.conf import settings
from django.db.models import F
from pgvector.django import CosineDistance
from apps.courses.models import MaterialChunk
from .models import ChatMessage, MessageSource

client = OpenAI(api_key=settings.OPENAI_API_KEY)

SYSTEM_PROMPT = """You are Acadexis, an academic AI tutor.
ONLY answer using the provided course context. Cite page numbers.
If the context lacks the answer, say so plainly."""

def retrieve(course_id, question, k=5):
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
```

---

## 10. Heatmap Analytics

Periodic Celery beat task to recompute struggle topics:

```python
# apps/analytics/tasks.py
from celery import shared_task
from collections import defaultdict
from apps.studylab.models import ChatMessage, SessionFeedback
from .models import TopicStruggle

@shared_task
def recompute_heatmap(course_id):
    # Simple heuristic: group user questions by keyword & average rating
    qs = ChatMessage.objects.filter(role="user", session__course_id=course_id)
    buckets = defaultdict(lambda: {"q": 0, "students": set(), "ratings": []})
    for m in qs.select_related("session"):
        topic = m.content.split()[0:3]  # replace with NLP topic extractor
        key = " ".join(topic).lower()
        buckets[key]["q"] += 1
        buckets[key]["students"].add(m.session.user_id)
    TopicStruggle.objects.filter(course_id=course_id).delete()
    TopicStruggle.objects.bulk_create([
        TopicStruggle(course_id=course_id, topic=k,
                      questions_asked=v["q"],
                      avg_confidence=0.5,
                      struggling_students=len(v["students"]))
        for k, v in buckets.items()
    ])
```

---

## 11. Notifications (Realtime)

### `apps/notifications/consumers.py`
```python
import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer

class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        if self.scope["user"].is_anonymous:
            await self.close(); return
        self.group = f"user_{self.scope['user'].id}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def notify(self, event):
        await self.send_json(event["payload"])
```

### `apps/notifications/routing.py`
```python
from django.urls import re_path
from .consumers import NotificationConsumer

websocket_urlpatterns = [re_path(r"ws/notifications/$", NotificationConsumer.as_asgi())]
```

### Push helper
```python
# apps/notifications/utils.py
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import Notification
from .serializers import NotificationSerializer

def push_notification(user, **kwargs):
    n = Notification.objects.create(user=user, **kwargs)
    async_to_sync(get_channel_layer().group_send)(
        f"user_{user.id}",
        {"type": "notify", "payload": NotificationSerializer(n).data},
    )
    return n
```

---

## 12. File Uploads & Storage

The `MaterialViewSet` and `AdminRequestView` accept `multipart/form-data`. Frontend example matches the existing `api.uploadMaterial()` shape:

```ts
const fd = new FormData();
fd.append("file", file);
fd.append("course", courseId);
await fetch("/api/materials/", { method: "POST", body: fd, headers: { Authorization: `Bearer ${token}` }});
```

In production, S3 returns signed URLs automatically through `django-storages`.

---

## 13. Permissions

Reusable role permissions:
```python
# apps/accounts/permissions.py
from rest_framework import permissions

class IsStudent(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "student"

class IsLecturer(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "lecturer"

class IsOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return getattr(obj, "user", None) == request.user
```

---

## 14. CORS, Pagination, Throttling

Add to `settings.py`:
```python
REST_FRAMEWORK.update({
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"user": "1000/day", "anon": "100/day"},
})
```

---

## 15. Testing

### `apps/courses/tests.py`
```python
from rest_framework.test import APITestCase
from apps.accounts.models import User
from apps.institutions.models import University, Faculty, Department

class CourseAPITests(APITestCase):
    def setUp(self):
        u = University.objects.create(name="UCT")
        f = Faculty.objects.create(name="Eng", university=u)
        self.dept = Department.objects.create(name="CS", faculty=f)
        self.lect = User.objects.create_user("l@x.com", "pass12345",
                                             role="lecturer", university=u)
        self.client.force_authenticate(self.lect)

    def test_create_course(self):
        r = self.client.post("/api/courses/", {
            "title": "ML", "code": "CS1", "description": "x",
            "department": str(self.dept.id), "lecturer": str(self.lect.id),
        })
        self.assertEqual(r.status_code, 201)
```

Run: `python manage.py test`

---

## 16. Deployment

### `Dockerfile`
```dockerfile
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "acadexis.asgi:application"]
```

### `docker-compose.yml`
```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: acadexis
      POSTGRES_PASSWORD: acadexis
      POSTGRES_DB: acadexis
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
  redis:
    image: redis:7
    ports: ["6379:6379"]
  web:
    build: .
    env_file: .env
    ports: ["8000:8000"]
    depends_on: [db, redis]
  worker:
    build: .
    command: celery -A acadexis worker -l info
    env_file: .env
    depends_on: [db, redis]
  beat:
    build: .
    command: celery -A acadexis beat -l info
    env_file: .env
    depends_on: [db, redis]
volumes:
  pgdata:
```

Run:
```bash
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

---

## 17. API Reference

Direct mapping to `src/services/api.ts`:

| Frontend method | HTTP | Endpoint |
|---|---|---|
| `api.login(email, password)` | POST | `/api/auth/login/` |
| `api.register(data)` | POST | `/api/auth/register/` |
| `api.getUniversities()` | GET | `/api/universities/` |
| `api.getFaculties(universityId)` | GET | `/api/universities/{id}/faculties/` |
| `api.getDepartments(facultyId)` | GET | `/api/faculties/{id}/departments/` |
| `api.getCourses()` | GET | `/api/courses/` |
| `api.getCourse(id)` | GET | `/api/courses/{id}/` |
| *My courses* | GET | `/api/courses/mine/` |
| *Enroll* | POST | `/api/courses/{id}/enroll/` |
| *Rate course* | POST | `/api/courses/{id}/rate/` |
| `api.getCourseMaterials(courseId)` | GET | `/api/materials/?course={id}` |
| `api.uploadMaterial(courseId, file)` | POST | `/api/materials/` (multipart) |
| *Create session* | POST | `/api/sessions/` |
| `api.getChatHistory(sessionId)` | GET | `/api/sessions/{id}/messages/` |
| `api.sendMessage(sessionId, msg)` | POST | `/api/sessions/{id}/ask/` |
| *Feedback* | POST | `/api/sessions/{id}/feedback/` |
| `api.getNotifications()` | GET | `/api/notifications/` |
| `api.markNotificationRead(id)` | POST | `/api/notifications/{id}/read/` |
| `api.getHeatmapData(courseId)` | GET | `/api/heatmap/?course={id}` |
| *Bookmarks* | GET/POST/DELETE | `/api/bookmarks/` |
| `api.updateProfile(data)` | PATCH | `/api/auth/profile/` |
| `api.submitContactForm(data)` | POST | `/api/support/contact/` |
| `api.submitReport(data)` | POST | `/api/support/report/` |
| `api.submitAdminRequest(data)` | POST | `/api/support/admin-request/` (multipart) |

### Standard auth headers
```
Authorization: Bearer <access_token>
Content-Type: application/json
```

### JWT flow
1. `POST /api/auth/login/` → `{ access, refresh, user }`
2. Send `Authorization: Bearer <access>` on every request
3. When 401, `POST /api/auth/refresh/` with `{ refresh }` → new access

---

## Quick Start Commands

```bash
# 1. Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. DB
createdb acadexis
psql acadexis -c "CREATE EXTENSION vector;"

# 3. Migrate + seed
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser

# 4. Run (3 terminals)
python manage.py runserver
celery -A acadexis worker -l info
celery -A acadexis beat -l info
```

You now have a production‑grade Django backend that drops straight into the Acadexis React frontend. 🚀
