"""
Utilities for safe logging with automatic PII data masking
"""

import hashlib
import logging
import re
from typing import Any, Dict, Optional, Union


def mask_email(email: str) -> str:
    """
    Masks email address for safe logging

    Args:
        email: Email address to mask

    Returns:
        Masked email (e.g., a***@example.com)
    """
    if not email or "@" not in email:
        return "[invalid_email]"

    username, domain = email.split("@", 1)
    if len(username) <= 1:
        return f"*@{domain}"

    return f"{username[0]}***@{domain}"


def mask_phone(phone: str) -> str:
    """
    Masks phone number for safe logging

    Args:
        phone: Phone number to mask

    Returns:
        Masked phone number (e.g., ***4567)
    """
    if not phone:
        return "[no_phone]"

    # Remove all non-digit characters
    digits = re.sub(r"\D", "", phone)

    if len(digits) < 4:
        return "***"

    return f"***{digits[-4:]}"


def mask_coordinates(lat: float, lng: float) -> str:
    """
    Masks GPS coordinates for safe logging

    Args:
        lat: Latitude
        lng: Longitude

    Returns:
        Generalized location
    """
    # Simple zone detection by coordinates
    if 32.0 <= lat <= 32.1 and 34.7 <= lng <= 34.9:
        return "Office Area"
    elif 31.5 <= lat <= 33.0 and 34.0 <= lng <= 35.5:
        return "City Area"
    else:
        return "Remote Location"


def mask_name(full_name: str) -> str:
    """
    Masks full name for safe logging

    Args:
        full_name: Full name to mask

    Returns:
        Initials (e.g., M.P.)
    """
    if not full_name or not full_name.strip():
        return "[no_name]"

    parts = full_name.strip().split()
    if len(parts) == 1:
        return f"{parts[0][0]}."
    elif len(parts) >= 2:
        return f"{parts[0][0]}.{parts[1][0]}."

    return "[no_name]"


def hash_user_id(user_id: Union[int, str], salt: str = "myhours_2025") -> str:
    """
    Creates hash from user ID for safe logging

    Args:
        user_id: User ID
        salt: Salt for hashing

    Returns:
        Hashed ID (first 8 characters)
    """
    if not user_id:
        return "[no_id]"

    hash_input = f"{salt}:{user_id}"
    hash_obj = hashlib.sha256(hash_input.encode())
    return f"usr_{hash_obj.hexdigest()[:8]}"


def safe_log_user(user, action: str = "action") -> Dict[str, Any]:
    """
    Creates safe object for logging user data

    Args:
        user: User object (Django User model)
        action: Action description

    Returns:
        Dictionary with safe data for logging
    """
    if not user:
        return {"action": action, "user": "anonymous"}

    safe_data = {
        "action": action,
        "user_hash": hash_user_id(user.id),
        "role": getattr(user, "role", "unknown"),
        "is_superuser": getattr(user, "is_superuser", False),
    }

    # Mask email if present
    if hasattr(user, "email") and user.email:
        safe_data["email_masked"] = mask_email(user.email)

    return safe_data


def safe_log_employee(employee, action: str = "action") -> Dict[str, Any]:
    """
    Creates safe object for logging employee data

    Args:
        employee: Employee object (Employee model)
        action: Action description

    Returns:
        Dictionary with safe data for logging
    """
    if not employee:
        return {"action": action, "employee": "none"}

    safe_data = {
        "action": action,
        "employee_hash": hash_user_id(employee.id),
        "role": getattr(employee, "role", "unknown"),
        "employment_type": getattr(employee, "employment_type", "unknown"),
    }

    # Mask personal data
    if hasattr(employee, "email") and employee.email:
        safe_data["email_masked"] = mask_email(employee.email)

    if hasattr(employee, "first_name") and hasattr(employee, "last_name"):
        full_name = f"{employee.first_name or ''} {employee.last_name or ''}".strip()
        if full_name:
            safe_data["name_initials"] = mask_name(full_name)

    if hasattr(employee, "phone") and employee.phone:
        safe_data["phone_masked"] = mask_phone(employee.phone)

    return safe_data


def safe_log_location(lat: Optional[float], lng: Optional[float]) -> str:
    """
    Creates safe location representation for logging

    Args:
        lat: Latitude
        lng: Longitude

    Returns:
        Generalized location
    """
    if lat is None or lng is None:
        return "Location Unknown"

    return mask_coordinates(lat, lng)


def get_safe_logger(name: str) -> logging.Logger:
    """
    Creates logger with security warnings

    Args:
        name: Logger name

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)

    # Add filter for detecting potential PII
    class PIIDetectionFilter(logging.Filter):
        def filter(self, record):
            message = record.getMessage()

            # Simple patterns for detecting PII
            email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
            coord_pattern = r"\b\d{1,3}\.\d{4,}\b"  # Precise coordinates

            if re.search(email_pattern, message):
                record.msg = "[WARNING: Potential email detected in log] " + record.msg

            if re.search(coord_pattern, message):
                record.msg = (
                    "[WARNING: Potential coordinates detected in log] " + record.msg
                )

            return True

    logger.addFilter(PIIDetectionFilter())
    return logger


def get_client_ip(request) -> str:
    """
    Get client IP address from request safely

    Args:
        request: Django request object

    Returns:
        Client IP address or 'unknown'
    """
    try:
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR", "unknown")
        return ip
    except Exception:
        return "unknown"


def safe_user_hash(user) -> str:
    """
    Create safe hash from user object for logging

    Args:
        user: User object or None

    Returns:
        Safe hashed user identifier
    """
    try:
        if user is None or not user:
            return "usr_anon"

        uid = getattr(user, "id", None) or getattr(user, "pk", None)
        if uid is None:
            return "usr_anon"

        hash_obj = hashlib.sha256(str(uid).encode())
        return f"usr_{hash_obj.hexdigest()[:8]}"
    except Exception as e:
        return f"usr_err_{e.__class__.__name__}"


def public_emp_id(employee_id: int, salt: str = "myhours_emp_2025") -> str:
    """
    Create safe public employee identifier for logging

    Args:
        employee_id: Employee ID
        salt: Salt for hashing to prevent reverse lookup

    Returns:
        Safe public employee identifier (emp_12345678)
    """
    if not employee_id:
        return "emp_anon"

    try:
        hash_input = f"{salt}:{employee_id}"
        hash_obj = hashlib.blake2b(hash_input.encode(), digest_size=6)
        return f"emp_{hash_obj.hexdigest()}"
    except Exception:
        return f"emp_err_{employee_id % 1000}"


def err_tag(exc: BaseException) -> str:
    """
    Extract safe error tag from exception for logging

    Args:
        exc: Exception instance

    Returns:
        Safe error tag with sanitized message content
    """
    # Check if exception has safe message attributes
    for attr in ("safe_message", "public_message"):
        msg = getattr(exc, attr, None)
        if msg:
            return str(msg)[:120]

    # Get exception message and sanitize it
    text = str(exc)

    # Simple sanitization from emails and long tokens
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "***@***", text)
    text = re.sub(r"\b(?:Bearer\s+)?[A-Za-z0-9._-]{16,}\b", "****", text)

    # Limit length
    return text[:120] if text.strip() else exc.__class__.__name__


# Universal sanitizer for biometric and sensitive data logging
SENSITIVE_KEYS = {
    "employee_id",
    "user_id",
    "email",
    "phone",
    "token",
    "device_id",
    "image_b64",
    "embedding",
    "auth_header",
    "device_token",
    "session_id",
    "face_encoding",
    "biometric_data",
    "similarity",
    "distance",
    "threshold",
}

# Additional redaction keys for debug info
REDACT_KEYS = {
    "authorization",
    "cookie",
    "password",
    "token",
    "email",
    "phone",
    "auth_header",
    "session",
    "csrf",
    "secret",
}


def safe_id(v):
    """Short stable hash for IDs"""
    from hashlib import blake2b

    d = blake2b(str(v).encode("utf-8"), digest_size=6)
    return d.hexdigest()


def safe_val(v):
    """Safe value representation preserving type info"""
    if isinstance(v, (bytes, bytearray)):
        return f"<{len(v)} bytes>"
    if isinstance(v, str) and len(v) > 64:
        return f"<{len(v)} chars>"
    return v


def safe_extra_kwargs(**kwargs):
    """Create safe extra dict for logging with automatic redaction from kwargs"""
    out = {}
    for k, v in kwargs.items():
        if k.lower() in REDACT_KEYS:
            out[k] = "***"
        elif isinstance(v, dict):
            out[k] = {
                ik: ("***" if ik.lower() in REDACT_KEYS else safe_val(iv))
                for ik, iv in v.items()
            }
        else:
            out[k] = safe_val(v)
    return out


def hash_id(value: Union[int, str]) -> str:
    """
    Create a safe hash for employee/user IDs using blake2b

    Args:
        value: ID to hash (int or str)

    Returns:
        Hashed ID as hex string
    """
    from hashlib import blake2b

    h = blake2b(digest_size=8)
    h.update(str(value).encode())
    return h.hexdigest()


def redact(val):
    """
    Recursively redact sensitive values from any data structure

    Args:
        val: Value to redact (dict, list, tuple, str, etc.)

    Returns:
        Redacted version preserving structure but hiding sensitive data
    """
    if isinstance(val, dict):
        return {
            k: ("***" if k.lower() in REDACT_KEYS else redact(v))
            for k, v in val.items()
        }
    if isinstance(val, (list, tuple)):
        return [redact(v) for v in val]
    if isinstance(val, (bytes, bytearray)):
        return f"<{len(val)} bytes>"
    if isinstance(val, str) and len(val) > 64:
        return f"<{len(val)} chars>"
    return val


def redact_dict(value):
    """
    Recursively redact sensitive values from dictionaries and other structures

    Args:
        value: Value to redact (dict, list, tuple, str, etc.)

    Returns:
        Redacted version of the value
    """
    if isinstance(value, dict):
        return {
            k: "***" if k.lower() in REDACT_KEYS else redact_dict(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_dict(v) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    if isinstance(value, str) and len(value) > 64:
        return f"<{len(value)} chars>"
    return value


def redact_value(v):
    """
    Redact sensitive values while preserving structure info

    Args:
        v: Value to potentially redact

    Returns:
        Safe representation of the value
    """
    if v is None:
        return None
    if isinstance(v, (bytes, bytearray)):
        return f"<bytes:{len(v)}>"
    if isinstance(v, str) and len(v) > 0:
        return "<redacted>"
    if isinstance(v, (list, tuple)):
        return f"<{type(v).__name__}:{len(v)}>"
    if isinstance(v, set):
        return f"<set:{len(v)}>"
    if isinstance(v, dict):
        return f"<dict:{len(v)}>"
    if isinstance(v, (int, float)):
        return "<redacted>"
    return v


def safe_extra(d: dict, allow: set = None) -> dict:
    """
    Create safe extra dict for logging by redacting sensitive fields

    Args:
        d: Dictionary with potentially sensitive data
        allow: Set of keys that are safe to log as-is

    Returns:
        Sanitized dictionary safe for logging
    """
    if allow is None:
        allow = set()

    safe = {}
    for k, v in d.items():
        if k in allow:
            safe[k] = v
        elif k in SENSITIVE_KEYS:
            safe[k] = redact_value(v)
        else:
            # For non-sensitive keys, preserve simple values but redact complex ones
            # Always redact if key suggests sensitive data (ID, token, etc.)
            if (
                k.lower().endswith("_id")
                or "id" in k.lower()
                or any(
                    pattern in k.lower() for pattern in ["token", "auth", "password"]
                )
            ):
                safe[k] = redact_value(v)
            elif isinstance(v, (bool, int, float)):
                safe[k] = v
            elif (
                isinstance(v, str)
                and len(v) < 50
                and not any(
                    pattern in v.lower()
                    for pattern in ["token", "auth", "password", "@", "bearer"]
                )
            ):
                safe[k] = v
            else:
                safe[k] = redact_value(v)
    return safe


def safe_biometric_subject(obj, role="subject") -> dict:
    """
    Create safe biometric subject info for logging (extends safe_log_employee)

    Args:
        obj: Object with potential ID/PII
        role: Role description for logging context

    Returns:
        Safe subject info without PII
    """
    try:
        if hasattr(obj, "id"):
            eid = getattr(obj, "id", None)
            return {
                "role": role,
                "has_id": eid is not None,
                "id_prefix": str(eid)[:6] if eid else None,
            }
        else:
            return {"role": role, "has_id": False}
    except Exception:
        return {"role": role, "has_id": False}


# Create security debug logger with NullHandler in production
security_debug = logging.getLogger("security_debug")
if not any(isinstance(h, logging.NullHandler) for h in security_debug.handlers):
    # Add NullHandler by default (can be overridden in settings)
    security_debug.addHandler(logging.NullHandler())


# Usage examples:
"""
# For exception logging, instead of:
logger.error("Unexpected error", extra={"err": "SomeError"})  # Safe example

# Use:
from core.logging_utils import err_tag
logger.error("Unexpected error", extra={"err": err_tag(e)})

# For biometric logging, instead of:
logger.info("Biometric verification", extra={"employee_id": employee.id, "similarity": 0.85})

# Use:
from core.logging_utils import safe_extra, safe_biometric_subject
logger.info("Biometric verification", extra=safe_extra({
    "subject": safe_biometric_subject(employee),
    "has_match": similarity >= threshold
}, allow={"has_match"}))

# Instead of:
logger.info("User login", extra={"user_id": "example"})  # Safe example

# Use:
logger.info("User login", extra={"user_id": user.id})
"""
