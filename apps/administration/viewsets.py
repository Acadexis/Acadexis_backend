"""
Administration API ViewSets
Staff-only CRUD endpoints for all admin-manageable resources.
"""

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from apps.accounts.models import User, Profile
from apps.institutions.models import University, Faculty, Department
from apps.courses.models import Course, Enrollment, CourseMaterial, CourseRating
from apps.studylab.models import StudySession

from .permissions import IsStaffUser, IsAdminUser
from .serializers import (
    UserAdminSerializer,
    UserListSerializer,
    UniversitySerializer,
    FacultySerializer,
    DepartmentSerializer,
    CourseAdminSerializer,
    EnrollmentSerializer,
    CourseMaterialAdminSerializer,
    CourseRatingSerializer,
    StudySessionAdminSerializer,
)


class AdminBaseViewSet(viewsets.ModelViewSet):
    """
    Base viewset for admin endpoints.
    - Requires staff authentication
    - Includes search and filtering
    """

    lookup_value_regex = "[0-9a-f-]+"
    permission_classes = [IsAuthenticated, IsStaffUser]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    ordering_fields = ["id", "created_at", "updated_at"]
    ordering = ["-created_at"]

    def perform_create(self, serializer):
        """Optionally set created_by or modified_by if the model supports it."""
        if hasattr(serializer.instance, "created_by"):
            serializer.save(created_by=self.request.user)
        else:
            serializer.save()

    def perform_update(self, serializer):
        """Optionally set modified_by if the model supports it."""
        if hasattr(serializer.instance, "modified_by"):
            serializer.save(modified_by=self.request.user)
        else:
            serializer.save()

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return qs

        # If they are staff but not superuser, filter by their university
        if not user.university:
            return qs.none()

        model = self.queryset.model
        if model == User:
            return qs.filter(university=user.university)
        elif model == University:
            return qs.filter(id=user.university.id)
        elif model == Faculty:
            return qs.filter(university=user.university)
        elif model == Department:
            return qs.filter(faculty__university=user.university)
        elif model == Course:
            return qs.filter(department__faculty__university=user.university)
        elif model == Enrollment:
            return qs.filter(course__department__faculty__university=user.university)
        elif model == CourseMaterial:
            return qs.filter(course__department__faculty__university=user.university)
        elif model == CourseRating:
            return qs.filter(course__department__faculty__university=user.university)
        elif model == StudySession:
            return qs.filter(course__department__faculty__university=user.university)

        return qs



class UserAdminViewSet(AdminBaseViewSet):
    """
    Admin endpoints for User management.
    - LIST: all users with pagination, search, filter
    - CREATE: new user (staff only)
    - RETRIEVE: user detail
    - UPDATE: edit user info
    - DELETE: deactivate user (soft delete via is_active)
    - CUSTOM: /deactivate/, /activate/
    """

    lookup_value_regex = "[0-9a-f-]+"
    queryset = User.objects.all().prefetch_related("profile")
    serializer_class = UserAdminSerializer
    filterset_fields = ["role", "is_active", "university", "date_joined"]
    search_fields = ["email", "first_name", "last_name"]
    ordering_fields = ["id", "email", "first_name", "last_name", "role", "date_joined", "last_login"]
    ordering = ["-date_joined"]

    def get_serializer_class(self):
        if self.action == "list":
            return UserListSerializer
        return UserAdminSerializer

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """Deactivate a user account."""
        user = self.get_object()
        user.is_active = False
        user.save()
        return Response(
            {"detail": f"User {user.email} deactivated."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Activate a deactivated user account."""
        user = self.get_object()
        user.is_active = True
        user.save()
        return Response(
            {"detail": f"User {user.email} activated."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def promote_to_staff(self, request, pk=None):
        """Promote user to staff status."""
        user = self.get_object()
        user.is_staff = True
        user.save()
        return Response(
            {"detail": f"User {user.email} promoted to staff."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def demote_from_staff(self, request, pk=None):
        """Demote user from staff status."""
        user = self.get_object()
        user.is_staff = False
        user.save()
        return Response(
            {"detail": f"User {user.email} demoted from staff."},
            status=status.HTTP_200_OK,
        )


class UniversityAdminViewSet(AdminBaseViewSet):
    """
    Admin endpoints for University management.
    - LIST: all universities
    - CREATE: new university
    - RETRIEVE: university detail with faculty/user counts
    - UPDATE: edit university
    - DELETE: remove university
    """

    queryset = University.objects.all().prefetch_related("faculties")
    serializer_class = UniversitySerializer
    search_fields = ["name"]
    ordering_fields = ["id", "name", "created_at"]


class FacultyAdminViewSet(AdminBaseViewSet):
    """
    Admin endpoints for Faculty management.
    - LIST: all faculties with filtering by university
    - CREATE: new faculty
    - RETRIEVE: faculty detail
    - UPDATE: edit faculty
    - DELETE: remove faculty
    """

    queryset = Faculty.objects.all().select_related("university")
    serializer_class = FacultySerializer
    filterset_fields = ["university"]
    search_fields = ["name"]


class DepartmentAdminViewSet(AdminBaseViewSet):
    """
    Admin endpoints for Department management.
    - LIST: all departments with filtering by faculty
    - CREATE: new department
    - RETRIEVE: department detail
    - UPDATE: edit department
    - DELETE: remove department
    """

    queryset = Department.objects.all().select_related("faculty")
    serializer_class = DepartmentSerializer
    filterset_fields = ["faculty"]
    search_fields = ["name"]


class CourseAdminViewSet(AdminBaseViewSet):
    """
    Admin endpoints for Course management.
    - LIST: all courses with filtering by department/lecturer
    - CREATE: new course
    - RETRIEVE: course detail with enrollments/materials
    - UPDATE: edit course
    - DELETE: remove course
    """

    queryset = Course.objects.all().select_related(
        "department", "lecturer"
    ).prefetch_related("enrollments", "materials")
    serializer_class = CourseAdminSerializer
    filterset_fields = ["department", "lecturer", "level"]
    search_fields = ["title", "code", "description"]


class EnrollmentAdminViewSet(AdminBaseViewSet):
    """
    Admin endpoints for Enrollment management.
    - LIST: all enrollments with filtering by student/course
    - CREATE: manually enroll a student
    - RETRIEVE: enrollment detail
    - UPDATE: edit enrollment
    - DELETE: remove enrollment (unenroll)
    - CUSTOM: /bulk-enroll/, /bulk-unenroll/
    """

    queryset = Enrollment.objects.all().select_related("student", "course")
    serializer_class = EnrollmentSerializer
    filterset_fields = ["student", "course"]
    search_fields = ["student__email", "course__title"]

    @action(detail=False, methods=["post"])
    def bulk_enroll(self, request):
        """
        Bulk enroll students in a course.
        Expected payload: {"course_id": uuid, "student_ids": [uuid, ...]}
        """
        course_id = request.data.get("course_id")
        student_ids = request.data.get("student_ids", [])

        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        created_count = 0
        for student_id in student_ids:
            try:
                student = User.objects.get(id=student_id, role="student")
                Enrollment.objects.get_or_create(
                    student=student, course=course
                )
                created_count += 1
            except User.DoesNotExist:
                continue

        return Response(
            {
                "detail": f"Enrolled {created_count} students in {course.title}.",
                "enrolled_count": created_count,
            },
            status=status.HTTP_200_OK,
        )


class CourseMaterialAdminViewSet(AdminBaseViewSet):
    """
    Admin endpoints for CourseMaterial management.
    - LIST: all materials with filtering by course/status
    - CREATE: upload new material
    - RETRIEVE: material detail
    - UPDATE: edit material metadata
    - DELETE: remove material
    """

    queryset = CourseMaterial.objects.all().select_related(
        "course", "uploaded_by"
    )
    serializer_class = CourseMaterialAdminSerializer
    filterset_fields = ["course", "status"]
    search_fields = ["file_name", "course__title"]


class CourseRatingAdminViewSet(AdminBaseViewSet):
    """
    Admin endpoints for CourseRating management.
    - LIST: all ratings with filtering by course/score
    - RETRIEVE: rating detail
    - DELETE: remove rating
    """

    queryset = CourseRating.objects.all().select_related("course", "user")
    serializer_class = CourseRatingSerializer
    filterset_fields = ["course", "score"]
    http_method_names = ["get", "delete", "head", "options"]  # Read-only with delete


class StudySessionAdminViewSet(AdminBaseViewSet):
    """
    Admin endpoints for StudySession monitoring.
    - LIST: all study sessions with filtering by user/course
    - RETRIEVE: session detail with chat history
    - Audit purposes only (read-only)
    """

    queryset = StudySession.objects.all().select_related(
        "user", "course"
    ).prefetch_related("messages")
    serializer_class = StudySessionAdminSerializer
    filterset_fields = ["user", "course"]
    search_fields = ["user__email", "title"]
    http_method_names = ["get", "head", "options"]  # Read-only
