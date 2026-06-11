from rest_framework import generics, filters, viewsets
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from apps.accounts.permissions import IsLecturerOrAdmin
from .models import TopicStruggle, Bookmark
from .serializers import TopicStruggleSerializer, BookmarkSerializer


class HeatmapListView(generics.ListAPIView):
    serializer_class = TopicStruggleSerializer
    permission_classes = [IsAuthenticated, IsLecturerOrAdmin]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ["course"]
    ordering_fields = ["questions_asked", "avg_confidence", "struggling_students", "updated_at"]
    ordering = ["-questions_asked"]
    search_fields = ["topic"]

    def get_queryset(self):
        user = self.request.user
        qs = TopicStruggle.objects.select_related("course")
        if user.role == "admin":
            return qs.all()
        return qs.filter(course__lecturer=user)


class BookmarkViewSet(viewsets.ViewSet, generics.ListCreateAPIView):
    serializer_class = BookmarkSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return Bookmark.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)