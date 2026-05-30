import os
from django.conf import settings
from django.db import models
from apps.institutions.models import TimestampedModel, Department
from apps.accounts.models import User


def material_upload_path(instance, filename):
    """Store materials in a folder per course: materials/<course_id>/<filename>"""
    return f"materials/{instance.course.id}/{filename}"


class Course(TimestampedModel):
    title = models.CharField(max_length=255)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True, default="")
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        related_name="courses",
    )
    lecturer = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="taught_courses",
    )
    thumbnail = models.ImageField(upload_to="course_thumbnails/", null=True, blank=True)
    level = models.CharField(max_length=50, blank=True, default="")
    lecturer_remark = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} — {self.title}"

    @property
    def materials_count(self):
        return self.materials.filter(status="ready").count()

    @property
    def students_enrolled(self):
        return self.enrollments.count()


class Enrollment(TimestampedModel):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")

    class Meta:
        unique_together = ("student", "course")

    def __str__(self):
        return f"{self.student.email} → {self.course.code}"


class CourseMaterial(TimestampedModel):
    STATUS_CHOICES = [
        ("processing", "Processing"),
        ("ready", "Ready"),
        ("failed", "Failed"),
    ]
    FILE_TYPE_CHOICES = [
        ("pdf", "PDF"),
        ("docx", "DOCX"),
        ("pptx", "PPTX"),
    ]

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="materials",
    )
    file = models.FileField(upload_to=material_upload_path)
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES, default="pdf")
    file_size = models.BigIntegerField()
    page_count = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="processing")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_materials",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.file_name} ({self.course.code}) — {self.status}"


class MaterialChunk(TimestampedModel):
    material = models.ForeignKey(
        CourseMaterial,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    page = models.IntegerField()
    content = models.TextField()

    class Meta:
        ordering = ["material", "page"]

    def __str__(self):
        return f"Chunk p.{self.page} — {self.material.file_name}"


class CourseRating(TimestampedModel):
    REACTION_CHOICES = [("up", "Up"), ("down", "Down")]

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="ratings")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ratings")
    score = models.PositiveSmallIntegerField()
    reaction = models.CharField(max_length=10, choices=REACTION_CHOICES)

    class Meta:
        unique_together = ("course", "user")

    def __str__(self):
        return f"{self.user.email} rated {self.course.code}: {self.score}"


class CourseModule(TimestampedModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.course.code} — Module {self.order}: {self.title}"
