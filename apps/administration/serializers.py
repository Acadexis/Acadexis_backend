"""
Administration API Serializers
Serializers for all admin-manageable models with proper field handling.
"""

from rest_framework import serializers
from apps.accounts.models import User, Profile
from apps.institutions.models import University, Faculty, Department
from apps.courses.models import Course, Enrollment, CourseMaterial, CourseRating
from apps.studylab.models import StudySession


class ProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile information."""

    class Meta:
        model = Profile
        fields = [
            "id",
            "first_name",
            "last_name",
            "identification_number",
            "level",
            "department",
            "avatar",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class UserAdminSerializer(serializers.ModelSerializer):
    """Serializer for User model with admin-level detail."""

    profile = ProfileSerializer(read_only=True)
    university_name = serializers.CharField(source="university.name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_active",
            "is_staff",
            "is_superuser",
            "university",
            "university_name",
            "profile",
            "date_joined",
            "last_login",
        ]
        read_only_fields = ["id", "date_joined", "last_login"]

    def validate_role(self, value):
        """Ensure role is valid."""
        valid_roles = ["student", "lecturer", "admin"]
        if value not in valid_roles:
            raise serializers.ValidationError(
                f"Role must be one of {valid_roles}"
            )
        return value


class UserListSerializer(serializers.ModelSerializer):
    """Minimal serializer for user list views (admin)."""

    university_name = serializers.CharField(source="university.name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_active",
            "university_name",
            "date_joined",
        ]
        read_only_fields = ["id", "date_joined"]


class UniversitySerializer(serializers.ModelSerializer):
    """Serializer for University model."""

    faculty_count = serializers.SerializerMethodField()
    user_count = serializers.SerializerMethodField()

    class Meta:
        model = University
        fields = [
            "id",
            "name",
            "faculty_count",
            "user_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "faculty_count", "user_count"]

    def get_faculty_count(self, obj):
        return obj.faculties.count()

    def get_user_count(self, obj):
        return obj.users.count()


class DepartmentSerializer(serializers.ModelSerializer):
    """Serializer for Department model."""

    faculty_name = serializers.CharField(source="faculty.name", read_only=True)
    course_count = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = [
            "id",
            "name",
            "faculty",
            "faculty_name",
            "course_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "course_count"]

    def get_course_count(self, obj):
        return obj.courses.count()


class FacultySerializer(serializers.ModelSerializer):
    """Serializer for Faculty model."""

    university_name = serializers.CharField(source="university.name", read_only=True)
    department_count = serializers.SerializerMethodField()

    class Meta:
        model = Faculty
        fields = [
            "id",
            "name",
            "university",
            "university_name",
            "department_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "department_count"]

    def get_department_count(self, obj):
        return obj.departments.count()


class EnrollmentSerializer(serializers.ModelSerializer):
    """Serializer for Enrollment model."""

    student_email = serializers.CharField(source="student.email", read_only=True)
    student_name = serializers.SerializerMethodField()
    course_title = serializers.CharField(source="course.title", read_only=True)
    course_code = serializers.CharField(source="course.code", read_only=True)

    class Meta:
        model = Enrollment
        fields = [
            "id",
            "student",
            "student_email",
            "student_name",
            "course",
            "course_title",
            "course_code",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}"


class CourseMaterialAdminSerializer(serializers.ModelSerializer):
    """Serializer for CourseMaterial model (admin view)."""

    course_title = serializers.CharField(source="course.title", read_only=True)
    uploaded_by_email = serializers.CharField(
        source="uploaded_by.email", read_only=True, allow_null=True
    )
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = CourseMaterial
        fields = [
            "id",
            "course",
            "course_title",
            "file",
            "file_url",
            "file_name",
            "file_type",
            "file_size",
            "page_count",
            "status",
            "uploaded_by",
            "uploaded_by_email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "page_count",
            "file_url",
            "uploaded_by_email",
        ]

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class CourseAdminSerializer(serializers.ModelSerializer):
    """Serializer for Course model (admin view)."""

    department_name = serializers.CharField(source="department.name", read_only=True)
    lecturer_email = serializers.CharField(
        source="lecturer.email", read_only=True, allow_null=True
    )
    lecturer_name = serializers.SerializerMethodField()
    enrollment_count = serializers.SerializerMethodField()
    material_count = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "code",
            "description",
            "department",
            "department_name",
            "lecturer",
            "lecturer_email",
            "lecturer_name",
            "level",
            "lecturer_remark",
            "thumbnail",
            "enrollment_count",
            "material_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "enrollment_count",
            "material_count",
            "lecturer_email",
            "lecturer_name",
        ]

    def get_lecturer_name(self, obj):
        if obj.lecturer:
            return f"{obj.lecturer.first_name} {obj.lecturer.last_name}"
        return None

    def get_enrollment_count(self, obj):
        return obj.enrollments.count()

    def get_material_count(self, obj):
        return obj.materials.count()


class CourseRatingSerializer(serializers.ModelSerializer):
    """Serializer for CourseRating model."""

    user_email = serializers.CharField(source="user.email", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)

    class Meta:
        model = CourseRating
        fields = [
            "id",
            "course",
            "course_title",
            "user",
            "user_email",
            "score",
            "reaction",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class StudySessionAdminSerializer(serializers.ModelSerializer):
    """Serializer for StudySession model (admin view)."""

    user_email = serializers.CharField(source="user.email", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = StudySession
        fields = [
            "id",
            "user",
            "user_email",
            "course",
            "course_title",
            "title",
            "description",
            "confidence_score",
            "message_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "message_count"]

    def get_message_count(self, obj):
        return obj.messages.count()
