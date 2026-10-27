from .base import *  # noqa: F401,F403
from .base import BASE_DIR, env

DEBUG = False
SECRET_KEY = "test-secret-key"
DATABASES = {"default": env.db("TEST_DATABASE_URL", default="sqlite://:memory:")}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_BROKER_URL = "memory://"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
AI_PROVIDER = "local"
AI_API_KEY = ""
AI_MODELS_DIR = BASE_DIR / "data" / "ai" / "models"
AXES_ENABLED = True
LOGGING = {"version": 1, "disable_existing_loggers": False, "root": {"level": "WARNING"}}
