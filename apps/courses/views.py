from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from .models import Course, CourseMaterial, Enrollment, CourseRating
from .serializers import (CourseSerializer, CourseMaterialSerializer,
                          EnrollmentSerializer, CourseRatingSerializer)
from .tasks import process_material
from .permissions import IsLecturerOrReadOnly

class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.select_related("lecturer", "department").all()
    serializer_class = CourseSerializer
    permission_classes = [permissions.IsAuthenticated, IsLecturerOrReadOnly]
    filterset_fields = ["department", "lecturer", "level"]
    search_fields = ["title", "code", "description"]

    def perform_create(self, serializer):
        serializer.save(lecturer=self.request.user)

    @action(detail=False, methods=["get"])
    def mine(self, request):
        if request.user.role == "lecturer":
            qs = self.queryset.filter(lecturer=request.user)
        else:
            qs = self.queryset.filter(enrollments__student=request.user)
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=True, methods=["post"])
    def enroll(self, request, pk=None):
        course = self.get_object()
        Enrollment.objects.get_or_create(student=request.user, course=course)
        return Response({"success": True})

    @action(detail=True, methods=["post"])
    def rate(self, request, pk=None):
        course = self.get_object()
        s = CourseRatingSerializer(data={**request.data, "course": course.id})
        s.is_valid(raise_exception=True)
        CourseRating.objects.update_or_create(
            user=request.user, course=course,
            defaults={"score": s.validated_data["score"],
                      "reaction": s.validated_data.get("reaction", "")},
        )
        return Response({"success": True})


class MaterialViewSet(viewsets.ModelViewSet):
    queryset = CourseMaterial.objects.all()
    serializer_class = CourseMaterialSerializer
    parser_classes = [MultiPartParser, FormParser]
    filterset_fields = ["course", "status"]

    def perform_create(self, serializer):
        f = self.request.FILES["file"]
        material = serializer.save(
            uploaded_by=self.request.user,
            file_name=f.name,
            file_type=f.name.split(".")[-1].lower(),
            file_size=f.size,
        )
        process_material.delay(str(material.id))