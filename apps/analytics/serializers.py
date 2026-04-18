from rest_framework import serializers
from .models import TopicStruggle, Bookmark

class HeatmapSerializer(serializers.ModelSerializer):
    class Meta: model = TopicStruggle
    fields = ["topic", "questions_asked", "avg_confidence", "struggling_students"]

class BookmarkSerializer(serializers.ModelSerializer):
    class Meta: model = Bookmark
    fields = ["id", "kind", "title", "content", "material", "page", "message", "created_at"]