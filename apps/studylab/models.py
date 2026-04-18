from django.db import models
from apps.institutions.models import TimestampedModel
from apps.accounts.models import User
from apps.courses.models import Course, CourseMaterial

class StudySession(TimestampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="sessions")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    confidence_score = models.FloatField(default=0.0)  # 0-1

class ChatMessage(TimestampedModel):
    class Role(models.TextChoices):
        USER = "user"
        ASSISTANT = "assistant"
    session = models.ForeignKey(StudySession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=Role.choices)
    content = models.TextField()

class MessageSource(models.Model):
    message = models.ForeignKey(ChatMessage, on_delete=models.CASCADE, related_name="sources")
    material = models.ForeignKey(CourseMaterial, on_delete=models.CASCADE)
    page = models.IntegerField()
    snippet = models.TextField()

class SessionFeedback(TimestampedModel):
    session = models.ForeignKey(StudySession, on_delete=models.CASCADE, related_name="feedback")
    rating = models.PositiveSmallIntegerField()  # 1-5
    note = models.TextField(blank=True)