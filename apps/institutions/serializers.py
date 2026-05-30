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
    universityId = serializers.UUIDField(source="university.id", read_only=True)

    class Meta:
        model = Faculty
        fields = ["id", "name", "university_id", "universityId"]


class DepartmentSerializer(serializers.ModelSerializer):
    faculty_id = serializers.UUIDField(source="faculty.id", read_only=True)
    facultyId = serializers.UUIDField(source="faculty.id", read_only=True)
    university_id = serializers.UUIDField(source="faculty.university.id", read_only=True)
    universityId = serializers.UUIDField(source="faculty.university.id", read_only=True)

    class Meta:
        model = Department
        fields = [
            "id",
            "name",
            "code",
            "faculty_id",
            "facultyId",
            "university_id",
            "universityId",
        ]
