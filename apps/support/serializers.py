from rest_framework import serializers
from .models import ContactMessage, IssueReport, AdminRequest

class ContactSerializer(serializers.ModelSerializer):
    class Meta: model = ContactMessage; fields = ["subject", "body", "email"]

class ReportSerializer(serializers.ModelSerializer):
    class Meta: model = IssueReport; fields = ["title", "description", "severity"]

class AdminRequestSerializer(serializers.ModelSerializer):
    class Meta: model = AdminRequest; fields = ["reason", "document_proof", "status"]
    read_only_fields = ["status"]