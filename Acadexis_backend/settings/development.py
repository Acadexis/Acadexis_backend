from .base import *
import dj_database_url

DEBUG = True

DATABASES = {"default": dj_database_url.parse(config("DATABASE_URL"))}

# Channels & Celery
CHANNEL_LAYERS = {"default": {
    "BACKEND": "channels_redis.core.RedisChannelLayer",
    "CONFIG": {"hosts": [config("REDIS_URL")]},
}}
CELERY_BROKER_URL = config("REDIS_URL")
CELERY_RESULT_BACKEND = config("REDIS_URL")

# Local Storage
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
