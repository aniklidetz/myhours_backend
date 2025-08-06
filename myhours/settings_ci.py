"""
Django settings for CI/CD environment
"""

import os
import sys

# Import everything from base settings first
from .settings import *

# Override for CI - don't use dj_database_url to avoid parsing issues

# Override settings for CI
DEBUG = True
SECRET_KEY = os.environ.get("SECRET_KEY", "test-secret-key-for-ci")

# Clear any existing DATABASE configuration from base settings
# This prevents the base settings DATABASE_URL logic from interfering
DATABASES = {}

# Temporarily clear DATABASE_URL to prevent base settings from using it
original_database_url = os.environ.get("DATABASE_URL", "")
if "DATABASE_URL" in os.environ:
    del os.environ["DATABASE_URL"]

# Database configuration will be set at the end of this file

# MongoDB (use default if not available)
MONGO_CONNECTION_STRING = os.environ.get(
    "MONGO_CONNECTION_STRING", "mongodb://localhost:27017/"
)
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "myhours_ci_test")

# Disable biometric processing in CI
ENABLE_BIOMETRIC_MOCK = True

# Disable some heavy apps for CI
INSTALLED_APPS = [app for app in INSTALLED_APPS if app not in ["celery"]]

print(f"🔍 CI DEBUG: INSTALLED_APPS = {INSTALLED_APPS}")

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

# CRITICAL: Force database configuration at the end to override any imports
# Use the original DATABASE_URL value that was captured before deletion
DATABASE_URL_CI = original_database_url or "sqlite:///ci_test.db"

print(f"🔍 CI DEBUG: Original DATABASE_URL = {original_database_url}")
print(f"🔍 CI DEBUG: Final DATABASE_URL_CI = {DATABASE_URL_CI}")
print(f"🔍 CI DEBUG: Current DATABASES before override = {DATABASES}")

# FORCE PostgreSQL configuration regardless of URL parsing issues
# This ensures we never fall back to dummy backend in CI
if os.environ.get("GITHUB_ACTIONS") == "true":
    # We're in GitHub Actions - force PostgreSQL
    if "myhours_test" in str(DATABASE_URL_CI):
        db_name = "myhours_test"
    elif "myhours_perf" in str(DATABASE_URL_CI):  
        db_name = "myhours_perf"
    elif "myhours_migration" in str(DATABASE_URL_CI):
        db_name = "myhours_migration"
    else:
        db_name = "myhours_test"  # default fallback
    
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": db_name,
            "USER": "postgres",
            "PASSWORD": "postgres",
            "HOST": "localhost",
            "PORT": "5432",
        }
    }
    print(f"✅ CI: FORCED PostgreSQL database: {db_name}")
elif "postgresql://" in DATABASE_URL_CI or "postgres://" in DATABASE_URL_CI:
    # Local development with PostgreSQL URL
    if "myhours_test" in DATABASE_URL_CI:
        db_name = "myhours_test"
    elif "myhours_perf" in DATABASE_URL_CI:
        db_name = "myhours_perf"
    elif "myhours_migration" in DATABASE_URL_CI:
        db_name = "myhours_migration"
    else:
        db_name = "myhours_test"

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": db_name,
            "USER": "postgres",
            "PASSWORD": "postgres",
            "HOST": "localhost",
            "PORT": "5432",
        }
    }
    print(f"✅ CI: Using PostgreSQL database: {db_name}")
else:
    # Local development fallback
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
    print("✅ CI: Using SQLite in-memory database")

print(f"🔍 CI DEBUG: Final DATABASES configuration = {DATABASES}")
print(f"🔍 CI DEBUG: Final ENGINE = {DATABASES['default'].get('ENGINE', 'NOT_SET')}")

# Final validation - ensure ENGINE is NEVER dummy
if DATABASES['default'].get('ENGINE') == 'django.db.backends.dummy':
    print("❌ CI ERROR: Django is using dummy backend! Forcing PostgreSQL...")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "myhours_test",
            "USER": "postgres", 
            "PASSWORD": "postgres",
            "HOST": "localhost",
            "PORT": "5432",
        }
    }
    print("🔧 CI FIX: Forced PostgreSQL configuration to prevent dummy backend")

# Final check
final_engine = DATABASES['default'].get('ENGINE', 'NOT_SET')
print(f"🎯 CI FINAL: Using database engine: {final_engine}")
if final_engine != 'django.db.backends.postgresql':
    print(f"⚠️ CI WARNING: Expected PostgreSQL but got {final_engine}")
else:
    print("✅ CI SUCCESS: PostgreSQL engine confirmed")
