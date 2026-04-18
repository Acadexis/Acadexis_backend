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