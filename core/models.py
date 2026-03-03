from django.db import models
import uuid



class AcademicLevel(models.TextChoices):
    LEVEL_100 = '100', '100 Level'
    LEVEL_200 = '200', '200 Level'
    LEVEL_300 = '300', '300 Level'
    LEVEL_400 = '400', '400 Level'
    LEVEL_500 = '500', '500 Level'
    LEVEL_600 = '600', '600 Level'
    POSTGRAD = 'PG', 'Postgraduate'

class Semester(models.TextChoices):
    FIRST = '1', 'First Semester / Harmattan'
    SECOND = '2', 'Second Semester / Rain'

    

class TimeStampedModel(models.Model):
    """
    An abstract base class model that provides self-updating
    'created_at' and 'updated_at' fields.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class University(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    abbreviation = models.CharField(max_length=20, blank=True, help_text="e.g. UNILAG")
    domain = models.CharField(max_length=100, unique=True, help_text="e.g. unilag.edu.ng")
    logo = models.ImageField(upload_to='universities/logos/', null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Universities"

    def __str__(self):
        return self.name

class Faculty(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    university = models.ForeignKey(University, on_delete=models.CASCADE, related_name='faculties')
    name = models.CharField(max_length=255)

    class Meta:
        verbose_name_plural = "Faculties"
        unique_together = ('name', 'university')

    def __str__(self):
        return f"{self.name} ({self.university.abbreviation})"

class Department(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=255)

    class Meta:
        unique_together = ('name', 'faculty')

    def __str__(self):
        return f"{self.name} ({self.faculty.name})"