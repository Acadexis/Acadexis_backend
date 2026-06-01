from rest_framework import serializers
from .models import StudySession, ChatMessage, MessageSource, SessionFeedback


class MessageSourceSerializer(serializers.ModelSerializer):
    material = serializers.SerializerMethodField()

    class Meta:
        model = MessageSource
        fields = ["id", "message", "material", "page", "snippet"]

    def get_material(self, obj):
        if not obj.material:
            return None
        return {
            "id": str(obj.material.id),
            "file_name": obj.material.file_name,
            "file": self._get_file_url(obj.material),
            "course": str(obj.material.course.id),
        }

    def _get_file_url(self, material):
        if not material.file:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(material.file.url) if request else material.file.url


class ChatMessageSerializer(serializers.ModelSerializer):
    sources = MessageSourceSerializer(many=True, read_only=True)
    # "timestamp" alias — the frontend mock contract references both created_at and timestamp
    timestamp = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = ChatMessage
        fields = ["id", "session", "role", "content", "sources", "created_at", "timestamp"]
        read_only_fields = fields


class StudySessionSerializer(serializers.ModelSerializer):
    user = serializers.UUIDField(source="user.id", read_only=True)
    course = serializers.UUIDField(source="course.id", read_only=True)

    class Meta:
        model = StudySession
        fields = [
            "id", "user", "course", "title", "description",
            "confidence_score", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "user", "confidence_score", "created_at", "updated_at"]


class StudySessionCreateSerializer(serializers.ModelSerializer):
    """Used for POST /api/sessions/ — writes course as FK UUID input."""
    from apps.courses.models import Course
    course = serializers.PrimaryKeyRelatedField(
        queryset=Course.objects.all()
    )

    class Meta:
        model = StudySession
        fields = ["course", "title", "description"]

    def validate_title(self, value):
        return value.strip() or "New Session"


class SessionFeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionFeedback
        fields = ["id", "session", "rating", "note", "created_at"]
        read_only_fields = ["id", "session", "created_at"]

    def validate_rating(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value