"""
Helper functions for biometric views.

This module contains utility functions used across multiple biometric views:
- IP address extraction
- Rate limiting
- Biometric attempt logging
"""

import logging

from ..models import BiometricAttempt, BiometricLog

logger = logging.getLogger("biometrics.views")


def get_client_ip(request):
    """Extract client IP from request"""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def check_rate_limit(request):
    """Check if IP is rate limited"""
    ip_address = get_client_ip(request)

    try:
        attempt = BiometricAttempt.objects.get(ip_address=ip_address)
        if attempt.is_blocked():
            return False, "Too many failed attempts. Please try again later."
        return True, None
    except BiometricAttempt.DoesNotExist:
        return True, None


def log_biometric_attempt(
    request,
    action,
    employee=None,
    success=False,
    confidence_score=None,
    error_message=None,
    processing_time=None,
):
    """Log biometric attempt"""
    try:
        log = BiometricLog.objects.create(
            employee=employee,
            action=action,
            confidence_score=confidence_score,
            location=request.data.get("location", ""),
            device_info=request.data.get("device_info", {}),
            ip_address=get_client_ip(request),
            success=success,
            error_message=error_message or "",
            processing_time_ms=processing_time,
        )
        return log
    except Exception:
        logger.exception("Failed to log biometric attempt")
        return None
