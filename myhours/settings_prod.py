"""
Production Django settings for myhours project.
Secure configuration for HTTPS deployment.
"""

import os

from .settings import *  # noqa

# SECURITY SETTINGS FOR PRODUCTION

# CRITICAL: Use environment variable for secret key
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

# Force production mode
DEBUG = False

# Production hosts - update with your actual domain(s)
ALLOWED_HOSTS = [
    "yourdomain.com",
    "www.yourdomain.com",
    # Add your actual production domains
]

# SSL/HTTPS SECURITY SETTINGS
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000  # 1 year (required for preload)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True  # Enables submission to browser preload lists

# If behind a proxy/load balancer (nginx, AWS ALB, etc.)
# SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Enhanced security headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

# Secure cookies (HTTPS only)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# Additional cookie security
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# Production logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "json": {
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "/var/log/django/myhours.log",  # Adjust path as needed
            "maxBytes": 1024 * 1024 * 15,  # 15MB
            "backupCount": 10,
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": True,
        },
        "myhours": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "": {  # Root logger
            "handlers": ["console", "file"],
            "level": "WARNING",
        },
    },
}

# Database - use production DATABASE_URL
# Example: DATABASE_URL=postgresql://user:pass@host:5432/dbname
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required in production")

# Static files for production (use with collectstatic)
STATIC_ROOT = "/var/www/static/"  # Adjust path as needed
MEDIA_ROOT = "/var/www/media/"  # Adjust path as needed

# Redis cache for production
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# Email backend for production
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD")

# Disable debug features
ENABLE_BIOMETRIC_MOCK = False  # Never enable in production

# Production-specific feature flags
FEATURE_FLAGS.update(
    {
        "ENABLE_PROJECT_PAYROLL": True,  # Enable all features in production
    }
)

print("🚀 Production settings loaded - HTTPS enforced with HSTS preload")
