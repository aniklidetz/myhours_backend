"""
Comprehensive tests for token rotation and replay attack detection.

Tests cover:
1. Token rotation mechanism
2. Replay attack detection
3. Token family revocation
4. Grace period handling (clock skew tolerance)
5. Security incident logging

This is critical security functionality that prevents attackers from reusing
stolen tokens after they have been rotated.
"""

import time
from datetime import timedelta
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from users.authentication import DeviceTokenAuthentication
from users.token_models import DeviceToken


class TokenRotationTests(TestCase):
    """Test token rotation mechanism"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.device_id = "test-device-12345"

    def test_token_rotation_creates_new_token(self):
        """Test that refresh() creates a new token"""
        # Create initial token
        device_token = DeviceToken.create_token(
            user=self.user, device_id=self.device_id, ttl_days=7
        )
        old_token = device_token.token

        # Refresh token (should rotate)
        new_token = device_token.refresh(ttl_days=7)

        # Verify new token was created
        self.assertIsNotNone(new_token)
        self.assertNotEqual(new_token, old_token)
        self.assertEqual(device_token.token, new_token)

    def test_token_rotation_stores_previous_token(self):
        """Test that old token is stored in previous_token"""
        device_token = DeviceToken.create_token(
            user=self.user, device_id=self.device_id, ttl_days=7
        )
        old_token = device_token.token

        # Refresh
        new_token = device_token.refresh(ttl_days=7)

        # Verify old token is stored
        device_token.refresh_from_db()
        self.assertEqual(device_token.previous_token, old_token)
        self.assertIsNotNone(device_token.previous_token_expires_at)

    def test_token_rotation_increments_counter(self):
        """Test that rotation_count is incremented"""
        device_token = DeviceToken.create_token(
            user=self.user, device_id=self.device_id, ttl_days=7
        )

        self.assertEqual(device_token.rotation_count, 0)

        # First rotation
        device_token.refresh(ttl_days=7)
        device_token.refresh_from_db()
        self.assertEqual(device_token.rotation_count, 1)

        # Second rotation
        device_token.refresh(ttl_days=7)
        device_token.refresh_from_db()
        self.assertEqual(device_token.rotation_count, 2)

    def test_expired_token_cannot_be_refreshed(self):
        """Test that expired tokens cannot be refreshed"""
        device_token = DeviceToken.create_token(
            user=self.user, device_id=self.device_id, ttl_days=7
        )

        # Expire token
        device_token.expires_at = timezone.now() - timedelta(days=1)
        device_token.save()

        # Try to refresh
        new_token = device_token.refresh(ttl_days=7)

        # Should fail
        self.assertIsNone(new_token)

    def test_inactive_token_cannot_be_refreshed(self):
        """Test that inactive tokens cannot be refreshed"""
        device_token = DeviceToken.create_token(
            user=self.user, device_id=self.device_id, ttl_days=7
        )

        # Deactivate
        device_token.is_active = False
        device_token.save()

        # Try to refresh
        new_token = device_token.refresh(ttl_days=7)

        # Should fail
        self.assertIsNone(new_token)

    def test_multiple_rotations_chain_correctly(self):
        """Test that multiple rotations work correctly"""
        device_token = DeviceToken.create_token(
            user=self.user, device_id=self.device_id, ttl_days=7
        )

        token1 = device_token.token
        token2 = device_token.refresh(ttl_days=7)
        token3 = device_token.refresh(ttl_days=7)

        # Each should be different
        self.assertNotEqual(token1, token2)
        self.assertNotEqual(token2, token3)
        self.assertNotEqual(token1, token3)

        # Previous token should be token2 (not token1)
        device_token.refresh_from_db()
        self.assertEqual(device_token.previous_token, token2)


class ReplayAttackDetectionTests(TestCase):
    """Test replay attack detection mechanism"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.device_id = "test-device-12345"
        self.auth = DeviceTokenAuthentication()

    def test_current_token_works(self):
        """Test that current token authenticates successfully"""
        device_token = DeviceToken.create_token(
            user=self.user, device_id=self.device_id, ttl_days=7
        )

        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.get("/test/")

        # Authenticate with current token
        result = self.auth.authenticate_credentials(device_token.token, request)

        self.assertIsNotNone(result)
        self.assertEqual(result[0], self.user)

    def test_old_token_within_grace_period_works(self):
        """Test that old token within grace period still works (clock skew tolerance)"""
        device_token = DeviceToken.create_token(
            user=self.user, device_id=self.device_id, ttl_days=7
        )
        old_token = device_token.token

        # Rotate with long grace period
        new_token = device_token.refresh(ttl_days=7, grace_period_seconds=60)

        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.get("/test/")

        # Old token should still work within grace period
        # Note: This will try to authenticate and check replay attack logic
        # Within grace period, it should NOT raise AuthenticationFailed
        try:
            self.auth.authenticate_credentials(old_token, request)
            # If we get here without exception, grace period logic is working
        except Exception as e:
            # Should not raise exception within grace period
            self.fail(f"Old token within grace period should work, but got: {e}")

    def test_old_token_after_grace_period_triggers_revocation(self):
        """Test that old token after grace period triggers token family revocation"""
        device_token = DeviceToken.create_token(
            user=self.user, device_id=self.device_id, ttl_days=7
        )
        old_token = device_token.token

        # Rotate with very short grace period
        new_token = device_token.refresh(ttl_days=7, grace_period_seconds=0)

        # Manually expire grace period to simulate time passing
        device_token.previous_token_expires_at = timezone.now() - timedelta(seconds=1)
        device_token.save()

        from rest_framework.exceptions import AuthenticationFailed
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.get("/test/")

        # Try to use old token after grace period - should trigger revocation
        with self.assertRaises(AuthenticationFailed) as cm:
            self.auth.authenticate_credentials(old_token, request)

        # Check error message mentions security incident
        self.assertIn("Security incident detected", str(cm.exception))

        # Verify token was revoked
        device_token.refresh_from_db()
        self.assertFalse(device_token.is_active)

    def test_token_family_revocation(self):
        """Test that entire token family is revoked on replay attack"""
        # Create multiple tokens for same user/device
        device_token1 = DeviceToken.create_token(
            user=self.user, device_id=self.device_id, ttl_days=7
        )
        old_token = device_token1.token

        # Rotate
        device_token1.refresh(ttl_days=7, grace_period_seconds=0)

        # Expire grace period
        device_token1.previous_token_expires_at = timezone.now() - timedelta(seconds=1)
        device_token1.save()

        # Verify both tokens are active before attack
        self.assertTrue(device_token1.is_active)

        from rest_framework.exceptions import AuthenticationFailed
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.get("/test/")

        # Trigger replay attack detection
        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate_credentials(old_token, request)

        # Verify all tokens for this user/device are revoked
        device_token1.refresh_from_db()
        self.assertFalse(device_token1.is_active)

    def test_invalid_token_not_confused_with_replay(self):
        """Test that completely invalid tokens don't trigger replay detection"""
        device_token = DeviceToken.create_token(
            user=self.user, device_id=self.device_id, ttl_days=7
        )

        from rest_framework.exceptions import AuthenticationFailed
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.get("/test/")

        # Try completely invalid token
        with self.assertRaises(AuthenticationFailed) as cm:
            self.auth.authenticate_credentials("invalid-token-xyz", request)

        # Should just say invalid token, not security incident
        self.assertNotIn("Security incident", str(cm.exception))

        # Token should still be active (not revoked)
        device_token.refresh_from_db()
        self.assertTrue(device_token.is_active)


class RefreshEndpointTests(APITestCase):
    """Test the refresh_token endpoint with rotation"""

    def setUp(self):
        """Set up test data"""
        from users.models import Employee

        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        # Create Employee for permission IsEmployeeOrAbove
        self.employee = Employee.objects.create(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            employment_type="full_time",
            is_active=True,
            user=self.user,
        )
        self.device_id = "test-device-12345"
        self.client = APIClient()

    def test_refresh_endpoint_returns_new_token(self):
        """Test that refresh endpoint returns new token"""
        device_token = DeviceToken.create_token(
            user=self.user, device_id=self.device_id, ttl_days=7
        )
        old_token = device_token.token

        # Call refresh endpoint
        self.client.credentials(HTTP_AUTHORIZATION=f"DeviceToken {old_token}")
        response = self.client.post("/api/v1/users/auth/refresh-token/", {})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])

        new_token = response.data["token"]

        # New token should be different
        self.assertNotEqual(new_token, old_token)

        # rotation_count should be included
        self.assertIn("rotation_count", response.data)
        self.assertEqual(response.data["rotation_count"], 1)

    def test_refresh_endpoint_old_token_stops_working(self):
        """Test that old token stops working after refresh (after grace period)"""
        device_token = DeviceToken.create_token(
            user=self.user, device_id=self.device_id, ttl_days=7
        )
        old_token = device_token.token

        # Refresh
        self.client.credentials(HTTP_AUTHORIZATION=f"DeviceToken {old_token}")
        response = self.client.post("/api/v1/users/auth/refresh-token/", {})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        new_token = response.data["token"]

        # Expire grace period manually
        device_token.refresh_from_db()
        device_token.previous_token_expires_at = timezone.now() - timedelta(seconds=1)
        device_token.save()

        # Try to use old token - should fail and trigger revocation
        self.client.credentials(HTTP_AUTHORIZATION=f"DeviceToken {old_token}")
        response = self.client.post("/api/v1/users/auth/refresh-token/", {})

        # Should fail with 401
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # All tokens should be revoked
        device_token.refresh_from_db()
        self.assertFalse(device_token.is_active)

    def test_new_token_works_after_refresh(self):
        """Test that new token works after refresh"""
        device_token = DeviceToken.create_token(
            user=self.user, device_id=self.device_id, ttl_days=7
        )
        old_token = device_token.token

        # Refresh
        self.client.credentials(HTTP_AUTHORIZATION=f"DeviceToken {old_token}")
        response = self.client.post("/api/v1/users/auth/refresh-token/", {})

        # Check response is successful first
        if response.status_code != status.HTTP_200_OK:
            print(
                f"First refresh failed: {response.status_code}, content: {response.content}"
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        new_token = response.data["token"]

        # Use new token for another request
        self.client.credentials(HTTP_AUTHORIZATION=f"DeviceToken {new_token}")
        response = self.client.post("/api/v1/users/auth/refresh-token/", {})

        # Should work
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class SecurityLoggingTests(TestCase):
    """Test that security events are properly logged"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.device_id = "test-device-12345"
        self.auth = DeviceTokenAuthentication()

    @patch("users.authentication.logger")
    def test_replay_attack_logged_as_critical(self, mock_logger):
        """Test that replay attacks are logged as CRITICAL"""
        device_token = DeviceToken.create_token(
            user=self.user, device_id=self.device_id, ttl_days=7
        )
        old_token = device_token.token

        # Rotate and expire grace period
        device_token.refresh(ttl_days=7, grace_period_seconds=0)
        device_token.previous_token_expires_at = timezone.now() - timedelta(seconds=1)
        device_token.save()

        from rest_framework.exceptions import AuthenticationFailed
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.get("/test/")

        # Trigger replay attack
        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate_credentials(old_token, request)

        # Verify critical logging
        critical_calls = [
            call
            for call in mock_logger.critical.call_args_list
            if "REPLAY ATTACK DETECTED" in str(call)
        ]
        self.assertGreater(
            len(critical_calls), 0, "Replay attack should be logged as CRITICAL"
        )

    @patch("users.token_models.logger")
    def test_token_rotation_logged(self, mock_logger):
        """Test that token rotations are logged"""
        device_token = DeviceToken.create_token(
            user=self.user, device_id=self.device_id, ttl_days=7
        )

        # Rotate
        device_token.refresh(ttl_days=7)

        # Verify info logging
        info_calls = [
            call
            for call in mock_logger.info.call_args_list
            if "Token rotated" in str(call)
        ]
        self.assertGreater(len(info_calls), 0, "Token rotation should be logged")


class EdgeCaseTests(TestCase):
    """Test edge cases and race conditions"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.device_id = "test-device-12345"
        self.auth = DeviceTokenAuthentication()

    def test_concurrent_refresh_attempts(self):
        """Test that concurrent refresh attempts are handled safely"""
        device_token = DeviceToken.create_token(
            user=self.user, device_id=self.device_id, ttl_days=7
        )

        # Simulate concurrent refresh (same token used twice)
        token1 = device_token.refresh(ttl_days=7)
        token2 = device_token.refresh(ttl_days=7)

        # Both should succeed and return different tokens
        self.assertIsNotNone(token1)
        self.assertIsNotNone(token2)
        self.assertNotEqual(token1, token2)

    def test_grace_period_edge_at_expiry(self):
        """Test grace period exactly at expiry time"""
        device_token = DeviceToken.create_token(
            user=self.user, device_id=self.device_id, ttl_days=7
        )
        old_token = device_token.token

        # Rotate
        device_token.refresh(ttl_days=7, grace_period_seconds=1)

        # Set grace period to expire NOW (edge case)
        device_token.previous_token_expires_at = timezone.now()
        device_token.save()

        # Slight delay to ensure it's expired
        time.sleep(0.1)

        from rest_framework.exceptions import AuthenticationFailed
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        request = factory.get("/test/")

        # Should trigger revocation (grace period expired)
        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate_credentials(old_token, request)


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v", "--tb=short"])
