"""
Django settings for CI/CD environment (clean version without emojis)
"""

import os
import sys
from urllib.parse import unquote, urlparse

# ========= CI flags & environment variables =========
GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS", "").lower() == "true"
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    # default for docker-compose: the DB service is named 'postgres'
    "postgresql://postgres:postgres@postgres:5432/myhours_db",
)

# Decide target DB name (can be overridden via CI_DB_NAME)
if "myhours_perf" in DATABASE_URL:
    CI_DB_NAME = "myhours_perf"
elif "myhours_migration" in DATABASE_URL:
    CI_DB_NAME = "myhours_migration"
else:
    CI_DB_NAME = os.getenv("CI_DB_NAME", "myhours_test")

# ========= Parse DATABASE_URL =========
u = urlparse(DATABASE_URL)
if u.scheme not in ("postgresql", "postgres"):
    raise RuntimeError(
        f"Invalid DATABASE_URL scheme: {u.scheme!r}. Expected 'postgresql' or 'postgres'."
    )

DB_CONFIG_FROM_URL = {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": CI_DB_NAME,  # force CI DB name
    "USER": unquote(u.username or ""),
    "PASSWORD": unquote(u.password or ""),
    "HOST": u.hostname or "localhost",  # will be 'postgres' if defined in URL
    "PORT": str(u.port or 5432),
}

# ========= Make DATABASES available BEFORE importing base settings =========
DATABASES = {"default": DB_CONFIG_FROM_URL}

# ========= Import base settings =========
from .settings import *  # noqa

# ========= Apply CI-specific overrides on top of base settings =========
DEBUG = True
SECRET_KEY = os.environ.get("SECRET_KEY", "test-secret-key-for-ci")

# Keep Celery and drf-spectacular out of CI test runs (lighter/faster + prevent schema generation crashes)
INSTALLED_APPS = [
    app for app in INSTALLED_APPS if app not in ("celery", "drf_spectacular")
]

# DRF and basic test adjustments
APPEND_SLASH = False
SECURE_SSL_REDIRECT = False

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.TokenAuthentication",
        "users.authentication.DeviceTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 5,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ],
}

# Cache/sessions — no Redis in CI
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "ci-tests",
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.cache"

# MongoDB — safe defaults
MONGO_CONNECTION_STRING = os.getenv(
    "MONGO_CONNECTION_STRING", "mongodb://localhost:27017/"
)
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "myhours_ci_test")
ENABLE_BIOMETRIC_MOCK = os.getenv("ENABLE_BIOMETRIC_MOCK", "False").lower() == "true"

# Lightweight Mongo mock during tests/CI
if "test" in sys.argv or GITHUB_ACTIONS:

    class _MockMongoService:
        def get_all_active_embeddings(self):
            return []

        def get_employee_embeddings(self, employee_id):
            return []

    import biometrics.services.mongodb_service

    biometrics.services.mongodb_service.mongodb_service = _MockMongoService()

# Feature flags
FEATURE_FLAGS = {
    "ENABLE_PROJECT_PAYROLL": True,
}

# Simplified logging for CI
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}

# ========= Sanity checks =========
_engine = DATABASES["default"]["ENGINE"]
_host = DATABASES["default"]["HOST"]
_name = DATABASES["default"]["NAME"]
if _engine != "django.db.backends.postgresql":
    raise RuntimeError(f"Unexpected DB engine in CI: {_engine}")
if GITHUB_ACTIONS and not _host:
    raise RuntimeError("Empty DB HOST in CI.")
