# Copilot Prompt — Acadexis Backend: Courses & Academic Structure

---

## Context

This is the Django REST Framework backend (`Django 5.1.7`, `djangorestframework 3.16.1`) for **Acadexis**. Two Django apps are in scope for this prompt:

- `institutions` — Universities, Faculties, Departments
- `courses` — Courses, Enrollments, CourseRatings, and the stub models for Modules

Auth, User, and Profile are handled and working from previous prompts. Do not touch `accounts/` unless reading a FK relationship.

The root `urls.py` must include both apps:

```python
# Acadexis_backend/urls.py
urlpatterns = [
    path("api/auth/",         include("accounts.urls")),
    path("api/",              include("institutions.urls")),
    path("api/",              include("courses.urls")),
    ...
]
```

---

## Part A — Institutions App

### A1: Confirm or create the models in `institutions/models.py`

```python
# institutions/models.py
import uuid
from django.db import models

class University(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name        = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    logo        = models.ImageField(upload_to="university_logos/", null=True, blank=True)
    code        = models.CharField(max_length=20, unique=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "universities"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Faculty(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name       = models.CharField(max_length=255)
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name="faculties")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "faculties"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} — {self.university.name}"


class Department(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name       = models.CharField(max_length=255)
    code       = models.CharField(max_length=20, blank=True, default="")
    faculty    = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name="departments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.faculty.university.name})"
```

Run `python manage.py makemigrations institutions` and `python manage.py migrate` after confirming the model.

---

### A2: Serializers for institutions

```python
# institutions/serializers.py
from rest_framework import serializers
from .models import University, Faculty, Department


class UniversitySerializer(serializers.ModelSerializer):
    logo = serializers.SerializerMethodField()

    class Meta:
        model = University
        fields = ["id", "name", "description", "logo", "code"]

    def get_logo(self, obj):
        if obj.logo:
            request = self.context.get("request")
            return request.build_absolute_uri(obj.logo.url) if request else obj.logo.url
        return None


class FacultySerializer(serializers.ModelSerializer):
    university_id = serializers.UUIDField(source="university.id", read_only=True)

    class Meta:
        model = Faculty
        fields = ["id", "name", "university_id"]


class DepartmentSerializer(serializers.ModelSerializer):
    faculty_id    = serializers.UUIDField(source="faculty.id", read_only=True)
    university_id = serializers.UUIDField(source="faculty.university.id", read_only=True)

    class Meta:
        model = Department
        fields = ["id", "name", "code", "faculty_id", "university_id"]
```

The frontend's `api.ts` mock contract expects:
- University: `{ id, name }`
- Faculty: `{ id, name, universityId }` — map to `university_id` in the serializer
- Department: `{ id, name, facultyId }` — map to `faculty_id` in the serializer

Both camelCase aliases (`universityId`, `facultyId`) and the snake_case versions are returned so the frontend can read either. Do not return only one and break the other.

---

### A3: Views and URL routing for institutions

```python
# institutions/views.py
from rest_framework import generics, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from .models import University, Faculty, Department
from .serializers import UniversitySerializer, FacultySerializer, DepartmentSerializer


class UniversityListCreateView(generics.ListCreateAPIView):
    queryset = University.objects.all().order_by("name")
    serializer_class = UniversitySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "code"]
    ordering_fields = ["name", "created_at"]

    def get_permissions(self):
        if self.request.method == "POST":
            from accounts.permissions import IsAdmin
            return [IsAdmin()]
        return [IsAuthenticated()]


class UniversityDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = University.objects.all()
    serializer_class = UniversitySerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT", "DELETE"):
            from accounts.permissions import IsAdmin
            return [IsAdmin()]
        return [IsAuthenticated()]


class FacultyListCreateView(generics.ListCreateAPIView):
    serializer_class = FacultySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        university_id = self.request.query_params.get("university")
        qs = Faculty.objects.select_related("university").all()
        if university_id:
            qs = qs.filter(university__id=university_id)
        return qs

    def get_permissions(self):
        if self.request.method == "POST":
            from accounts.permissions import IsAdmin
            return [IsAdmin()]
        return [IsAuthenticated()]


class FacultyDetailView(generics.RetrieveAPIView):
    queryset = Faculty.objects.select_related("university").all()
    serializer_class = FacultySerializer
    permission_classes = [IsAuthenticated]


class DepartmentListCreateView(generics.ListCreateAPIView):
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Department.objects.select_related("faculty__university").all()
        faculty_id    = self.request.query_params.get("faculty")
        university_id = self.request.query_params.get("university")
        if faculty_id:
            qs = qs.filter(faculty__id=faculty_id)
        if university_id:
            qs = qs.filter(faculty__university__id=university_id)
        return qs

    def get_permissions(self):
        if self.request.method == "POST":
            from accounts.permissions import IsLecturerOrAdmin
            return [IsLecturerOrAdmin()]
        return [IsAuthenticated()]


class DepartmentDetailView(generics.RetrieveAPIView):
    queryset = Department.objects.select_related("faculty__university").all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]
```

```python
# institutions/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("universities/",          views.UniversityListCreateView.as_view(),  name="university-list"),
    path("universities/<uuid:pk>/", views.UniversityDetailView.as_view(),     name="university-detail"),
    path("faculties/",             views.FacultyListCreateView.as_view(),     name="faculty-list"),
    path("faculties/<uuid:pk>/",   views.FacultyDetailView.as_view(),        name="faculty-detail"),
    path("departments/",           views.DepartmentListCreateView.as_view(), name="department-list"),
    path("departments/<uuid:pk>/", views.DepartmentDetailView.as_view(),     name="department-detail"),
]
```

---

### A4: Permission classes needed in `accounts/permissions.py`

These are referenced by the institution views. If they don't exist yet, add them:

```python
# accounts/permissions.py
from rest_framework.permissions import BasePermission

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "admin"

class IsLecturer(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "lecturer"

class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "student"

class IsLecturerOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ("lecturer", "admin")
```

---

### A5: Seed data management command

Create a management command so the team can populate institutions quickly during development:

```python
# institutions/management/commands/seed_institutions.py
from django.core.management.base import BaseCommand
from institutions.models import University, Faculty, Department

class Command(BaseCommand):
    help = "Seed universities, faculties, and departments with sample data"

    def handle(self, *args, **kwargs):
        uni, _ = University.objects.get_or_create(
            code="UNILAG",
            defaults={"name": "University of Lagos", "description": "A top Nigerian university"}
        )
        fac, _ = Faculty.objects.get_or_create(
            name="Faculty of Science",
            university=uni
        )
        Department.objects.get_or_create(
            name="Computer Science",
            faculty=fac,
            defaults={"code": "CS"}
        )
        Department.objects.get_or_create(
            name="Mathematics",
            faculty=fac,
            defaults={"code": "MTH"}
        )
        self.stdout.write(self.style.SUCCESS("Institutions seeded successfully."))
```

Run with: `python manage.py seed_institutions`

---

## Part B — Courses App

### B1: Confirm or create models in `courses/models.py`

```python
# courses/models.py
import uuid
from django.db import models
from django.conf import settings
from institutions.models import Department


class Course(models.Model):
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title           = models.CharField(max_length=255)
    code            = models.CharField(max_length=20, unique=True)
    description     = models.TextField(blank=True, default="")
    department      = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, related_name="courses")
    lecturer        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="taught_courses")
    thumbnail       = models.ImageField(upload_to="course_thumbnails/", null=True, blank=True)
    level           = models.CharField(max_length=50, blank=True, default="")
    lecturer_remark = models.TextField(blank=True, default="")
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} — {self.title}"

    @property
    def materials_count(self):
        return self.materials.filter(status="ready").count()

    @property
    def students_enrolled(self):
        return self.enrollments.count()


class Enrollment(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments")
    course     = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("student", "course")

    def __str__(self):
        return f"{self.student.email} → {self.course.code}"


class CourseRating(models.Model):
    REACTION_CHOICES = [("up", "Up"), ("down", "Down")]

    user     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ratings")
    course   = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="ratings")
    score    = models.IntegerField()          # 1–5
    reaction = models.CharField(max_length=10, choices=REACTION_CHOICES)

    class Meta:
        unique_together = ("user", "course")

    def __str__(self):
        return f"{self.user.email} rated {self.course.code}: {self.score}"


class CourseModule(models.Model):
    """Stub model — to be fully expanded when module feature is built."""
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course      = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    title       = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    order       = models.PositiveIntegerField(default=0)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.course.code} — Module {self.order}: {self.title}"
```

Run `python manage.py makemigrations courses` and `python manage.py migrate`.

---

### B2: Course serializers

```python
# courses/serializers.py
from rest_framework import serializers
from .models import Course, Enrollment, CourseRating, CourseModule
from accounts.serializers import UserSerializer  # The canonical user serializer from previous prompt


class CourseListSerializer(serializers.ModelSerializer):
    """Lightweight serializer — used in list views to avoid N+1."""
    department_id   = serializers.UUIDField(source="department.id", read_only=True)
    lecturer_id     = serializers.UUIDField(source="lecturer.id", read_only=True)
    lecturer_name   = serializers.SerializerMethodField()
    materials_count = serializers.IntegerField(source="materials_count", read_only=True)
    students_enrolled = serializers.IntegerField(source="students_enrolled", read_only=True)
    thumbnail       = serializers.SerializerMethodField()
    is_enrolled     = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            "id", "title", "code", "description", "level",
            "department_id", "lecturer_id", "lecturer_name",
            "materials_count", "students_enrolled",
            "thumbnail", "is_enrolled", "created_at",
        ]

    def get_lecturer_name(self, obj):
        if not obj.lecturer:
            return None
        profile = getattr(obj.lecturer, "profile", None)
        if profile:
            return f"{profile.first_name} {profile.last_name}".strip() or obj.lecturer.email
        return obj.lecturer.email

    def get_thumbnail(self, obj):
        if obj.thumbnail:
            request = self.context.get("request")
            return request.build_absolute_uri(obj.thumbnail.url) if request else obj.thumbnail.url
        return None

    def get_is_enrolled(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.enrollments.filter(student=request.user).exists()
        return False


class CourseDetailSerializer(CourseListSerializer):
    """Full serializer — used in retrieve/create/update views."""
    lecturer = UserSerializer(read_only=True)
    lecturer_id = serializers.PrimaryKeyRelatedField(
        queryset=__import__("accounts.models", fromlist=["User"]).User.objects.filter(role="lecturer"),
        source="lecturer",
        write_only=True,
        required=False,
    )
    department = serializers.PrimaryKeyRelatedField(
        queryset=__import__("institutions.models", fromlist=["Department"]).Department.objects.all(),
        required=False,
    )
    lecturer_remark = serializers.CharField(required=False, allow_blank=True)

    class Meta(CourseListSerializer.Meta):
        fields = CourseListSerializer.Meta.fields + [
            "lecturer", "lecturer_remark", "updated_at",
        ]


class CourseWriteSerializer(serializers.ModelSerializer):
    """Used only for POST/PATCH — clean input serializer."""
    class Meta:
        model = Course
        fields = ["title", "code", "description", "department", "level", "lecturer_remark", "thumbnail"]

    def validate_code(self, value):
        qs = Course.objects.filter(code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A course with this code already exists.")
        return value


class CourseModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseModule
        fields = ["id", "course", "title", "description", "order", "created_at"]
        read_only_fields = ["id", "created_at"]
```

---

### B3: Course views

```python
# courses/views.py
from rest_framework import generics, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from .models import Course, Enrollment, CourseRating, CourseModule
from .serializers import (
    CourseListSerializer, CourseDetailSerializer,
    CourseWriteSerializer, CourseModuleSerializer,
)
from accounts.permissions import IsLecturerOrAdmin, IsLecturer


class CourseViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["department", "lecturer", "level"]
    search_fields = ["title", "code", "description"]
    ordering_fields = ["created_at", "title"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return Course.objects.select_related(
            "department__faculty__university", "lecturer__profile"
        ).prefetch_related("enrollments", "materials").all()

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return CourseWriteSerializer
        if self.action == "retrieve":
            return CourseDetailSerializer
        return CourseListSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsLecturerOrAdmin()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        # Automatically assign the requesting lecturer as the course owner
        serializer.save(lecturer=self.request.user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    @action(detail=False, methods=["get"], url_path="mine")
    def mine(self, request):
        """
        Returns courses the user teaches (lecturer) or is enrolled in (student).
        Frontend uses this for role-aware dashboard course lists.
        """
        user = request.user
        if user.role == "lecturer":
            qs = Course.objects.filter(lecturer=user).select_related(
                "department", "lecturer__profile"
            ).prefetch_related("enrollments", "materials")
        else:
            enrolled_ids = Enrollment.objects.filter(student=user).values_list("course_id", flat=True)
            qs = Course.objects.filter(id__in=enrolled_ids).select_related(
                "department", "lecturer__profile"
            ).prefetch_related("enrollments", "materials")
        serializer = CourseListSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="enroll")
    def enroll(self, request, pk=None):
        """Student enrolls in a course. Idempotent — safe to call more than once."""
        course = self.get_object()
        if request.user.role != "student":
            return Response(
                {"detail": "Only students can enroll in courses."},
                status=status.HTTP_403_FORBIDDEN
            )
        Enrollment.objects.get_or_create(student=request.user, course=course)
        return Response({"success": True})

    @action(detail=True, methods=["post"], url_path="rate")
    def rate(self, request, pk=None):
        """Rate a course. One rating per user per course — updates if already rated."""
        course = self.get_object()
        score    = request.data.get("score")
        reaction = request.data.get("reaction")

        if score is None or reaction not in ("up", "down"):
            return Response(
                {"detail": "Provide a valid score (1–5) and reaction ('up' or 'down')."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            score = int(score)
            if not (1 <= score <= 5):
                raise ValueError
        except (ValueError, TypeError):
            return Response({"detail": "Score must be an integer between 1 and 5."}, status=400)

        CourseRating.objects.update_or_create(
            user=request.user, course=course,
            defaults={"score": score, "reaction": reaction},
        )
        return Response({"success": True})

    @action(detail=True, methods=["get"], url_path="sessions")
    def sessions(self, request, pk=None):
        """Returns all study sessions for this course belonging to the requesting user."""
        course = self.get_object()
        from studylab.models import StudySession
        from studylab.serializers import StudySessionSerializer
        qs = StudySession.objects.filter(course=course, user=request.user).order_by("-created_at")
        serializer = StudySessionSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)
```

---

### B4: Modules view (stub — supports the frontend `/modules?courseId=` call)

```python
# courses/views.py (add below CourseViewSet)

class CourseModuleListView(generics.ListAPIView):
    """
    GET /api/modules/?course=<courseId>
    Returns modules for a course ordered by their position.
    This is a stub — modules are not yet fully featured but the endpoint
    must exist to avoid 404s from the frontend course detail page.
    """
    serializer_class = CourseModuleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        course_id = self.request.query_params.get("course")
        if not course_id:
            return CourseModule.objects.none()
        return CourseModule.objects.filter(course__id=course_id).order_by("order")


class CourseModuleDetailView(generics.RetrieveAPIView):
    """GET /api/modules/<id>/"""
    queryset = CourseModule.objects.select_related("course").all()
    serializer_class = CourseModuleSerializer
    permission_classes = [IsAuthenticated]
```

---

### B5: Recommendations stub endpoint

The frontend calls `GET /recommendations?courseId=<id>`. This feature is not fully built yet but the endpoint must return a valid empty response rather than a 404:

```python
# courses/views.py (add below modules views)
from rest_framework.views import APIView

class CourseRecommendationsView(APIView):
    """
    GET /api/recommendations/?course=<courseId>
    Stub endpoint — returns an empty list until the recommendation engine is built.
    Shape is a list of Course objects using CourseListSerializer.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # TODO: replace with real recommendation logic
        return Response([])
```

---

### B6: URL routing for the courses app

```python
# courses/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"courses", views.CourseViewSet, basename="course")

urlpatterns = [
    path("", include(router.urls)),
    path("modules/",             views.CourseModuleListView.as_view(),   name="module-list"),
    path("modules/<uuid:pk>/",   views.CourseModuleDetailView.as_view(), name="module-detail"),
    path("recommendations/",     views.CourseRecommendationsView.as_view(), name="recommendations"),
]
```

This produces the following routes (all under `/api/`):

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/courses/` | List courses (paginated, filterable) |
| POST | `/api/courses/` | Create course (lecturer only) |
| GET | `/api/courses/{id}/` | Course detail |
| PATCH | `/api/courses/{id}/` | Update course (lecturer only) |
| DELETE | `/api/courses/{id}/` | Delete course (lecturer only) |
| GET | `/api/courses/mine/` | Role-filtered course list |
| POST | `/api/courses/{id}/enroll/` | Student enrolls |
| POST | `/api/courses/{id}/rate/` | Rate a course |
| GET | `/api/courses/{id}/sessions/` | Study sessions for course |
| GET | `/api/modules/?course=uuid` | Modules for a course |
| GET | `/api/modules/{id}/` | Single module detail |
| GET | `/api/recommendations/?course=uuid` | Course recommendations (stub) |

---

### B7: Course response shapes — what the frontend expects

**List item** (from `GET /api/courses/` and `GET /api/courses/mine/`):

```json
{
  "id": "uuid",
  "title": "Introduction to Python",
  "code": "CS101",
  "description": "Learn Python basics",
  "level": "100",
  "department_id": "uuid",
  "lecturer_id": "uuid",
  "lecturer_name": "Dr. Jane Smith",
  "materials_count": 4,
  "students_enrolled": 32,
  "thumbnail": "http://localhost:8000/media/course_thumbnails/cs101.jpg",
  "is_enrolled": true,
  "created_at": "2024-05-27T10:30:00Z"
}
```

**Detail item** (from `GET /api/courses/{id}/`):

```json
{
  "id": "uuid",
  "title": "Introduction to Python",
  "code": "CS101",
  "description": "Learn Python basics",
  "level": "100",
  "department_id": "uuid",
  "lecturer_id": "uuid",
  "lecturer_name": "Dr. Jane Smith",
  "lecturer": {
    "id": "uuid",
    "email": "jane@university.edu",
    "role": "lecturer",
    "university": "uuid",
    "name": "Dr. Jane Smith",
    "profile": { ... }
  },
  "lecturer_remark": "Complete all exercises before each class.",
  "materials_count": 4,
  "students_enrolled": 32,
  "thumbnail": "http://localhost:8000/media/course_thumbnails/cs101.jpg",
  "is_enrolled": true,
  "created_at": "2024-05-27T10:30:00Z",
  "updated_at": "2024-05-27T12:00:00Z"
}
```

---

### B8: Pagination

All list endpoints must use the global DRF pagination config. Add this to `settings.py` if not already set:

```python
REST_FRAMEWORK = {
    ...
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
}
```

Install `django-filter` if not present: `pip install django-filter --break-system-packages` and add `"django_filters"` to `INSTALLED_APPS`.

All list responses follow this paginated envelope:

```json
{
  "count": 42,
  "next": "http://localhost:8000/api/courses/?page=2",
  "previous": null,
  "results": [ ... ]
}
```

---

### B9: Register both apps in `INSTALLED_APPS`

```python
# settings.py
INSTALLED_APPS = [
    ...
    "institutions",
    "courses",
    "django_filters",
]
```

---

### B10: General rules

- All serializer output must use `snake_case` keys.
- Any FK to another model must serialize as the UUID string (not a nested object) in list views. Use nested serializers only in detail views where explicitly specified.
- `is_enrolled` must be computed per-request — never a stored field.
- `materials_count` and `students_enrolled` are computed properties on the model — do not store them as DB columns.
- The `CourseViewSet` must call `select_related` and `prefetch_related` to prevent N+1 queries on the courses list.
- Do not expose `lecturer__password`, `is_staff`, or `is_superuser` in any course-related serializer output.
