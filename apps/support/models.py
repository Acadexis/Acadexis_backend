from django.db import models
from apps.institutions.models import TimestampedModel
from apps.accounts.models import User

class ContactMessage(TimestampedModel):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    email = models.EmailField()

class IssueReport(TimestampedModel):
    class Severity(models.TextChoices):
        LOW = "low"; MEDIUM = "medium"; HIGH = "high"; CRITICAL = "critical"
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    title = models.CharField(max_length=255)
    description = models.TextField()
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.MEDIUM)
    resolved = models.BooleanField(default=False)

class AdminRequest(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending"; APPROVED = "approved"; REJECTED = "rejected"
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="admin_requests")
    reason = models.TextField()
    document_proof = models.FileField(upload_to="admin_proofs/", null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)