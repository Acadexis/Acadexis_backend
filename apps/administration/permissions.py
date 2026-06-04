"""
Administration API Permissions
- IsStaffUser: requires is_staff=True and authenticated
- IsAdmin: requires is_staff=True and role='admin'
"""

from rest_framework import permissions


class IsStaffUser(permissions.BasePermission):
    """
    Allow access only to authenticated staff users (is_staff=True).
    """

    message = "Only staff users can access this resource."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class IsAdminUser(permissions.BasePermission):
    """
    Allow access only to authenticated admin users (is_superuser=True).
    """

    message = "Only admin users can access this resource."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class IsStaffOrAdmin(permissions.BasePermission):
    """
    Allow access to staff OR admin users.
    """

    message = "Only staff or admin users can access this resource."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or request.user.is_superuser)
        )
