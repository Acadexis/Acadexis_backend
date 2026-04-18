from rest_framework import serializers
from .models import University, Faculty, Department

class UniversitySerializer(serializers.ModelSerializer):
    class Meta: model = University; fields = ["id", "name"]

class FacultySerializer(serializers.ModelSerializer):
    class Meta: model = Faculty; fields = ["id", "name", "university"]

class DepartmentSerializer(serializers.ModelSerializer):
    class Meta: model = Department; fields = ["id", "name", "faculty"]