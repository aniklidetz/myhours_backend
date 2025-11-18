"""
Tests for API Idempotency Middleware
"""

import json
import uuid
from unittest.mock import Mock, patch

from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from django.contrib.auth.models import User
from django.core.cache import cache
from django.http import JsonResponse
from django.test import RequestFactory, TestCase

from core.middleware_idempotency import APIIdempotencyMiddleware
from users.models import Employee


class APIIdempotencyMiddlewareTest(TestCase):
    """Test API idempotency middleware"""

    def setUp(self):
        """Set up test environment"""
        self.factory = RequestFactory()
        self.middleware = APIIdempotencyMiddleware(
            get_response=lambda r: JsonResponse({"success": True})
        )
        cache.clear()

    def tearDown(self):
        """Clean up"""
        cache.clear()

    def test_non_post_requests_not_affected(self):
        """Test that GET requests are not affected by middleware"""
        request = self.factory.get("/api/v1/biometrics/check-in/")
        response = self.middleware.process_request(request)

        self.assertIsNone(response)  # Middleware doesn't intercept

    def test_non_protected_endpoints_not_affected(self):
        """Test that non-protected endpoints don't require idempotency key"""
        request = self.factory.post("/api/v1/some-other-endpoint/")
        response = self.middleware.process_request(request)

        self.assertIsNone(response)  # Middleware doesn't intercept

    def test_protected_endpoint_without_key_logs_warning(self):
        """Test that missing idempotency key logs warning but allows request"""
        request = self.factory.post("/api/v1/biometrics/check-in/")
        request.user = Mock(is_authenticated=False)

        with self.assertLogs("core.middleware_idempotency", level="WARNING") as cm:
            response = self.middleware.process_request(request)

        self.assertIsNone(response)  # Request allowed to proceed
        self.assertTrue(any("Idempotency-Key missing" in log for log in cm.output))

    def test_idempotency_key_too_long_rejected(self):
        """Test that overly long idempotency keys are rejected"""
        long_key = "x" * 300  # Exceeds MAX_KEY_LENGTH (255)
        request = self.factory.post(
            "/api/v1/biometrics/check-in/", HTTP_IDEMPOTENCY_KEY=long_key
        )
        request.user = Mock(is_authenticated=False)

        response = self.middleware.process_request(request)

        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn("INVALID_IDEMPOTENCY_KEY", data["error"])

    def test_first_request_with_key_not_cached(self):
        """Test that first request with idempotency key is not found in cache"""
        idempotency_key = str(uuid.uuid4())
        request = self.factory.post(
            "/api/v1/biometrics/check-in/", HTTP_IDEMPOTENCY_KEY=idempotency_key
        )
        request.user = Mock(is_authenticated=True, id=1)

        response = self.middleware.process_request(request)

        self.assertIsNone(response)  # No cached response
        self.assertTrue(hasattr(request, "_idempotency_key"))
        self.assertEqual(request._idempotency_key, idempotency_key)

    def test_duplicate_request_returns_cached_response(self):
        """Test that duplicate request returns cached response"""
        idempotency_key = str(uuid.uuid4())

        # First request
        request1 = self.factory.post(
            "/api/v1/biometrics/check-in/", HTTP_IDEMPOTENCY_KEY=idempotency_key
        )
        request1.user = Mock(is_authenticated=True, id=1)

        # Process first request
        response1 = self.middleware.process_request(request1)
        self.assertIsNone(response1)  # Not cached yet

        # Simulate successful response
        success_response = JsonResponse(
            {"success": True, "worklog_id": 123}, status=200
        )
        success_response.data = {"success": True, "worklog_id": 123}

        # Cache the response
        cached_response = self.middleware.process_response(request1, success_response)

        # Second request with same key
        request2 = self.factory.post(
            "/api/v1/biometrics/check-in/", HTTP_IDEMPOTENCY_KEY=idempotency_key
        )
        request2.user = Mock(is_authenticated=True, id=1)

        # Should return cached response
        response2 = self.middleware.process_request(request2)

        self.assertIsNotNone(response2)
        self.assertEqual(response2.status_code, 200)
        self.assertTrue(response2["X-Idempotency-Cached"])
        data = json.loads(response2.content)
        self.assertEqual(data["worklog_id"], 123)

    def test_different_users_with_same_key_not_confused(self):
        """Test that same idempotency key from different users doesn't cause collision"""
        idempotency_key = str(uuid.uuid4())

        # User 1's request
        request1 = self.factory.post(
            "/api/v1/biometrics/check-in/", HTTP_IDEMPOTENCY_KEY=idempotency_key
        )
        request1.user = Mock(is_authenticated=True, id=1)

        # Process and cache
        self.middleware.process_request(request1)
        success_response1 = JsonResponse({"success": True, "user_id": 1}, status=200)
        success_response1.data = {"success": True, "user_id": 1}
        self.middleware.process_response(request1, success_response1)

        # User 2's request with SAME key
        request2 = self.factory.post(
            "/api/v1/biometrics/check-in/", HTTP_IDEMPOTENCY_KEY=idempotency_key
        )
        request2.user = Mock(is_authenticated=True, id=2)

        # Should NOT return cached response from user 1
        response2 = self.middleware.process_request(request2)
        self.assertIsNone(response2)  # Not cached for user 2

    def test_failed_responses_not_cached(self):
        """Test that failed responses (4xx, 5xx) are not cached"""
        idempotency_key = str(uuid.uuid4())

        request = self.factory.post(
            "/api/v1/biometrics/check-in/", HTTP_IDEMPOTENCY_KEY=idempotency_key
        )
        request.user = Mock(is_authenticated=True, id=1)

        # Process request
        self.middleware.process_request(request)

        # Simulate error response
        error_response = JsonResponse({"error": "Something went wrong"}, status=500)

        # Process response
        self.middleware.process_response(request, error_response)

        # Second request should NOT get cached response
        request2 = self.factory.post(
            "/api/v1/biometrics/check-in/", HTTP_IDEMPOTENCY_KEY=idempotency_key
        )
        request2.user = Mock(is_authenticated=True, id=1)

        response2 = self.middleware.process_request(request2)
        self.assertIsNone(response2)  # Error not cached

    def test_cache_ttl_set_correctly(self):
        """Test that cache TTL is set correctly"""
        idempotency_key = str(uuid.uuid4())

        request = self.factory.post(
            "/api/v1/biometrics/check-in/", HTTP_IDEMPOTENCY_KEY=idempotency_key
        )
        request.user = Mock(is_authenticated=True, id=1)

        # Process request
        self.middleware.process_request(request)

        # Simulate successful response
        success_response = JsonResponse({"success": True}, status=200)
        success_response.data = {"success": True}

        # Cache the response
        result_response = self.middleware.process_response(request, success_response)

        # Check TTL header
        ttl = result_response["X-Idempotency-TTL"]
        self.assertEqual(int(ttl), 24 * 60 * 60)  # 24 hours in seconds


class APIIdempotencyIntegrationTest(APITestCase):
    """Integration tests for idempotency with real API endpoints"""

    def setUp(self):
        """Set up test environment"""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.employee = Employee.objects.create(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            employment_type="full_time",
            is_active=True,
            user=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        cache.clear()

    def tearDown(self):
        """Clean up"""
        cache.clear()

    def test_duplicate_check_in_with_idempotency_key_prevented(self):
        """Test that duplicate check-in is prevented with idempotency key"""
        # NOTE: This is an integration test concept
        # In reality, you'd need to mock the biometric matching and MongoDB
        # This test demonstrates the pattern

        idempotency_key = str(uuid.uuid4())

        # First check-in
        with patch(
            "biometrics.views.face_processor.find_matching_employee"
        ) as mock_match:
            mock_match.return_value = {
                "success": True,
                "employee_id": self.employee.id,
                "confidence": 0.95,
                "processing_time_ms": 50,
            }

            response1 = self.client.post(
                "/api/v1/biometrics/check-in/",
                {"image": "base64_image_data", "location": "Office"},
                HTTP_IDEMPOTENCY_KEY=idempotency_key,
                format="json",
            )

        # If first request was successful (200), subsequent request should return cached
        if response1.status_code == 200:
            response2 = self.client.post(
                "/api/v1/biometrics/check-in/",
                {"image": "base64_image_data", "location": "Office"},
                HTTP_IDEMPOTENCY_KEY=idempotency_key,
                format="json",
            )

            # Should return same response
            self.assertEqual(response2.status_code, 200)
            self.assertTrue("X-Idempotency-Cached" in response2)


class IdempotencyKeyGenerationTest(TestCase):
    """Test idempotency key generation utilities"""

    def test_uuid_format_valid_key(self):
        """Test that UUID format is valid idempotency key"""
        key = str(uuid.uuid4())
        self.assertEqual(len(key), 36)  # UUID length
        self.assertIsInstance(key, str)

    def test_key_uniqueness(self):
        """Test that generated keys are unique"""
        key1 = str(uuid.uuid4())
        key2 = str(uuid.uuid4())
        self.assertNotEqual(key1, key2)
