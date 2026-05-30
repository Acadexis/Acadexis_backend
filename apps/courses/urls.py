from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r"courses", views.CourseViewSet, basename="course")

urlpatterns = [
    path("", include(router.urls)),
    path("modules/", views.CourseModuleListView.as_view(), name="module-list"),
    path("modules/<uuid:pk>/", views.CourseModuleDetailView.as_view(), name="module-detail"),
    path("recommendations/", views.CourseRecommendationsView.as_view(), name="recommendations"),
    path("materials/", views.CourseMaterialListCreateView.as_view(), name="material-list"),
    path("materials/<uuid:pk>/", views.CourseMaterialDetailView.as_view(), name="material-detail"),
]
