from django.db import models
from apps.institutions.models import TimestampedModel
from apps.accounts.models import User
from apps.courses.models import Course, CourseMaterial
from apps.studylab.models import ChatMessage

class TopicStruggle(TimestampedModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="struggles")
    topic = models.CharField(max_length=255)
    questions_asked = models.IntegerField(default=0)
    avg_confidence = models.FloatField(default=0.0)
    struggling_students = models.IntegerField(default=0)

class Bookmark(TimestampedModel):
    class Kind(models.TextChoices):
        SNIPPET = "snippet"
        ANSWER = "answer"
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bookmarks")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    title = models.CharField(max_length=255)
    content = models.TextField()
    material = models.ForeignKey(CourseMaterial, on_delete=models.SET_NULL, null=True, blank=True)
    page = models.IntegerField(null=True, blank=True)
    message = models.ForeignKey(ChatMessage, on_delete=models.SET_NULL, null=True, blank=True)