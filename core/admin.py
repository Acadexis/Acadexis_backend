from django.contrib import admin
from .models import University, Faculty, Department

@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display = ('name', 'abbreviation', 'domain', 'is_active', 'created_at')
    search_fields = ('name', 'abbreviation', 'domain')
    list_filter = ('is_active',)

@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ('name', 'university', 'created_at')
    search_fields = ('name',)
    list_filter = ('university',)

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'faculty', 'created_at')
    search_fields = ('name',)
    list_filter = ('faculty__university', 'faculty')