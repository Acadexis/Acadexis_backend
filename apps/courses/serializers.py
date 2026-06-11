import os

from rest_framework import serializers
from apps.accounts.models import User
from apps.accounts.serializers import UserSerializer
from apps.institutions.models import Department
from .models import Course, CourseMaterial, CourseModule, CourseRating, Enrollment


class CourseListSerializer(serializers.ModelSerializer):
    department_id = serializers.UUIDField(source="department.id", read_only=True)
    lecturer_id = serializers.UUIDField(source="lecturer.id", read_only=True)
    lecturer_name = serializers.SerializerMethodField()
    materials_count = serializers.IntegerField(read_only=True)
    students_enrolled = serializers.IntegerField(read_only=True)
    thumbnail = serializers.SerializerMethodField()
    is_enrolled = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "code",
            "description",
            "level",
            "department_id",
            "lecturer_id",
            "lecturer_name",
            "materials_count",
            "students_enrolled",
            "thumbnail",
            "is_enrolled",
            "created_at",
        ]

    def get_lecturer_name(self, obj):
        if not obj.lecturer:
            return None
        profile = getattr(obj.lecturer, "profile", None)
        if profile:
            full = f"{profile.first_name} {profile.last_name}".strip()
            return full if full else obj.lecturer.email
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


class EnrollmentSerializer(serializers.ModelSerializer):
    student_id = serializers.UUIDField(source="student.id", read_only=True)
    student_name = serializers.SerializerMethodField()
    student_email = serializers.EmailField(source="student.email", read_only=True)
    identification_number = serializers.SerializerMethodField()
    course_title = serializers.CharField(source="course.title", read_only=True)
    course_code = serializers.CharField(source="course.code", read_only=True)

    class Meta:
        model = Enrollment
        fields = [
            "id",
            "student_id",
            "student_name",
            "student_email",
            "identification_number",
            "course_title",
            "course_code",
            "created_at",
        ]

    def get_student_name(self, obj):
        profile = getattr(obj.student, "profile", None)
        if profile:
            full = f"{profile.first_name} {profile.last_name}".strip()
            return full if full else obj.student.email
        return obj.student.email

    def get_identification_number(self, obj):
        profile = getattr(obj.student, "profile", None)
        return profile.identification_number if profile else ""


class CourseDetailSerializer(CourseListSerializer):
    lecturer = UserSerializer(read_only=True)
    lecturer_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role="lecturer"),
        source="lecturer",
        write_only=True,
        required=False,
    )
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(),
        required=False,
    )
    lecturer_remark = serializers.CharField(required=False, allow_blank=True)

    class Meta(CourseListSerializer.Meta):
        fields = CourseListSerializer.Meta.fields + [
            "lecturer",
            "lecturer_remark",
            "updated_at",
        ]


class CourseWriteSerializer(serializers.ModelSerializer):
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




class CourseMaterialSerializer(serializers.ModelSerializer):
    file = serializers.SerializerMethodField()
    course_id = serializers.UUIDField(source="course.id", read_only=True)
    file_name = serializers.CharField(read_only=True)
    file_type = serializers.CharField(read_only=True)
    file_size = serializers.IntegerField(read_only=True)
    page_count = serializers.IntegerField(read_only=True, allow_null=True)
    uploaded_by = serializers.UUIDField(source="uploaded_by.id", read_only=True)
    uploaded_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = CourseMaterial
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
    course = serializers.PrimaryKeyRelatedField(queryset=Course.objects.all())
    file = serializers.FileField()

    def validate_file(self, value):
        allowed_extensions = [".pdf", ".docx", ".pptx"]
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in allowed_extensions:
            raise serializers.ValidationError(
                f"Unsupported file type '{ext}'. Allowed: pdf, docx, pptx."
            )
        max_size = 100 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError("File size exceeds the 100 MB limit.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        course = attrs.get("course")
        if request and request.user.role not in ("lecturer", "admin"):
            raise serializers.ValidationError(
                {"course": "Only lecturers can upload course materials."}
            )
        if request and course and course.lecturer != request.user and request.user.role != "admin":
            raise serializers.ValidationError(
                {"course": "You can only upload materials to your own courses."}
            )
        return attrs


class CourseModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseModule
        fields = ["id", "course", "title", "description", "order", "created_at"]
        read_only_fields = ["id", "created_at"]
