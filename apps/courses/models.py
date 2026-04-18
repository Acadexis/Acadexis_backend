from django.db import models
from pgvector.django import VectorField
from apps.institutions.models import TimestampedModel, Department
from apps.accounts.models import User

class Course(TimestampedModel):
    title = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField()
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="courses")
    lecturer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="courses_taught",
                                 limit_choices_to={"role": "lecturer"})
    thumbnail = models.ImageField(upload_to="courses/thumbnails/", null=True, blank=True)
    level = models.CharField(max_length=50, blank=True)
    lecturer_remark = models.TextField(blank=True)

class Enrollment(TimestampedModel):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    class Meta: unique_together = ("student", "course")

class CourseMaterial(TimestampedModel):
    class Status(models.TextChoices):
        PROCESSING = "processing"
        READY = "ready"
        FAILED = "failed"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="materials")
    file = models.FileField(upload_to="materials/")
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=20)
    file_size = models.BigIntegerField()
    page_count = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROCESSING)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

class MaterialChunk(TimestampedModel):
    """Vector chunks for RAG."""
    material = models.ForeignKey(CourseMaterial, on_delete=models.CASCADE, related_name="chunks")
    page = models.IntegerField()
    content = models.TextField()
    embedding = VectorField(dimensions=1536)  # text-embedding-3-small

class CourseRating(TimestampedModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="ratings")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    score = models.PositiveSmallIntegerField()  # 1-5
    reaction = models.CharField(max_length=10, blank=True)  # 'up' / 'down'
    class Meta: unique_together = ("course", "user")