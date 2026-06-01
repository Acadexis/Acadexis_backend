from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.institutions.models import TimestampedModel
from apps.courses.models import Course, CourseMaterial


class StudySession(TimestampedModel):
    """A study session belongs to a user and a course."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="study_sessions",
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    title = models.CharField(max_length=255, default="New Session")
    description = models.TextField(blank=True, default="")
    confidence_score = models.FloatField(default=0.0)  # 0.0 – 1.0

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} — {self.title} ({self.course.code})"


class ChatMessage(TimestampedModel):
    """A chat message within a study session."""
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    session = models.ForeignKey(
        StudySession,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.role}] {self.content[:60]}"


class MessageSource(TimestampedModel):
    """
    A citation linking an assistant ChatMessage to a specific page
    in a CourseMaterial. Populated by the RAG pipeline.
    """
    message = models.ForeignKey(
        ChatMessage,
        on_delete=models.CASCADE,
        related_name="sources",
    )
    material = models.ForeignKey(
        CourseMaterial,
        on_delete=models.SET_NULL,
        null=True,
        related_name="cited_in",
    )
    page = models.IntegerField()
    snippet = models.TextField()  # First ~240 characters of the relevant chunk

    class Meta:
        ordering = ["page"]

    def __str__(self):
        return f"Source p.{self.page} — {self.material.file_name if self.material else 'deleted'}"


class SessionFeedback(TimestampedModel):
    """Feedback for a study session (rating 1-5)."""
    session = models.OneToOneField(
        StudySession,
        on_delete=models.CASCADE,
        related_name="feedback",
    )
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    note = models.TextField(blank=True, default="")

    def __str__(self):
        return f"Feedback {self.rating}/5 for {self.session.title}"