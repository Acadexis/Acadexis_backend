from rest_framework import viewsets
from rest_framework.response import Response
from .models import TopicStruggle, Bookmark
from .serializers import HeatmapSerializer, BookmarkSerializer

class HeatmapViewSet(viewsets.ViewSet):
    def list(self, request):
        course_id = request.query_params.get("course")
        qs = TopicStruggle.objects.filter(course_id=course_id) if course_id else TopicStruggle.objects.all()
        return Response(HeatmapSerializer(qs, many=True).data)

class BookmarkViewSet(viewsets.ModelViewSet):
    serializer_class = BookmarkSerializer
    def get_queryset(self):
        return Bookmark.objects.filter(user=self.request.user)
    def perform_create(self, s): s.save(user=self.request.user)