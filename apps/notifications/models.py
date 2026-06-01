from django.db import models
from django.conf import settings
from apps.institutions.models import TimestampedModel

class Notification(TimestampedModel):
    class Type(models.TextChoices):
        INFO = "info"
        SUCCESS = "success"
        WARNING = "warning"
        COURSE = "course"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=255)
    # Primary text field stored in DB
    body = models.TextField()
    # Backwards-compatible alias field name kept as a property
    read = models.BooleanField(default=False)
    notification_type = models.CharField(max_length=60, default=Type.INFO, choices=Type.choices)
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.notification_type}] {self.title} → {self.user.email}"

    @classmethod
    def create_and_push(cls, user, title: str, body: str, notification_type: str, data: dict = None):
        """
        Convenience: create DB record and push to the user's WebSocket group.
        """
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        notification = cls.objects.create(
            user=user,
            title=title,
            body=body,
            notification_type=notification_type,
            data=data or {},
        )

        channel_layer = get_channel_layer()
        group_name = f"notifications_{user.id}"
        payload = {
            "type": "send_notification",
            "id": str(notification.id),
            "title": notification.title,
            "body": notification.body,
            "notification_type": notification.notification_type,
            "read": notification.read,
            "created_at": notification.created_at.isoformat(),
            "data": notification.data,
        }

        try:
            async_to_sync(channel_layer.group_send)(group_name, payload)
        except Exception:
            # Best-effort push — DB record is source of truth
            pass

        return notification

    # Backwards-compatible properties for existing code that used `message`/`type`
    @property
    def message(self):
        return self.body

    @property
    def type(self):
        return self.notification_type

    @type.setter
    def type(self, value):
        self.notification_type = value

    @message.setter
    def message(self, value):
        self.body = value