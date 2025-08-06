# core/middleware.py
import time
import json
import logging
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from core.logging_utils import safe_log_user, hash_user_id

logger = logging.getLogger(__name__)


class APIResponseMiddleware(MiddlewareMixin):
    """
    Middleware to enhance API responses with metadata
    """

    def process_request(self, request):
        """
        Mark request start time for performance tracking
        """
        request._start_time = time.time()
        return None

    def process_response(self, request, response):
        """
        Enhance API responses with standard metadata
        """
        # Only process JSON API responses
        if (
            hasattr(response, "data")
            and request.path.startswith("/api/")
            and response.get("Content-Type", "").startswith("application/json")
        ):

            # Calculate processing time
            processing_time = None
            if hasattr(request, "_start_time"):
                processing_time = round((time.time() - request._start_time) * 1000, 2)

            # Add timestamp to error responses
            if isinstance(response.data, dict) and response.data.get("error"):
                response.data["timestamp"] = timezone.now().isoformat()
                if processing_time:
                    response.data["processing_time_ms"] = processing_time

            # Add metadata to successful list responses (pagination info, etc.)
            elif isinstance(response.data, dict) and "results" in response.data:
                # This is a paginated response from DRF
                if processing_time:
                    response.data["meta"] = response.data.get("meta", {})
                    response.data["meta"]["processing_time_ms"] = processing_time

            # Add version info to root API endpoint
            elif request.path in ["/api/", "/api/v1/"]:
                if processing_time:
                    response.data["meta"] = {
                        "processing_time_ms": processing_time,
                        "timestamp": timezone.now().isoformat(),
                    }

        return response


class APILoggingMiddleware(MiddlewareMixin):
    """
    Middleware for comprehensive API request/response logging
    """

    def process_request(self, request):
        """
        Log incoming API requests
        """
        if request.path.startswith("/api/") and request.path not in [
            "/api/schema/",
            "/api/docs/",
            "/api/redoc/",
        ]:
            # Безопасное логирование без PII
            log_data = {
                "method": request.method,
                "path": request.path,
                "user_hash": (
                    hash_user_id(request.user.id)
                    if hasattr(request, "user") and request.user.is_authenticated
                    else "anonymous"
                ),
                "ip": self.get_client_ip(request),
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[
                    :100
                ],  # Truncate long user agents
            }

            # Log query parameters (but not for sensitive endpoints)
            if not any(
                sensitive in request.path for sensitive in ["/auth/", "/biometrics/"]
            ):
                log_data["query_params"] = dict(request.GET)

            logger.info(f"API Request: {json.dumps(log_data)}")

        return None

    def process_response(self, request, response):
        """
        Log API responses (errors and important status codes)
        """
        if (
            request.path.startswith("/api/")
            and request.path not in ["/api/schema/", "/api/docs/", "/api/redoc/"]
            and response.status_code >= 400
        ):

            log_data = {
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "user_hash": (
                    hash_user_id(request.user.id)
                    if hasattr(request, "user") and request.user.is_authenticated
                    else "anonymous"
                ),
                "ip": self.get_client_ip(request),
            }

            # Log error details for server errors
            if response.status_code >= 500:
                logger.error(f"API Server Error: {json.dumps(log_data)}")
            else:
                logger.warning(f"API Client Error: {json.dumps(log_data)}")

        return response

    def get_client_ip(self, request):
        """Extract client IP from request"""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip


class APIVersionMiddleware(MiddlewareMixin):
    """
    Middleware to handle API versioning headers and validation
    """

    def process_request(self, request):
        """
        Process API version information from headers or URL
        """
        if request.path.startswith("/api/"):
            # Extract version from URL
            if "/v1/" in request.path:
                request.api_version = "v1"
            elif "/v2/" in request.path:
                request.api_version = "v2"
            else:
                # Default version for legacy URLs
                request.api_version = "v1"

            # Check Accept-Version header if present
            accept_version = request.META.get("HTTP_ACCEPT_VERSION")
            if accept_version and accept_version != request.api_version:
                logger.warning(
                    f"Version mismatch: URL has {request.api_version}, "
                    f"Header requests {accept_version}"
                )

        return None

    def process_response(self, request, response):
        """
        Add API version to response headers
        """
        if hasattr(request, "api_version"):
            response["X-API-Version"] = request.api_version
            response["X-API-Supported-Versions"] = "v1"
            response["X-API-Deprecated-Versions"] = ""

        return response
