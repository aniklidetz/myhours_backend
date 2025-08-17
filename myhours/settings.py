"""
Django settings for myhours project.
"""

import logging
import os
import sys
from pathlib import Path

import dj_database_url  # pip install dj-database-url
from decouple import config  # pip install python-decouple
from pymongo import MongoClient

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY SETTINGS
SECRET_KEY = config("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable must be set")

DEBUG = config("DEBUG", default=False, cast=bool)

# Production-safe ALLOWED_HOSTS - remove * for production
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1,192.168.1.164" + (",*" if DEBUG else ""),
).split(",")

# Check if we're running tests
TESTING = "test" in sys.argv

# Security warning for weak keys
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5:
    if not TESTING:
        print("⚠️  WARNING: SECRET_KEY should be longer and more complex for production")

# ENABLE_SPECTACULAR - Safe Feature Flag (Default: False for CI/CD stability)
# drf_spectacular is DISABLED by default to prevent CI/CD crashes
ENABLE_SPECTACULAR = config("ENABLE_SPECTACULAR", default=False, cast=bool)

# Force disable for maximum CI/CD stability - only enable if explicitly developing OpenAPI docs
SPECTACULAR_AVAILABLE = False
if ENABLE_SPECTACULAR:
    try:
        import drf_spectacular  # noqa: F401

        SPECTACULAR_AVAILABLE = True
        if not TESTING:
            print("✅ drf_spectacular enabled for OpenAPI documentation")
    except ImportError:
        SPECTACULAR_AVAILABLE = False
        if not TESTING:
            print("⚠️  ENABLE_SPECTACULAR=True but drf_spectacular not installed")

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "django_filters",
    "corsheaders",  # Add: pip install django-cors-headers
    "rest_framework.authtoken",  # For authentication
    # Local apps
    "core",
    "users",
    "worktime",
    "payroll",
    "biometrics",
    "integrations",
]

# Conditionally add drf_spectacular ONLY if available
if SPECTACULAR_AVAILABLE:
    INSTALLED_APPS.append("drf_spectacular")

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # Must be first
]

# Add security middleware only if not testing
if not TESTING:
    MIDDLEWARE.append("django.middleware.security.SecurityMiddleware")

MIDDLEWARE += [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Custom API middleware
    "core.middleware.APIVersionMiddleware",
    "core.middleware.APILoggingMiddleware",
    "core.middleware.APIResponseMiddleware",
]

ROOT_URLCONF = "myhours.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "myhours.wsgi.application"

# Database settings
# Priority: DATABASE_URL > individual DB settings > SQLite fallback
DATABASE_URL = config("DATABASE_URL", default="")

if DATABASE_URL:
    # Use DATABASE_URL if provided (recommended for production)
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL)}
else:
    # Fallback to individual settings or SQLite
    db_engine = config("DB_ENGINE", default="django.db.backends.sqlite3")

    if db_engine == "django.db.backends.postgresql":
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": config("DB_NAME", default="myhours_db"),
                "USER": config("DB_USER", default="myhours_user"),
                "PASSWORD": config("DB_PASSWORD", default="secure_password_123"),
                "HOST": config("DB_HOST", default="localhost"),
                "PORT": config("DB_PORT", default="5432"),
                "OPTIONS": {
                    "connect_timeout": 60,
                },
            }
        }
    else:
        # SQLite fallback for development
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": BASE_DIR / "db.sqlite3",
            }
        }

# MongoDB settings
MONGO_CONNECTION_STRING = config(
    "MONGO_CONNECTION_STRING", default="mongodb://localhost:27017/"
)
MONGO_DB_NAME = config("MONGO_DB_NAME", default="biometrics_db")
MONGO_HOST = config("MONGO_HOST", default="localhost")
MONGO_PORT = config("MONGO_PORT", default=27017, cast=int)

# Disable HTTPS redirect for tests
if TESTING:
    SECURE_SSL_REDIRECT = False
else:
    SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=False, cast=bool)

try:
    MONGO_CLIENT = MongoClient(MONGO_CONNECTION_STRING)
    MONGO_DB = MONGO_CLIENT[MONGO_DB_NAME]
    # Test connection
    MONGO_CLIENT.admin.command("ping")
    if not TESTING:
        print("MongoDB connection established")
except Exception as e:
    if not TESTING:
        print(f"MongoDB connection failed: {e}")
    MONGO_CLIENT = None
    MONGO_DB = None

# Redis/Cache configuration will be set up below

# Session settings
# Use database sessions until Redis auth is fixed
SESSION_ENGINE = "django.contrib.sessions.backends.db"
# SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
# SESSION_CACHE_ALIAS = "default"
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_NAME = "myhours_session"
SESSION_COOKIE_AGE = 86400  # 1 day
SESSION_SERIALIZER = "django.contrib.sessions.serializers.JSONSerializer"

# Production security settings
if not DEBUG:
    # HTTPS/SSL settings
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_PRELOAD = True  # Enables browser preload submission
    SECURE_REDIRECT_EXEMPT = []
    SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)

    # Secure cookies
    SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=True, cast=bool)
    CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=True, cast=bool)
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SAMESITE = "Lax"

# Reverse proxy HTTPS header (if behind proxy/load balancer)
if not DEBUG and config("USE_X_FORWARDED_PROTO", default=True, cast=bool):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# CORS settings for React Native
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in config(
        "CORS_ALLOWED_ORIGINS",
        default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:8081",
    ).split(",")
]

# CORS settings
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]

# CSRF trusted origins for production
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in config("CSRF_TRUSTED_ORIGINS", default="", cast=str).split(",")
    if origin.strip()
]

if DEBUG:
    # In development, allow all origins for easier testing
    CORS_ALLOW_ALL_ORIGINS = True
else:
    # In production, be strict about allowed origins
    CORS_ALLOW_ALL_ORIGINS = False
    # Add additional security headers
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"

# REST Framework settings
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "users.authentication.HybridAuthentication",  # Support both old and new tokens
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "users.permissions.IsEmployeeOrAbove",  # Enhanced role-based permissions
    ],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardResultsSetPagination",
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    # Schema class will be set conditionally below
    "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
    # Enhanced throttling with device tracking
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "1000/hour",  # Increased for development/testing
        "user": "5000/hour",  # Increased per-user limit for testing
        "biometric": "200/hour",  # Increased biometric operations limit
    },
}

# Safe drf_spectacular schema class configuration
try:
    import drf_spectacular  # noqa: F401

    REST_FRAMEWORK["DEFAULT_SCHEMA_CLASS"] = "drf_spectacular.openapi.AutoSchema"
except ImportError:
    # Fallback to CoreAPI if drf_spectacular not available
    REST_FRAMEWORK["DEFAULT_SCHEMA_CLASS"] = "rest_framework.schemas.coreapi.AutoSchema"

# Enhanced Authentication Settings
AUTH_TOKEN_TTL_DAYS = 7  # Default token expiration
BIOMETRIC_SESSION_TTL_HOURS = 8  # Biometric session duration
BIOMETRIC_VERIFICATION_REQUIRED_FOR = [
    "payroll",  # Payroll operations require fresh biometric verification
    "admin_actions",  # Admin actions require biometric confirmation
    "data_export",  # Data export requires verification
    # 'time_tracking', # REMOVED time_tracking - now check-in/out without additional verification
]

# Security Settings
MAX_FAILED_AUTH_ATTEMPTS = 5
AUTH_LOCKOUT_DURATION_MINUTES = 15
REQUIRE_BIOMETRIC_FOR_SENSITIVE_OPS = True

# Biometric Control Settings
# CRITICAL: This should NEVER be True in production
ENABLE_BIOMETRIC_MOCK = config("ENABLE_BIOMETRIC_MOCK", default=False, cast=bool)
if ENABLE_BIOMETRIC_MOCK and not DEBUG:
    raise ValueError(
        "ENABLE_BIOMETRIC_MOCK must not be enabled in production (DEBUG=False)"
    )

# Test mode for bypassing quality checks in tests
BIOMETRY_TEST_MODE = TESTING or config("BIOMETRY_TEST_MODE", default=False, cast=bool)

# Log critical security warning if mock is enabled
if ENABLE_BIOMETRIC_MOCK:
    logging.getLogger(__name__).critical(
        "🚨 BIOMETRIC MOCK MODE ENABLED - NOT FOR PRODUCTION USE!"
    )

# Face Recognition Settings - Improved for better matching
FACE_RECOGNITION_TOLERANCE = config(
    "FACE_RECOGNITION_TOLERANCE", default=0.65, cast=float
)  # Increased from 0.6 to 0.65
FACE_QUALITY_THRESHOLD = config(
    "FACE_QUALITY_THRESHOLD", default=0.6, cast=float
)  # Lowered from 0.7 to 0.6
FACE_ENCODING_MODEL = config(
    "FACE_ENCODING_MODEL", default="large"
)  # Use large model for better accuracy
MIN_FACE_SIZE = (40, 40)  # Minimum face size in pixels

# Feature Flags
FEATURE_FLAGS = {
    "ENABLE_PROJECT_PAYROLL": config(
        "ENABLE_PROJECT_PAYROLL", default=False, cast=bool
    ),
}

# Redis/Cache/Session configuration moved below

# Celery configuration moved below

# DRF Spectacular settings for OpenAPI
SPECTACULAR_SETTINGS = {
    "TITLE": "MyHours API",
    "DESCRIPTION": "API for employee time tracking and payroll management with biometric authentication",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1/",
    "COMPONENT_SPLIT_REQUEST": True,
    "TAGS": [
        {
            "name": "Authentication",
            "description": "User authentication and token management",
        },
        {"name": "Users", "description": "User and employee management"},
        {"name": "Worktime", "description": "Work time tracking and logs"},
        {"name": "Payroll", "description": "Salary and payroll management"},
        {
            "name": "Biometrics",
            "description": "Biometric face recognition for check-in/out",
        },
        {
            "name": "Integrations",
            "description": "Holiday calendar and external integrations",
        },
    ],
    "SERVERS": [
        {"url": "http://localhost:8000", "description": "Development server"},
        {"url": "http://192.168.1.164:8000", "description": "Local network server"},
    ],
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": True,
        "defaultModelsExpandDepth": 2,
        "defaultModelExpandDepth": 2,
        "docExpansion": "list",
        "filter": True,
        "showExtensions": True,
        "showCommonExtensions": True,
    },
    "REDOC_UI_SETTINGS": {
        "hideDownloadButton": False,
        "expandResponses": "all",
        "pathInMiddlePanel": True,
    },
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {
            "min_length": 8,
        },
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Jerusalem"  # Israeli time zone
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files for file uploads
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Create logs directory if it doesn't exist
(BASE_DIR / "logs").mkdir(exist_ok=True)

# Optimized Logging configuration with rotation
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,

    "filters": {
        "pii_redactor": {"()": "myhours.logging_filters.PIIRedactorFilter"},
    },

    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}", "style": "{"},
        "simple":  {"format": "{levelname} {asctime} {message}", "style": "{"},
        "minimal": {"format": "{levelname} {message}", "style": "{"},
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "minimal",
            "level": "DEBUG" if DEBUG else "INFO",
            "filters": ["pii_redactor"],
        },
        "django_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "django.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 3,
            "formatter": "simple",
            "level": "INFO",
            "encoding": "utf-8",
            "filters": ["pii_redactor"],
        },
        "biometric_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "biometric.log",
            "maxBytes": 2 * 1024 * 1024,
            "backupCount": 2,
            "formatter": "simple",
            "level": "INFO",
            "encoding": "utf-8",
            "filters": ["pii_redactor"],
        },
    },

    "loggers": {
        "django":     {"handlers": ["django_file"] if not DEBUG else ["console"], "level": "INFO", "propagate": False},
        "biometrics": {"handlers": ["biometric_file"] + (["console"] if DEBUG else []), "level": "INFO", "propagate": False},
        "users":      {"handlers": ["django_file"] if not DEBUG else ["console"], "level": "INFO", "propagate": False},
        "payroll":    {"handlers": ["django_file"] if not DEBUG else ["console"], "level": "INFO", "propagate": False},
        "worktime":   {"handlers": ["django_file"] if not DEBUG else ["console"], "level": "INFO", "propagate": False},

        # optional: route gunicorn logs through filtered console
        "gunicorn.error":  {"handlers": ["console"], "level": "INFO", "propagate": False},
        "gunicorn.access": {"handlers": ["console"], "level": "INFO", "propagate": False},

        # root
        "": {"handlers": ["console"], "level": "WARNING"},
    },
}


# Testing settings
if "test" in sys.argv:
    import logging
    import warnings

    # Disable most logging during tests
    logging.disable(logging.CRITICAL)

    # Suppress Django warnings during tests
    warnings.filterwarnings(
        "ignore", category=RuntimeWarning, module="django.db.models.fields"
    )

    DEBUG = False  # Turn off DEBUG for cleaner test output

    DATABASES["default"] = {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
    # Disable external connections for tests
    MONGO_CLIENT = None
    MONGO_DB = None

    # Test cache configuration moved to unified section above

# Safe DRF Spectacular settings - only applied if available
if SPECTACULAR_AVAILABLE:

    SPECTACULAR_SETTINGS = {
        "TITLE": "MyHours API",
        "DESCRIPTION": "API for employee time tracking and payroll management with biometric authentication",
        "VERSION": "1.0.0",
        "SERVE_INCLUDE_SCHEMA": False,  # Disable schema serving to prevent startup crashes
        "SCHEMA_PATH_PREFIX": r"/api/v1/",
        "COMPONENT_SPLIT_REQUEST": True,
        "DISABLE_ERRORS_AND_WARNINGS": True,  # Critical: suppress warnings that crash CI
        "SCHEMA_PATH_PREFIX_TRIM": True,
        "SCHEMA_COERCE_PATH_PK": True,
        "PREPROCESSING_HOOKS": [],  # Empty preprocessing hooks to prevent issues
        "POSTPROCESSING_HOOKS": [],  # Empty postprocessing hooks
        "TAGS": [
            {
                "name": "Authentication",
                "description": "User authentication and token management",
            },
            {"name": "Users", "description": "User and employee management"},
            {"name": "Worktime", "description": "Work time tracking and logs"},
            {"name": "Payroll", "description": "Salary and payroll management"},
            {
                "name": "Biometrics",
                "description": "Biometric face recognition for check-in/out",
            },
            {
                "name": "Integrations",
                "description": "Holiday calendar and external integrations",
            },
        ],
        "SERVERS": [
            {"url": "http://localhost:8000", "description": "Development server"},
            {"url": "http://192.168.1.164:8000", "description": "Local network server"},
        ],
        "SWAGGER_UI_SETTINGS": {
            "deepLinking": True,
            "persistAuthorization": True,
            "displayOperationId": True,
            "defaultModelsExpandDepth": 2,
            "defaultModelExpandDepth": 2,
            "docExpansion": "list",
            "filter": True,
            "showExtensions": True,
            "showCommonExtensions": True,
        },
        "REDOC_UI_SETTINGS": {
            "hideDownloadButton": False,
            "expandResponses": "all",
            "pathInMiddlePanel": True,
        },
    }

    # Safe import of authentication schemas (only when needed and available)
    if not os.getenv("GITHUB_ACTIONS") and not TESTING:
        try:
            import users.schema  # noqa: F401
        except ImportError:
            print(
                "⚠️  Could not import users.schema - OpenAPI auth schemas not available"
            )
else:
    # Fallback settings when drf_spectacular is disabled
    SPECTACULAR_SETTINGS = {}
    if not TESTING:
        print("ℹ️  drf_spectacular disabled - using basic DRF schema")
