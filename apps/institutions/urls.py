from django.urls import path
from . import views

urlpatterns = [
    path("universities/", views.UniversityListCreateView.as_view(), name="university-list"),
    path("universities/<uuid:pk>/", views.UniversityDetailView.as_view(), name="university-detail"),
    path("faculties/", views.FacultyListCreateView.as_view(), name="faculty-list"),
    path("faculties/<uuid:pk>/", views.FacultyDetailView.as_view(), name="faculty-detail"),
    path("departments/", views.DepartmentListCreateView.as_view(), name="department-list"),
    path("departments/<uuid:pk>/", views.DepartmentDetailView.as_view(), name="department-detail"),
]
