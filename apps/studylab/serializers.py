from rest_framework import serializers
from .models import StudySession, ChatMessage, MessageSource, SessionFeedback

class MessageSourceSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source="material.file_name", read_only=True)
    class Meta: model = MessageSource; fields = ["page", "snippet", "material_name"]

class ChatMessageSerializer(serializers.ModelSerializer):
    sources = MessageSourceSerializer(many=True, read_only=True)
    timestamp = serializers.DateTimeField(source="created_at", read_only=True)
    class Meta: model = ChatMessage; fields = ["id", "role", "content", "sources", "timestamp"]

class StudySessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudySession
        fields = ["id", "user", "course", "title", "description",
                  "confidence_score", "created_at"]
        read_only_fields = ["user", "confidence_score"]

class FeedbackSerializer(serializers.ModelSerializer):
    class Meta: model = SessionFeedback; fields = ["session", "rating", "note"]