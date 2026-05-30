from django.contrib import admin
from .models import ContactMessage, IssueReport, AdminRequest

admin.site.register(ContactMessage)
admin.site.register(IssueReport)
admin.site.register(AdminRequest)
