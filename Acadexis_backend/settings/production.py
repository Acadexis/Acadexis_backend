"""
Acadexis_backend/settings/production.py
--------------------------------------
Production settings — deployed environment.

Usage:
  Set in your hosting environment:
  DJANGO_SETTINGS_MODULE=Acadexis_backend.settings.production

Required environment variables (set in your hosting dashboard):
  SECRET_KEY, DB_URL, REDIS_URL, SENDGRID_API_KEY,
  ALLOWED_HOSTS, CORS_ALLOWED_ORIGINS, FRONTEND_URL,
  DEFAULT_FROM_EMAIL, EMAIL_FROM_NAME
"""

from .base import *
import dj_database_url
from decouple import config


# ------------------------------------------------------------------
# Security
# ------------------------------------------------------------------
SECRET_KEY = config("SECRET_KEY")
DEBUG = True
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="").split(",")


# ------------------------------------------------------------------
# Database — PostgreSQL via DATABASE_URL
# ------------------------------------------------------------------
DATABASES = {
    "default": dj_database_url.config(
        default=config("DB_URL"),
        conn_max_age=600,
        ssl_require=True,
    )
}



# ------------------------------------------------------------------
# CORS
# ------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS", default=""
).split(",")



# ------------------------------------------------------------------
# Security hardening
# ------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"



# ------------------------------------------------------------------
# Email — use Resend if configured, otherwise fallback to SMTP.
# ------------------------------------------------------------------
RESEND_API_KEY = config("RESEND_API_KEY", default=None)
EMAIL_BACKEND = (
    "apps.accounts.email_backend.ResendEmailBackend"
    if RESEND_API_KEY
    else config("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
)



# ------------------------------------------------------------------
# Celery — Redis broker (Upstash, Railway Redis, etc.)
# ------------------------------------------------------------------
CELERY_BROKER_URL = config("REDIS_URL")
CELERY_RESULT_BACKEND = config("REDIS_URL")



# Channels & Celery
CHANNEL_LAYERS = {"default": {
    "BACKEND": "channels_redis.core.RedisChannelLayer",
    "CONFIG": {"hosts": [config("REDIS_URL")]},
}}


# S3 Storage
USE_S3 = config("USE_S3", default="False") == "True"
if USE_S3:
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="us-east-1")
