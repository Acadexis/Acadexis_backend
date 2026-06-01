import uuid

from django.db import models
from django.db.models import Avg
from django.conf import settings

from apps.institutions.models import TimestampedModel


class TopicStruggle(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.CASCADE,
        related_name="struggles",
    )
    topic = models.CharField(max_length=255)
    questions_asked = models.IntegerField(default=0)
    avg_confidence = models.FloatField(default=0.0)
    struggling_students = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("course", "topic")
        ordering = ["-questions_asked"]

    def __str__(self):
        return f"{self.topic} ({self.course.code}) — {self.questions_asked} questions"

    @classmethod
    def recalculate_for_topic(cls, course, topic: str):
        from apps.studylab.models import StudySession, ChatMessage

        sessions = StudySession.objects.filter(course=course, title__iexact=topic)

        if not sessions.exists():
            return

        questions_asked = ChatMessage.objects.filter(
            session__in=sessions,
            role="user",
        ).count()

        agg = sessions.aggregate(avg_conf=Avg("confidence_score"))
        avg_confidence = round(agg["avg_conf"] or 0.0, 4)

        struggling_students = sessions.filter(
            confidence_score__lt=0.5
        ).values("user").distinct().count()

        cls.objects.update_or_create(
            course=course,
            topic=topic,
            defaults={
                "questions_asked": questions_asked,
                "avg_confidence": avg_confidence,
                "struggling_students": struggling_students,
            },
        )


class Bookmark(TimestampedModel):
    class Kind(models.TextChoices):
        SNIPPET = "snippet"
        ANSWER = "answer"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookmarks")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    title = models.CharField(max_length=255)
    content = models.TextField()
    material = models.ForeignKey(
        "courses.CourseMaterial",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    page = models.IntegerField(null=True, blank=True)
    message = models.ForeignKey(
        "studylab.ChatMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )