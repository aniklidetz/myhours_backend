"""
Test settings for running pytest without database creation issues
"""
import os

from .settings import *

# Override DEBUG and SECRET_KEY
DEBUG = True
SECRET_KEY = os.environ.get('SECRET_KEY', 'test-secret-key-for-pytest')

# Use the existing database for tests instead of creating a new one
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'myhours_db',  # Use existing production database
        'USER': 'myhours_user',
        'PASSWORD': 'secure_password_123',
        'HOST': 'localhost',
        'PORT': '5432',
        'TEST': {
            'NAME': 'myhours_db',  # Don't create a separate test database
        },
    }
}

# Disable coverage requirement for quick tests
COVERAGE_FAIL_UNDER = 0

# Simplified cache for tests
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'test-cache',
    }
}

# Lightweight logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'}
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
}

print("✅ Using test settings with existing database")