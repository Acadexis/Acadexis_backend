from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    # Aliases to satisfy frontend contract
    message = serializers.CharField(source="body", read_only=True)
    type = serializers.CharField(source="notification_type", read_only=True)
    user = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "user",
            "title",
            "body",
            "message",
            "notification_type",
            "type",
            "read",
            "data",
            "created_at",
        ]
        read_only_fields = fields

    def get_user(self, obj):
        return str(obj.user.id) if obj.user_id else None