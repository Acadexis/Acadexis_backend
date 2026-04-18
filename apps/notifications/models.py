from django.db import models
from apps.institutions.models import TimestampedModel
from apps.accounts.models import User

class Notification(TimestampedModel):
    class Type(models.TextChoices):
        INFO = "info"
        SUCCESS = "success"
        WARNING = "warning"
        COURSE = "course"
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=255)
    message = models.TextField()
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.INFO)
    read = models.BooleanField(default=False)