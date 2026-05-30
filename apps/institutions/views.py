from rest_framework import generics, filters
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
            from apps.accounts.permissions import IsAdmin
            return [IsAdmin()]
        return [IsAuthenticated()]


class UniversityDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = University.objects.all()
    serializer_class = UniversitySerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT", "DELETE"):
            from apps.accounts.permissions import IsAdmin
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
            from apps.accounts.permissions import IsAdmin
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
        faculty_id = self.request.query_params.get("faculty")
        university_id = self.request.query_params.get("university")
        if faculty_id:
            qs = qs.filter(faculty__id=faculty_id)
        if university_id:
            qs = qs.filter(faculty__university__id=university_id)
        return qs

    def get_permissions(self):
        if self.request.method == "POST":
            from apps.accounts.permissions import IsLecturerOrAdmin
            return [IsLecturerOrAdmin()]
        return [IsAuthenticated()]


class DepartmentDetailView(generics.RetrieveAPIView):
    queryset = Department.objects.select_related("faculty__university").all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]
