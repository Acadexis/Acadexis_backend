import os

from rest_framework import generics, filters, status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet
from django_filters.rest_framework import DjangoFilterBackend

from apps.studylab.models import StudySession
from apps.studylab.serializers import StudySessionSerializer
from .models import Course, CourseModule, CourseRating, Enrollment, CourseMaterial
from .serializers import (
    CourseListSerializer,
    CourseDetailSerializer,
    CourseWriteSerializer,
    CourseModuleSerializer,
    CourseMaterialSerializer,
    CourseMaterialUploadSerializer,
)
from .tasks import process_material
from apps.accounts.permissions import IsLecturerOrAdmin


class CourseViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["department", "lecturer", "level"]
    search_fields = ["title", "code", "description"]
    ordering_fields = ["created_at", "title"]
    ordering = ["-created_at"]

    def get_queryset(self):
        user = self.request.user
        base_queryset = Course.objects.select_related(
            "department__faculty__university", "lecturer__profile"
        ).prefetch_related("enrollments", "materials")

        # Students: only see courses from their university AND department
        if user.role == "student":
            if not user.university or not user.profile.department:
                return base_queryset.none()
            return base_queryset.filter(
                department__faculty__university=user.university,
                department=user.profile.department
            )

        # Lecturers: see courses in their university (they can teach across departments)
        if user.role == "lecturer":
            if not user.university:
                return base_queryset.none()
            return base_queryset.filter(department__faculty__university=user.university)

        # Admins: see all courses
        return base_queryset.all()

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

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def perform_create(self, serializer):
        serializer.save(lecturer=self.request.user)

    @action(detail=False, methods=["get"], url_path="mine")
    def mine(self, request):
        user = request.user
        if user.role == "lecturer":
            qs = Course.objects.filter(lecturer=user)
        else:
            enrolled_ids = Enrollment.objects.filter(student=user).values_list("course_id", flat=True)
            qs = Course.objects.filter(id__in=enrolled_ids)
        serializer = CourseListSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="enroll")
    def enroll(self, request, pk=None):
        course = self.get_object()
        if request.user.role != "student":
            return Response(
                {"detail": "Only students can enroll in courses."},
                status=status.HTTP_403_FORBIDDEN,
            )
        created = Enrollment.objects.get_or_create(student=request.user, course=course)
        try:
            from apps.notifications.models import Notification
            # Notify lecturer (best-effort)
            if course.lecturer:
                Notification.create_and_push(
                    user=course.lecturer,
                    title="New Enrollment",
                    body=f"{request.user.email} has enrolled in {course.title}.",
                    notification_type="new_enrollment",
                    data={"course_id": str(course.id), "student_id": str(request.user.id)},
                )
        except Exception:
            pass
        return Response({"success": True})

    @action(detail=True, methods=["post"], url_path="rate")
    def rate(self, request, pk=None):
        course = self.get_object()
        score = request.data.get("score")
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
        except (TypeError, ValueError):
            return Response(
                {"detail": "Score must be an integer between 1 and 5."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        CourseRating.objects.update_or_create(
            user=request.user,
            course=course,
            defaults={"score": score, "reaction": reaction},
        )
        return Response({"success": True})

    @action(detail=True, methods=["get"], url_path="sessions")
    def sessions(self, request, pk=None):
        course = self.get_object()
        qs = StudySession.objects.filter(course=course, user=request.user).order_by("-created_at")
        serializer = StudySessionSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)


class CourseMaterialListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/materials/?course=<uuid>&status=<status>&page=<n>
    POST /api/materials/  (multipart/form-data: course + file)
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CourseMaterialUploadSerializer
        return CourseMaterialSerializer

    def get_queryset(self):
        qs = CourseMaterial.objects.select_related("course", "uploaded_by").all()
        course_id = self.request.query_params.get("course")
        status_filter = self.request.query_params.get("status")
        if course_id:
            qs = qs.filter(course__id=course_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
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

        file = upload_serializer.validated_data["file"]
        course = upload_serializer.validated_data["course"]
        ext = os.path.splitext(file.name)[1].lower().lstrip(".")
        file_type = ext if ext in ("pdf", "docx", "pptx") else "pdf"

        material = CourseMaterial.objects.create(
            course=course,
            file=file,
            file_name=file.name,
            file_type=file_type,
            file_size=file.size,
            status="processing",
            uploaded_by=request.user,
        )

        process_material.delay(str(material.id))

        response_serializer = CourseMaterialSerializer(material, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class CourseMaterialDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/materials/<id>/
    PATCH  /api/materials/<id>/   — rename only; no re-upload
    DELETE /api/materials/<id>/   — removes file + DB record + chunks
    """
    queryset = CourseMaterial.objects.select_related("course", "uploaded_by").all()
    serializer_class = CourseMaterialSerializer
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
            if self.request.user.role != "admin" and obj.uploaded_by != self.request.user:
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


class CourseModuleListView(generics.ListAPIView):
    serializer_class = CourseModuleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        course_id = self.request.query_params.get("course")
        if not course_id:
            return CourseModule.objects.none()
        return CourseModule.objects.filter(course__id=course_id).order_by("order")


class CourseModuleDetailView(generics.RetrieveAPIView):
    queryset = CourseModule.objects.select_related("course").all()
    serializer_class = CourseModuleSerializer
    permission_classes = [IsAuthenticated]


class CourseRecommendationsView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response([])
