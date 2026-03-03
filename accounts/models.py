from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from core.models import TimeStampedModel, Department, University, AcademicLevel

class AccountManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        return self.create_user(email, password, **extra_fields)

class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        LECTURER = 'lecturer', 'Lecturer'
        STUDENT = 'student', 'Student'

    username = None  # Remove username field
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)
    university = models.ForeignKey(University, on_delete=models.SET_NULL, null=True, related_name='users')

    objects = AccountManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email

class Profile(TimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    bio = models.TextField(blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, related_name='profiles')
    
    # Role-specific fields
    identification_number = models.CharField(max_length=50, help_text="Matric Number or Staff ID")
    level = models.CharField(
        max_length=10, 
        choices=AcademicLevel.choices, 
        null=True, 
        blank=True, 
        help_text="For Students only"
    )
    avatar = models.ImageField(upload_to='profiles/avatars/', null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.user.email})"


class AdminRequest(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='admin_requests')
    reason = models.TextField(help_text="Why do you need admin access?")
    document_proof = models.FileField(upload_to='admin_requests/proofs/', null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_requests'
    )
    admin_notes = models.TextField(blank=True, help_text="Notes from the Super Admin")

    def __str__(self):
        return f"Request from {self.user.email} - {self.status}"