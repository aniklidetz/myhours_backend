"""
API Idempotency Middleware for Critical Endpoints

Prevents duplicate API requests using Idempotency-Key header.
Based on Stripe's idempotency implementation:
https://stripe.com/docs/api/idempotent_requests

Usage:
    Add 'core.middleware_idempotency.APIIdempotencyMiddleware' to MIDDLEWARE

Critical endpoints protected:
- POST /api/v1/biometrics/check-in/
- POST /api/v1/biometrics/check-out/
- POST /api/v1/biometrics/register/
- POST /api/v1/payroll/calculate/
- POST /api/v1/payroll/bulk-calculate/

Client sends:
    POST /api/v1/biometrics/check-in/
    Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000

Response cached for 24 hours. Subsequent requests with same key return cached response.
"""

import hashlib
import json
import logging
from datetime import timedelta

from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class APIIdempotencyMiddleware(MiddlewareMixin):
    """
    Middleware for API request idempotency using Idempotency-Key header.

    Protects critical POST endpoints from duplicate execution.
    """

    # Endpoints that require idempotency protection
    IDEMPOTENT_ENDPOINTS = {
        '/api/v1/biometrics/check-in/',
        '/api/v1/biometrics/check-out/',
        '/api/v1/biometrics/register/',
        '/api/v1/payroll/calculate/',
        '/api/v1/payroll/bulk-calculate/',
        '/api/v1/payroll/monthly-summary/',
    }

    # TTL for idempotency cache (24 hours)
    IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60

    # Max idempotency key length
    MAX_KEY_LENGTH = 255

    def process_request(self, request):
        """
        Check for idempotency key before processing request.

        Returns cached response if request was already processed.
        """
        # Only apply to POST requests on protected endpoints
        if request.method != 'POST':
            return None

        if request.path not in self.IDEMPOTENT_ENDPOINTS:
            return None

        # Get idempotency key from header
        idempotency_key = request.META.get('HTTP_IDEMPOTENCY_KEY')

        if not idempotency_key:
            # Idempotency key not provided - allow request but log warning
            logger.warning(
                f"Idempotency-Key missing for critical endpoint: {request.path}",
                extra={
                    "path": request.path,
                    "method": request.method,
                    "user_id": request.user.id if request.user.is_authenticated else None
                }
            )
            return None

        # Validate idempotency key format
        if len(idempotency_key) > self.MAX_KEY_LENGTH:
            return JsonResponse(
                {
                    "error": "INVALID_IDEMPOTENCY_KEY",
                    "message": f"Idempotency-Key too long (max {self.MAX_KEY_LENGTH} characters)",
                    "timestamp": timezone.now().isoformat(),
                },
                status=400
            )

        # Generate cache key
        cache_key = self._make_cache_key(request, idempotency_key)

        # Check if request was already processed
        cached_response = cache.get(cache_key)

        if cached_response:
            logger.info(
                f"Idempotent request detected - returning cached response",
                extra={
                    "path": request.path,
                    "idempotency_key": idempotency_key[:16] + "...",
                    "user_id": request.user.id if request.user.is_authenticated else None
                }
            )

            # Return cached response
            response = JsonResponse(cached_response['data'], status=cached_response['status'])
            response['X-Idempotency-Cached'] = 'true'
            response['X-Idempotency-Original-Timestamp'] = cached_response['timestamp']
            return response

        # Store idempotency key in request for process_response
        request._idempotency_key = idempotency_key
        request._idempotency_cache_key = cache_key

        return None

    def process_response(self, request, response):
        """
        Cache successful responses for idempotency.
        """
        # Only cache if idempotency key was provided
        if not hasattr(request, '_idempotency_key'):
            return response

        # Only cache successful responses (200-299)
        if not (200 <= response.status_code < 300):
            logger.debug(
                f"Not caching response for idempotency (status {response.status_code})",
                extra={"path": request.path}
            )
            return response

        # Cache the response
        try:
            # Parse response data
            if hasattr(response, 'data'):
                # DRF Response
                response_data = response.data
            elif response['Content-Type'] == 'application/json':
                # Django JsonResponse
                response_data = json.loads(response.content)
            else:
                # Non-JSON response - don't cache
                return response

            cached_response = {
                'data': response_data,
                'status': response.status_code,
                'timestamp': timezone.now().isoformat(),
            }

            # Store in cache
            cache.set(
                request._idempotency_cache_key,
                cached_response,
                timeout=self.IDEMPOTENCY_TTL_SECONDS
            )

            logger.info(
                f"Cached response for idempotency",
                extra={
                    "path": request.path,
                    "idempotency_key": request._idempotency_key[:16] + "...",
                    "ttl_hours": self.IDEMPOTENCY_TTL_SECONDS / 3600
                }
            )

            # Add header to indicate response was cached
            response['X-Idempotency-Cached'] = 'false'
            response['X-Idempotency-TTL'] = str(self.IDEMPOTENCY_TTL_SECONDS)

        except Exception as e:
            logger.error(
                f"Failed to cache response for idempotency: {e}",
                extra={"path": request.path}
            )

        return response

    def _make_cache_key(self, request, idempotency_key):
        """
        Generate cache key from request and idempotency key.

        Includes user ID to prevent cross-user key collisions.
        """
        # Include user ID for security
        user_id = request.user.id if request.user.is_authenticated else 'anonymous'

        # Hash the idempotency key for consistent length
        key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()[:32]

        # Build cache key
        cache_key = f"idempotency:{request.path}:{user_id}:{key_hash}"

        return cache_key
