from django.db import models
import uuid

class TimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class University(TimestampedModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    logo = models.ImageField(upload_to="university_logos/", null=True, blank=True)
    code = models.CharField(max_length=20, unique=True, null=True, blank=True)

    class Meta:
        verbose_name_plural = "universities"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Faculty(TimestampedModel):
    name = models.CharField(max_length=255)
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name="faculties")

    class Meta:
        verbose_name_plural = "faculties"
        ordering = ["name"]
        unique_together = ("name", "university")

    def __str__(self):
        return f"{self.name} — {self.university.name}"


class Department(TimestampedModel):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, blank=True, default="")
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name="departments")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.faculty.university.name})"
