"""
Acadexis_backend/settings/development.py
---------------------------------------
Local development settings.

Usage:
  export DJANGO_SETTINGS_MODULE=Acadexis_backend.settings.development
  python manage.py runserver

Or set in .env:
  DJANGO_SETTINGS_MODULE=Acadexis_backend.settings.development
"""



from .base import *
from decouple import config
import dj_database_url


# ------------------------------------------------------------------
# Security
# ------------------------------------------------------------------
SECRET_KEY = config("SECRET_KEY", default="dev-insecure-secret-key-change-in-prod")
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]



# ------------------------------------------------------------------
# Database — SQLite for local dev (zero setup)
# ------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}


# Uncomment to use local PostgreSQL instead:
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.postgresql",
#         "NAME": config("DB_NAME", default="acadexis_db"),
#         "USER": config("DB_USER", default="acadexis_user"),
#         "PASSWORD": config("DB_PASSWORD", default=""),
#         "HOST": config("DB_HOST", default="localhost"),
#         "PORT": config("DB_PORT", default="5432"),
#     }
# }


# ------------------------------------------------------------------
# CORS — allow local Next.js dev server
# ------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


# ------------------------------------------------------------------
# Email — print to console in development (no SendGrid needed)
# ------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"



# ------------------------------------------------------------------
# Channels & Celery
# ------------------------------------------------------------------
CHANNEL_LAYERS = {"default": {
    "BACKEND": "channels_redis.core.RedisChannelLayer",
    "CONFIG": {"hosts": [config("REDIS_URL")]},
}}
CELERY_BROKER_URL = config("REDIS_URL")
CELERY_RESULT_BACKEND = config("REDIS_URL")


# ------------------------------------------------------------------
# Local Storage
# ------------------------------------------------------------------
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
