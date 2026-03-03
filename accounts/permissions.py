from rest_framework import permissions

class IsLecturer(permissions.BasePermission):
    """Allows access only to users with the Lecturer role."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'lecturer')

class IsStudent(permissions.BasePermission):
    """Allows access only to users with the Student role."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'student')