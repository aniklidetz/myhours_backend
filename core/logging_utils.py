"""
Utilities for safe logging with automatic PII data masking
"""
import re
import hashlib
import logging
from typing import Any, Dict, Optional, Union


def mask_email(email: str) -> str:
    """
    Masks email address for safe logging
    
    Args:
        email: Email address to mask
        
    Returns:
        Masked email (e.g., a***@example.com)
    """
    if not email or '@' not in email:
        return '[invalid_email]'
    
    username, domain = email.split('@', 1)
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
        return '[no_phone]'
    
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', phone)
    
    if len(digits) < 4:
        return '***'
    
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
        return '[no_name]'
    
    parts = full_name.strip().split()
    if len(parts) == 1:
        return f"{parts[0][0]}."
    elif len(parts) >= 2:
        return f"{parts[0][0]}.{parts[1][0]}."
    
    return '[no_name]'


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
        return '[no_id]'
    
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
        "role": getattr(user, 'role', 'unknown'),
        "is_superuser": getattr(user, 'is_superuser', False)
    }
    
    # Mask email if present
    if hasattr(user, 'email') and user.email:
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
        "role": getattr(employee, 'role', 'unknown'),
        "employment_type": getattr(employee, 'employment_type', 'unknown')
    }
    
    # Mask personal data
    if hasattr(employee, 'email') and employee.email:
        safe_data["email_masked"] = mask_email(employee.email)
    
    if hasattr(employee, 'first_name') and hasattr(employee, 'last_name'):
        full_name = f"{employee.first_name or ''} {employee.last_name or ''}".strip()
        if full_name:
            safe_data["name_initials"] = mask_name(full_name)
    
    if hasattr(employee, 'phone') and employee.phone:
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
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            coord_pattern = r'\b\d{1,3}\.\d{4,}\b'  # Precise coordinates
            
            if re.search(email_pattern, message):
                record.msg = "[WARNING: Potential email detected in log] " + record.msg
            
            if re.search(coord_pattern, message):
                record.msg = "[WARNING: Potential coordinates detected in log] " + record.msg
            
            return True
    
    logger.addFilter(PIIDetectionFilter())
    return logger


# Usage examples:
"""
# In views.py instead of:
logger.info(f"Invitation URL for {employee.email}: {invitation_url}")

# Use:
logger.info(f"Invitation URL generated", extra=safe_log_employee(employee, "invitation_sent"))

# Instead of:
logger.info(f"User {user.email} logged in from {lat}, {lng}")

# Use:
safe_logger = get_safe_logger(__name__)
safe_logger.info(f"User login", extra={
    **safe_log_user(user, "login"),
    "location": safe_log_location(lat, lng)
})
"""