# core/exceptions.py
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError
from django.http import Http404
import logging
import uuid

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler that returns consistent error format
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)

    # Generate unique error ID for tracking
    error_id = str(uuid.uuid4())[:8]

    # Get request info for logging
    request = context.get("request")
    user = getattr(request, "user", None)
    path = getattr(request, "path", "unknown")
    method = getattr(request, "method", "unknown")

    if response is not None:
        # Standard DRF exceptions
        custom_response_data = {
            "error": True,
            "code": get_error_code(exc),
            "message": get_error_message(response.data),
            "details": format_error_details(response.data),
            "error_id": error_id,
            "timestamp": None,  # Will be set by middleware
        }

        # Log the error
        logger.error(
            f"API Error [{error_id}]: {exc.__class__.__name__} - "
            f"{method} {path} - User: {user} - Status: {response.status_code}"
        )

        response.data = custom_response_data

    else:
        # Handle non-DRF exceptions
        if isinstance(exc, Http404):
            custom_response_data = {
                "error": True,
                "code": "RESOURCE_NOT_FOUND",
                "message": "The requested resource was not found.",
                "details": None,
                "error_id": error_id,
                "timestamp": None,
            }
            response = Response(custom_response_data, status=status.HTTP_404_NOT_FOUND)

        elif isinstance(exc, ValidationError):
            custom_response_data = {
                "error": True,
                "code": "VALIDATION_ERROR",
                "message": "Validation failed.",
                "details": (
                    exc.message_dict if hasattr(exc, "message_dict") else str(exc)
                ),
                "error_id": error_id,
                "timestamp": None,
            }
            response = Response(
                custom_response_data, status=status.HTTP_400_BAD_REQUEST
            )

        else:
            # Generic server error
            custom_response_data = {
                "error": True,
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An internal server error occurred.",
                "details": None,
                "error_id": error_id,
                "timestamp": None,
            }
            response = Response(
                custom_response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Log unhandled exceptions
        logger.error(
            f"Unhandled Exception [{error_id}]: {exc.__class__.__name__} - "
            f"{method} {path} - User: {user}",
            exc_info=True,
        )

    return response


def get_error_code(exc):
    """
    Generate appropriate error code based on exception type
    """
    error_codes = {
        "ValidationError": "VALIDATION_ERROR",
        "PermissionDenied": "PERMISSION_DENIED",
        "NotAuthenticated": "AUTHENTICATION_REQUIRED",
        "AuthenticationFailed": "AUTHENTICATION_FAILED",
        "NotFound": "RESOURCE_NOT_FOUND",
        "MethodNotAllowed": "METHOD_NOT_ALLOWED",
        "ParseError": "PARSE_ERROR",
        "UnsupportedMediaType": "UNSUPPORTED_MEDIA_TYPE",
        "Throttled": "RATE_LIMIT_EXCEEDED",
    }

    exc_name = exc.__class__.__name__
    return error_codes.get(exc_name, "UNKNOWN_ERROR")


def get_error_message(data):
    """
    Extract human-readable error message from DRF error data
    """
    if isinstance(data, dict):
        if "detail" in data:
            return str(data["detail"])
        elif "non_field_errors" in data:
            return (
                str(data["non_field_errors"][0])
                if data["non_field_errors"]
                else "Validation error"
            )
        else:
            # Get first error message from any field
            for key, value in data.items():
                if isinstance(value, list) and value:
                    return str(value[0])
                elif isinstance(value, str):
                    return value
            return "Validation error"
    elif isinstance(data, list) and data:
        return str(data[0])
    else:
        return str(data)


def format_error_details(data):
    """
    Format error details for consistent structure
    """
    if isinstance(data, dict):
        # Remove 'detail' from details since it's in message
        details = {k: v for k, v in data.items() if k != "detail"}
        return details if details else None
    elif isinstance(data, list):
        return data
    else:
        return None


class APIError(Exception):
    """
    Custom API exception class for business logic errors
    """

    def __init__(
        self, message, code=None, status_code=status.HTTP_400_BAD_REQUEST, details=None
    ):
        super().__init__(message)
        self.message = message
        self.code = code or "API_ERROR"
        self.status_code = status_code
        self.details = details


class BiometricError(APIError):
    """
    Specific exception for biometric-related errors
    """

    def __init__(self, message, code=None, details=None):
        super().__init__(
            message=message,
            code=code or "BIOMETRIC_ERROR",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class AuthenticationError(APIError):
    """
    Specific exception for authentication-related errors
    """

    def __init__(self, message, code=None, details=None):
        super().__init__(
            message=message,
            code=code or "AUTHENTICATION_ERROR",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class PermissionError(APIError):
    """
    Specific exception for permission-related errors
    """

    def __init__(self, message, code=None, details=None):
        super().__init__(
            message=message,
            code=code or "PERMISSION_ERROR",
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )
