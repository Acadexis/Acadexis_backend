"""
Administration API URL routing.
Exposes all admin endpoints under /api/admin/ namespace.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .viewsets import (
    UserAdminViewSet,
    UniversityAdminViewSet,
    FacultyAdminViewSet,
    DepartmentAdminViewSet,
    CourseAdminViewSet,
    EnrollmentAdminViewSet,
    CourseMaterialAdminViewSet,
    CourseRatingAdminViewSet,
    StudySessionAdminViewSet,
)

router = DefaultRouter()
router.register(r"users", UserAdminViewSet, basename="admin-users")
router.register(r"universities", UniversityAdminViewSet, basename="admin-universities")
router.register(r"faculties", FacultyAdminViewSet, basename="admin-faculties")
router.register(r"departments", DepartmentAdminViewSet, basename="admin-departments")
router.register(r"courses", CourseAdminViewSet, basename="admin-courses")
router.register(r"enrollments", EnrollmentAdminViewSet, basename="admin-enrollments")
router.register(
    r"materials", CourseMaterialAdminViewSet, basename="admin-materials"
)
router.register(r"ratings", CourseRatingAdminViewSet, basename="admin-ratings")
router.register(
    r"study-sessions", StudySessionAdminViewSet, basename="admin-study-sessions"
)

app_name = "administration"

urlpatterns = [
    path("", include(router.urls)),
]
