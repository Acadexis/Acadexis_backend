from django.urls import path
from . import views

urlpatterns = [
    path("heatmap/", views.HeatmapListView.as_view(), name="heatmap-list"),
]
