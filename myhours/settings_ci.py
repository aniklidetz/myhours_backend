"""
Django settings for CI/CD environment
"""

from .settings import *
import os
import sys
import dj_database_url

# Override settings for CI
DEBUG = True
SECRET_KEY = os.environ.get("SECRET_KEY", "test-secret-key-for-ci")

# Database
DATABASES = {
    "default": dj_database_url.parse(
        os.environ.get("DATABASE_URL", "sqlite:///ci_test.db")
    )
}

# MongoDB (use default if not available)
MONGO_CONNECTION_STRING = os.environ.get(
    "MONGO_CONNECTION_STRING", "mongodb://localhost:27017/"
)
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "myhours_ci_test")

# Disable biometric processing in CI
ENABLE_BIOMETRIC_MOCK = True

# Disable some heavy apps for CI
INSTALLED_APPS = [app for app in INSTALLED_APPS if app not in ["celery"]]

# Disable MongoDB connections during tests
if "test" in sys.argv or "GITHUB_ACTIONS" in os.environ:
    # Override MongoDB service to avoid connection errors during Django setup
    class MockMongoService:
        def get_all_active_embeddings(self):
            return []

        def get_employee_embeddings(self, employee_id):
            return []

    # Monkey patch for CI
    import biometrics.services.mongodb_service

    biometrics.services.mongodb_service.mongodb_service = MockMongoService()

# Simpler logging for CI
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}

# Feature flags for CI
FEATURE_FLAGS = {
    "ENABLE_PROJECT_PAYROLL": True,  # Test with all features enabled
}
