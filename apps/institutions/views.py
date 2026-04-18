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