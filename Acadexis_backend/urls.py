from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

from apps.studylab.views import StudySessionViewSet
from apps.analytics.views import HeatmapViewSet, BookmarkViewSet
from apps.notifications.views import NotificationViewSet
from apps.support.views import ContactView, ReportView, AdminRequestView

router = DefaultRouter()
router.register("sessions", StudySessionViewSet, basename="sessions")
router.register("heatmap", HeatmapViewSet, basename="heatmap")
router.register("bookmarks", BookmarkViewSet, basename="bookmarks")
router.register("notifications", NotificationViewSet, basename="notifications")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.institutions.urls")),
    path("api/", include("apps.courses.urls")),
    path("api/", include(router.urls)),
    path("api/support/contact/", ContactView.as_view()),
    path("api/support/report/", ReportView.as_view()),
    path("api/support/admin-request/", AdminRequestView.as_view()),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/swagger/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/docs/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc-ui"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
