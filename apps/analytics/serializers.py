from rest_framework import serializers
from .models import TopicStruggle, Bookmark

class TopicStruggleSerializer(serializers.ModelSerializer):
    course = serializers.UUIDField(source="course.id", read_only=True)
    questionsAsked = serializers.IntegerField(source="questions_asked", read_only=True)
    avgConfidence = serializers.FloatField(source="avg_confidence", read_only=True)
    strugglingStudents = serializers.IntegerField(source="struggling_students", read_only=True)

    class Meta:
        model = TopicStruggle
        fields = [
            "id",
            "course",
            "topic",
            "questions_asked",
            "avg_confidence",
            "struggling_students",
            "questionsAsked",
            "avgConfidence",
            "strugglingStudents",
            "updated_at",
        ]
        read_only_fields = fields


class BookmarkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bookmark
        fields = ["id", "kind", "title", "content", "material", "page", "message", "created_at"]