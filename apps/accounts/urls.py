from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView,
    LoginView,
    LogoutView,
    CurrentUserView,
    ProfileView,
    ForgotPasswordView,
    ResetPasswordView,
    ChangePasswordView,
    CSRFTokenView,
    AdminLoginView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("me/", CurrentUserView.as_view(), name="auth-me"),
    path("profile/", ProfileView.as_view(), name="auth-profile"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot-password"),
    path("reset-password/", ResetPasswordView.as_view(), name="reset-password"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("csrf/", CSRFTokenView.as_view(), name="auth-csrf"),
    path("admin-login/", AdminLoginView.as_view(), name="auth-admin-login"),
]