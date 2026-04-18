from django.db import models
import uuid

class TimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

class University(TimestampedModel):
    name = models.CharField(max_length=255, unique=True)
    def __str__(self): return self.name

class Faculty(TimestampedModel):
    name = models.CharField(max_length=255)
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name="faculties")
    class Meta: unique_together = ("name", "university")

class Department(TimestampedModel):
    name = models.CharField(max_length=255)
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name="departments")
    class Meta: unique_together = ("name", "faculty")