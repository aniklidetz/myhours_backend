"""
Biometric views package - provides backward compatibility for all view imports.

All views are now split into separate modules by functionality:
- helpers.py - Helper functions (IP, rate limiting, logging)
- registration_views.py - Face registration
- attendance_views.py - Check-in/Check-out operations
- status_views.py - Status and statistics views
"""

import logging

# Create logger for backward compatibility
logger = logging.getLogger("biometrics.views")

from users.models import Employee

# Import models for backward compatibility with tests
from ..models import BiometricAttempt, BiometricLog, BiometricProfile, FaceQualityCheck

# Import services
from ..services.enhanced_biometric_service import (
    CriticalBiometricError,
    enhanced_biometric_service,
)

try:
    from ..services.face_processor import face_processor
except ImportError:
    face_processor = None

# Import serializers
from ..serializers import FaceRecognitionSerializer, FaceRegistrationSerializer
from ..services.mongodb_repository import mongo_biometric_repository

# Import attendance views
from .attendance_views import check_in, check_out, check_work_status

# Import helper functions
from .helpers import check_rate_limit, get_client_ip, log_biometric_attempt

# Import registration views
from .registration_views import register_face

# Import status views
from .status_views import (
    biometric_stats,
    get_biometric_status,
    test_endpoint,
    verify_face,
)

# Export all view functions for backward compatibility
__all__ = [
    # Helper functions
    "get_client_ip",
    "check_rate_limit",
    "log_biometric_attempt",
    # Registration views
    "register_face",
    # Attendance views
    "check_in",
    "check_out",
    "check_work_status",
    # Status views
    "test_endpoint",
    "biometric_stats",
    "get_biometric_status",
    "verify_face",
    # Models for test compatibility
    "BiometricAttempt",
    "BiometricLog",
    "BiometricProfile",
    "FaceQualityCheck",
    "Employee",
    # Services for test compatibility
    "enhanced_biometric_service",
    "CriticalBiometricError",
    "face_processor",
    "mongo_biometric_repository",
    # Serializers
    "FaceRecognitionSerializer",
    "FaceRegistrationSerializer",
    # Logger for tests
    "logger",
]
