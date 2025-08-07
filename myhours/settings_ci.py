"""
Django settings for CI/CD environment
"""

import os
import sys

print("🚀 CI SETTINGS: Starting configuration...")

# CRITICAL: Configure DATABASE before importing base settings
# This prevents base settings from using broken dj_database_url parsing

# Get DATABASE_URL before any imports
database_url = os.environ.get("DATABASE_URL", "")
github_actions = os.environ.get("GITHUB_ACTIONS", "")

print("=" * 60)
print("🔍 CI PRE-IMPORT DEBUG:")
print(f"  GITHUB_ACTIONS = {github_actions!r}")
print(f"  DATABASE_URL = {database_url!r}")
print(f"  DJANGO_SETTINGS_MODULE = {os.environ.get('DJANGO_SETTINGS_MODULE')!r}")
print("=" * 60)

# FORCE PostgreSQL configuration BEFORE importing base settings
if github_actions == "true" or database_url:
    # Determine database name from URL
    if "myhours_test" in database_url:
        db_name = "myhours_test"
    elif "myhours_perf" in database_url:
        db_name = "myhours_perf"
    elif "myhours_migration" in database_url:
        db_name = "myhours_migration"
    else:
        db_name = "myhours_test"  # default fallback

    # Set PostgreSQL configuration BEFORE base settings import
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
    print(f"✅ CI PRE-IMPORT: Set PostgreSQL with DB name: {db_name}")
    print(f"✅ CI PRE-IMPORT: ENGINE = {DATABASES['default']['ENGINE']}")
else:
    # Local development fallback
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
    print("✅ CI PRE-IMPORT: Set SQLite fallback")

# Now import base settings - they WON'T override our DATABASES
print("🔄 CI: Importing base settings...")
from .settings import *

print("✅ CI: Base settings imported")

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

# Extended environment debugging as suggested in analysis
print("=" * 50)
print("🔍 CI ENV CHECK: GITHUB_ACTIONS =", os.environ.get("GITHUB_ACTIONS"))
print("🔍 CI ENV CHECK: DATABASE_URL =", os.environ.get("DATABASE_URL"))
print(
    "🔍 CI ENV CHECK: DJANGO_SETTINGS_MODULE =",
    os.environ.get("DJANGO_SETTINGS_MODULE"),
)
print("🔍 CI DEBUG: Original DATABASE_URL = {!r}".format(original_database_url))
print("🔍 CI DEBUG: Final DATABASE_URL_CI = {!r}".format(DATABASE_URL_CI))
print("🔍 CI DEBUG: Current DATABASES before override = {!r}".format(DATABASES))
print("=" * 50)

# FORCE PostgreSQL configuration regardless of URL parsing issues
# This ensures we never fall back to dummy backend in CI
github_actions = os.environ.get("GITHUB_ACTIONS")
print(
    f"🔍 CI DEBUG: GITHUB_ACTIONS check: {github_actions!r} == 'true'? {github_actions == 'true'}"
)

if github_actions == "true":
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
current_engine = DATABASES.get("default", {}).get("ENGINE", "NOT_SET")
print(f"🔍 CI DEBUG: Current ENGINE before validation: {current_engine!r}")

if (
    current_engine == "django.db.backends.dummy"
    or current_engine == "NOT_SET"
    or not current_engine
):
    print(
        "❌ CI ERROR: Django is using dummy backend or ENGINE not set! Forcing PostgreSQL..."
    )

    # Determine database name from environment or use sensible default
    env_db_url = os.environ.get("DATABASE_URL", "")
    if "myhours_test" in env_db_url:
        fallback_db_name = "myhours_test"
    elif "myhours_perf" in env_db_url:
        fallback_db_name = "myhours_perf"
    elif "myhours_migration" in env_db_url:
        fallback_db_name = "myhours_migration"
    else:
        fallback_db_name = "myhours_test"  # ultimate fallback

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": fallback_db_name,
            "USER": "postgres",
            "PASSWORD": "postgres",
            "HOST": "localhost",
            "PORT": "5432",
        }
    }
    print(
        f"🔧 CI FIX: Forced PostgreSQL configuration with DB name: {fallback_db_name}"
    )

# Final check with comprehensive validation
final_engine = DATABASES.get("default", {}).get("ENGINE", "NOT_SET")
final_db_name = DATABASES.get("default", {}).get("NAME", "NOT_SET")
print(f"🎯 CI FINAL: Using database engine: {final_engine}")
print(f"🎯 CI FINAL: Using database name: {final_db_name}")

# Ensure we have a proper PostgreSQL config in CI
if os.environ.get("GITHUB_ACTIONS") == "true":
    if final_engine != "django.db.backends.postgresql":
        print(f"🚨 CI CRITICAL ERROR: Expected PostgreSQL in CI but got {final_engine}")
        raise Exception(
            f"CI database configuration failed - got {final_engine} instead of PostgreSQL"
        )
    else:
        print("✅ CI SUCCESS: PostgreSQL engine confirmed for GitHub Actions")
else:
    print(f"ℹ️ CI INFO: Local development mode - using {final_engine}")
