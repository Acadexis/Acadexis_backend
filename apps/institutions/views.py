from rest_framework import generics, filters
from rest_framework.permissions import IsAuthenticated, AllowAny

from .models import University, Faculty, Department
from .serializers import UniversitySerializer, FacultySerializer, DepartmentSerializer


class UniversityListCreateView(generics.ListCreateAPIView):
    queryset = University.objects.all().order_by("name")
    serializer_class = UniversitySerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "code"]
    ordering_fields = ["name", "created_at"]

    def get_permissions(self):
        if self.request.method == "POST":
            from apps.accounts.permissions import IsAdmin
            return [IsAdmin()]
        # Allow public read access (for registration dropdowns)
        return [AllowAny()]


class UniversityDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = University.objects.all()
    serializer_class = UniversitySerializer

    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT", "DELETE"):
            from apps.accounts.permissions import IsAdmin
            return [IsAdmin()]
        # Allow public read access (for registration dropdowns)
        return [AllowAny()]


class FacultyListCreateView(generics.ListCreateAPIView):
    serializer_class = FacultySerializer

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
        # Allow public read access (for registration dropdowns)
        return [AllowAny()]


class FacultyDetailView(generics.RetrieveAPIView):
    queryset = Faculty.objects.select_related("university").all()
    serializer_class = FacultySerializer
    # Allow public read access (for registration dropdowns)
    permission_classes = [AllowAny()]


class DepartmentListCreateView(generics.ListCreateAPIView):
    serializer_class = DepartmentSerializer

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
        # Allow public read access (for registration dropdowns)
        return [AllowAny()]


class DepartmentDetailView(generics.RetrieveAPIView):
    queryset = Department.objects.select_related("faculty__university").all()
    serializer_class = DepartmentSerializer
    # Allow public read access (for registration dropdowns)
    permission_classes = [AllowAny()]
