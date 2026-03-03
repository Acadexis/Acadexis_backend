from django.contrib import admin
from .models import AdminRequest, User

@admin.register(AdminRequest)
class AdminRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'created_at', 'get_university')
    list_filter = ('status', 'user__university')
    search_fields = ('user__email', 'reason')
    readonly_fields = ('user', 'reason', 'document_proof', 'created_at')
    
    # Custom Action to Approve Requests
    actions = ['approve_elevation']

    @admin.display(description='University')
    def get_university(self, obj):
        return obj.user.university

    @admin.action(description="Approve selected staff elevation to Admin")
    def approve_elevation(self, request, queryset):
        # Only process pending requests
        pending_requests = queryset.filter(status='pending')
        count = 0
        
        for admin_req in pending_requests:
            # 1. Update the actual User role
            user = admin_req.user
            user.role = User.Role.ADMIN
            user.save()
            
            # 2. Mark the request as Approved
            admin_req.status = 'approved'
            admin_req.save()
            count += 1
            
        self.message_user(request, f"Successfully promoted {count} staff to Admin.")