"""
Advanced tests for users/authentication.py to improve coverage from 23% to 65%+

Tests authentication classes:
- DeviceTokenAuthentication
- BiometricSessionAuthentication  
- HybridAuthentication
- SecurityMiddleware
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

from rest_framework.exceptions import AuthenticationFailed

from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory, TestCase
from django.utils import timezone

from users.authentication import (
    BiometricSessionAuthentication,
    DeviceTokenAuthentication,
    HybridAuthentication,
    SecurityMiddleware,
)
from users.models import Employee
from users.token_models import BiometricSession, DeviceToken


class DeviceTokenAuthenticationTest(TestCase):
    """Test DeviceTokenAuthentication class"""
    
    def setUp(self):
        self.factory = RequestFactory()
        self.auth = DeviceTokenAuthentication()
        
        # Create test user and employee
        self.user = User.objects.create_user(
            username="testuser", email="test@test.com", password="pass123"
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Test", last_name="User",
            email="test@test.com",
            employment_type="full_time", role="employee"
        )
        
        # Create valid device token
        self.device_token = DeviceToken.objects.create(
            user=self.user,
            device_id="test-device-12345",
            token="test-token-abcdef123456",
            expires_at=timezone.now() + timedelta(days=30)
        )
    
    def test_authenticate_no_header(self):
        """Test authentication with no authorization header"""
        request = self.factory.get('/')
        result = self.auth.authenticate(request)
        self.assertIsNone(result)
    
    def test_authenticate_wrong_keyword(self):
        """Test authentication with wrong keyword"""
        request = self.factory.get('/', HTTP_AUTHORIZATION='Bearer token123')
        result = self.auth.authenticate(request)
        self.assertIsNone(result)
    
    def test_authenticate_no_credentials(self):
        """Test authentication with keyword but no token"""
        request = self.factory.get('/', HTTP_AUTHORIZATION='DeviceToken')
        with self.assertRaises(AuthenticationFailed) as cm:
            self.auth.authenticate(request)
        self.assertIn("No credentials provided", str(cm.exception))
    
    def test_authenticate_too_many_parts(self):
        """Test authentication with too many authorization parts"""
        request = self.factory.get('/', HTTP_AUTHORIZATION='DeviceToken token1 token2 token3')
        with self.assertRaises(AuthenticationFailed) as cm:
            self.auth.authenticate(request)
        self.assertIn("should not contain spaces", str(cm.exception))
    
    def test_authenticate_unicode_error(self):
        """Test authentication with invalid unicode in token"""
        with patch('users.authentication.DeviceTokenAuthentication.get_authorization_header') as mock_get_header:
            mock_get_header.return_value = b'DeviceToken \xff\xfe'
            request = self.factory.get('/')
            
            with self.assertRaises(AuthenticationFailed) as cm:
                self.auth.authenticate(request)
            self.assertIn("invalid characters", str(cm.exception))
    
    def test_authenticate_credentials_invalid_token(self):
        """Test authenticate_credentials with invalid token"""
        with self.assertRaises(AuthenticationFailed) as cm:
            self.auth.authenticate_credentials("invalid-token", self.factory.get('/'))
        self.assertEqual(str(cm.exception), "Invalid token.")
    
    def test_authenticate_credentials_expired_token(self):
        """Test authenticate_credentials with expired token"""
        # Create expired token
        expired_token = DeviceToken.objects.create(
            user=self.user,
            device_id="expired-device", 
            token="expired-token-123",
            expires_at=timezone.now() - timedelta(days=1)  # Expired
        )
        
        with self.assertRaises(AuthenticationFailed) as cm:
            self.auth.authenticate_credentials("expired-token-123", self.factory.get('/'))
        self.assertEqual(str(cm.exception), "Token expired.")
        
        # Check that token was deactivated
        expired_token.refresh_from_db()
        self.assertFalse(expired_token.is_active)
    
    def test_authenticate_credentials_inactive_user(self):
        """Test authenticate_credentials with inactive user"""
        # Deactivate user
        self.user.is_active = False
        self.user.save()
        
        with self.assertRaises(AuthenticationFailed) as cm:
            self.auth.authenticate_credentials("test-token-abcdef123456", self.factory.get('/'))
        self.assertEqual(str(cm.exception), "User inactive or deleted.")
    
    def test_authenticate_credentials_success(self):
        """Test successful authenticate_credentials"""
        request = self.factory.get('/')
        
        with patch('users.authentication.DeviceTokenAuthentication.get_client_ip') as mock_get_ip:
            mock_get_ip.return_value = "192.168.1.1"
            
            user, token = self.auth.authenticate_credentials("test-token-abcdef123456", request)
            
            self.assertEqual(user, self.user)
            self.assertEqual(token, self.device_token)
            self.assertTrue(hasattr(request, 'device_token'))
            self.assertEqual(request.device_token, self.device_token)
    
    def test_get_authorization_header_string(self):
        """Test get_authorization_header with string input"""
        request = Mock()
        request.META = {'HTTP_AUTHORIZATION': 'DeviceToken abc123'}
        
        header = self.auth.get_authorization_header(request)
        self.assertEqual(header, b'DeviceToken abc123')
    
    def test_get_authorization_header_bytes(self):
        """Test get_authorization_header with bytes input"""
        request = Mock()
        request.META = {'HTTP_AUTHORIZATION': b'DeviceToken abc123'}
        
        header = self.auth.get_authorization_header(request)
        self.assertEqual(header, b'DeviceToken abc123')
    
    def test_get_authorization_header_missing(self):
        """Test get_authorization_header with missing header"""
        request = Mock()
        request.META = {}
        
        header = self.auth.get_authorization_header(request)
        self.assertEqual(header, b'')
    
    def test_get_client_ip_with_forwarded(self):
        """Test get_client_ip with X-Forwarded-For header"""
        request = Mock()
        request.META = {'HTTP_X_FORWARDED_FOR': '10.0.0.1,192.168.1.1'}
        
        ip = self.auth.get_client_ip(request)
        self.assertEqual(ip, '10.0.0.1')
    
    def test_get_client_ip_without_forwarded(self):
        """Test get_client_ip without X-Forwarded-For header"""
        request = Mock()
        request.META = {'REMOTE_ADDR': '192.168.1.100'}
        
        ip = self.auth.get_client_ip(request)
        self.assertEqual(ip, '192.168.1.100')
    
    def test_get_client_ip_no_headers(self):
        """Test get_client_ip with no IP headers"""
        request = Mock()
        request.META = {}
        
        ip = self.auth.get_client_ip(request)
        self.assertIsNone(ip)
    
    def test_authenticate_header(self):
        """Test authenticate_header method"""
        header = self.auth.authenticate_header(self.factory.get('/'))
        self.assertEqual(header, 'DeviceToken')
    
    def test_full_authentication_flow(self):
        """Test complete authentication flow"""
        request = self.factory.get('/', HTTP_AUTHORIZATION='DeviceToken test-token-abcdef123456')
        
        with patch('users.authentication.DeviceTokenAuthentication.get_client_ip') as mock_get_ip:
            mock_get_ip.return_value = "192.168.1.1"
            
            result = self.auth.authenticate(request)
            
            self.assertIsNotNone(result)
            user, token = result
            self.assertEqual(user, self.user)
            self.assertEqual(token, self.device_token)


class BiometricSessionAuthenticationTest(TestCase):
    """Test BiometricSessionAuthentication class"""
    
    def setUp(self):
        self.factory = RequestFactory()
        self.auth = BiometricSessionAuthentication()
        
        # Create test user and employee
        self.user = User.objects.create_user(
            username="testuser", email="test@test.com", password="pass123"
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Test", last_name="User",
            email="test@test.com",
            employment_type="full_time", role="employee"
        )
        
        # Create device token
        self.device_token = DeviceToken.objects.create(
            user=self.user,
            device_id="test-device-12345",
            token="test-token-abcdef123456",
            expires_at=timezone.now() + timedelta(days=30)
        )
        
        # Create biometric session
        self.biometric_session = BiometricSession.objects.create(
            device_token=self.device_token,
            started_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=1),
            confidence_score=0.95  # Add required field
        )
    
    def test_authenticate_no_device_token(self):
        """Test authentication with no device token"""
        request = self.factory.get('/')
        
        with patch('users.authentication.DeviceTokenAuthentication.authenticate') as mock_device_auth:
            mock_device_auth.return_value = None
            
            result = self.auth.authenticate(request)
            self.assertIsNone(result)
    
    def test_authenticate_no_biometric_session(self):
        """Test authentication with device token but no biometric session"""
        request = self.factory.get('/')
        
        # Delete biometric session
        self.biometric_session.delete()
        
        with patch('users.authentication.DeviceTokenAuthentication.authenticate') as mock_device_auth:
            mock_device_auth.return_value = (self.user, self.device_token)
            
            with self.assertRaises(AuthenticationFailed) as cm:
                self.auth.authenticate(request)
            self.assertEqual(str(cm.exception), "Biometric verification required.")
    
    def test_authenticate_expired_biometric_session(self):
        """Test authentication with expired biometric session"""
        request = self.factory.get('/')
        
        # Make session expired
        self.biometric_session.expires_at = timezone.now() - timedelta(hours=1)
        self.biometric_session.save()
        
        with patch('users.authentication.DeviceTokenAuthentication.authenticate') as mock_device_auth:
            mock_device_auth.return_value = (self.user, self.device_token)
            
            with self.assertRaises(AuthenticationFailed) as cm:
                self.auth.authenticate(request)
            self.assertIn("Biometric session expired", str(cm.exception))
    
    def test_authenticate_success(self):
        """Test successful biometric authentication"""
        request = self.factory.get('/')
        
        with patch('users.authentication.DeviceTokenAuthentication.authenticate') as mock_device_auth:
            mock_device_auth.return_value = (self.user, self.device_token)
            
            result = self.auth.authenticate(request)
            
            self.assertIsNotNone(result)
            user, auth_data = result
            self.assertEqual(user, self.user)
            self.assertEqual(auth_data['device_token'], self.device_token)
            self.assertEqual(auth_data['biometric_session'], self.biometric_session)
            self.assertTrue(hasattr(request, 'biometric_session'))


class HybridAuthenticationTest(TestCase):
    """Test HybridAuthentication class"""
    
    def setUp(self):
        self.factory = RequestFactory()
        self.auth = HybridAuthentication()
        
        # Create test user
        self.user = User.objects.create_user(
            username="testuser", email="test@test.com", password="pass123"
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Test", last_name="User",
            email="test@test.com",
            employment_type="full_time", role="employee"
        )
    
    def test_authenticate_no_header(self):
        """Test authentication with no authorization header"""
        request = self.factory.get('/')
        result = self.auth.authenticate(request)
        self.assertIsNone(result)
    
    def test_authenticate_invalid_format_one_part(self):
        """Test authentication with invalid format (one part)"""
        request = self.factory.get('/', HTTP_AUTHORIZATION='InvalidFormat')
        result = self.auth.authenticate(request)
        self.assertIsNone(result)
    
    def test_authenticate_invalid_format_too_many_parts(self):
        """Test authentication with too many parts"""
        request = self.factory.get('/', HTTP_AUTHORIZATION='Type token1 token2 extra')
        result = self.auth.authenticate(request)
        self.assertIsNone(result)
    
    def test_authenticate_unicode_error(self):
        """Test authentication with unicode decode error"""
        with patch('users.authentication.HybridAuthentication.get_authorization_header') as mock_get_header:
            mock_get_header.return_value = b'DeviceToken \xff\xfe'  # Return bytes, not list
            request = self.factory.get('/')
            
            result = self.auth.authenticate(request)
            self.assertIsNone(result)
    
    def test_authenticate_device_token_success(self):
        """Test successful device token authentication"""
        request = self.factory.get('/', HTTP_AUTHORIZATION='DeviceToken test-token-123')
        
        with patch('users.authentication.DeviceTokenAuthentication.authenticate') as mock_device_auth:
            mock_device_auth.return_value = (self.user, Mock())
            
            result = self.auth.authenticate(request)
            self.assertIsNotNone(result)
            self.assertEqual(result[0], self.user)
    
    def test_authenticate_device_token_failed(self):
        """Test failed device token authentication"""
        request = self.factory.get('/', HTTP_AUTHORIZATION='DeviceToken invalid-token')
        
        with patch('users.authentication.DeviceTokenAuthentication.authenticate') as mock_device_auth:
            mock_device_auth.side_effect = AuthenticationFailed("Invalid token")
            
            result = self.auth.authenticate(request)
            self.assertIsNone(result)
    
    def test_authenticate_device_token_none(self):
        """Test device token authentication returning None"""
        request = self.factory.get('/', HTTP_AUTHORIZATION='DeviceToken test-token-123')
        
        with patch('users.authentication.DeviceTokenAuthentication.authenticate') as mock_device_auth:
            mock_device_auth.return_value = None
            
            result = self.auth.authenticate(request)
            self.assertIsNone(result)
    
    def test_authenticate_legacy_token_success(self):
        """Test successful legacy token authentication"""
        request = self.factory.get('/', HTTP_AUTHORIZATION='Token legacy-token-123')
        
        with patch('rest_framework.authentication.TokenAuthentication.authenticate') as mock_token_auth:
            mock_token_auth.return_value = (self.user, Mock())
            
            result = self.auth.authenticate(request)
            self.assertIsNotNone(result)
            self.assertEqual(result[0], self.user)
            self.assertTrue(hasattr(request, 'is_legacy_auth'))
    
    def test_authenticate_legacy_token_failed(self):
        """Test failed legacy token authentication"""
        request = self.factory.get('/', HTTP_AUTHORIZATION='Token invalid-token')
        
        with patch('rest_framework.authentication.TokenAuthentication.authenticate') as mock_token_auth:
            mock_token_auth.side_effect = AuthenticationFailed("Invalid token")
            
            result = self.auth.authenticate(request)
            self.assertIsNone(result)
    
    def test_authenticate_legacy_token_none(self):
        """Test legacy token authentication returning None"""
        request = self.factory.get('/', HTTP_AUTHORIZATION='Token test-token-123')
        
        with patch('rest_framework.authentication.TokenAuthentication.authenticate') as mock_token_auth:
            mock_token_auth.return_value = None
            
            result = self.auth.authenticate(request)
            self.assertIsNone(result)
    
    def test_authenticate_unknown_type(self):
        """Test authentication with unknown auth type"""
        request = self.factory.get('/', HTTP_AUTHORIZATION='Unknown test-token-123')
        
        result = self.auth.authenticate(request)
        self.assertIsNone(result)
    
    def test_get_authorization_header_string(self):
        """Test get_authorization_header with string"""
        request = Mock()
        request.META = {'HTTP_AUTHORIZATION': 'DeviceToken abc123'}
        
        header = self.auth.get_authorization_header(request)
        self.assertEqual(header, b'DeviceToken abc123')
    
    def test_get_authorization_header_bytes(self):
        """Test get_authorization_header with bytes"""
        request = Mock()
        request.META = {'HTTP_AUTHORIZATION': b'DeviceToken abc123'}
        
        header = self.auth.get_authorization_header(request)
        self.assertEqual(header, b'DeviceToken abc123')
    
    def test_authenticate_header(self):
        """Test authenticate_header method"""
        header = self.auth.authenticate_header(self.factory.get('/'))
        self.assertEqual(header, 'DeviceToken')


class SecurityMiddlewareTest(TestCase):
    """Test SecurityMiddleware class"""
    
    def setUp(self):
        self.factory = RequestFactory()
        
        # Create mock get_response function
        def mock_get_response(request):
            from django.http import JsonResponse
            return JsonResponse({'status': 'ok'})
        
        self.middleware = SecurityMiddleware(mock_get_response)
        
        # Create test user
        self.user = User.objects.create_user(
            username="testuser", email="test@test.com", password="pass123"
        )
    
    def test_init(self):
        """Test middleware initialization"""
        self.assertEqual(self.middleware.max_attempts, 5)
        self.assertEqual(self.middleware.lockout_duration, 900)
        self.assertIsInstance(self.middleware.failed_attempts, dict)
    
    def test_get_client_ip_with_forwarded(self):
        """Test get_client_ip with X-Forwarded-For"""
        request = Mock()
        request.META = {'HTTP_X_FORWARDED_FOR': '10.0.0.1,192.168.1.1'}
        
        ip = self.middleware.get_client_ip(request)
        self.assertEqual(ip, '10.0.0.1')
    
    def test_get_client_ip_without_forwarded(self):
        """Test get_client_ip without X-Forwarded-For"""
        request = Mock()
        request.META = {'REMOTE_ADDR': '192.168.1.100'}
        
        ip = self.middleware.get_client_ip(request)
        self.assertEqual(ip, '192.168.1.100')
    
    def test_is_ip_locked_out_no_attempts(self):
        """Test is_ip_locked_out with no previous attempts"""
        result = self.middleware.is_ip_locked_out("192.168.1.1")
        self.assertFalse(result)
    
    def test_is_ip_locked_out_under_threshold(self):
        """Test is_ip_locked_out under max attempts threshold"""
        ip = "192.168.1.1"
        self.middleware.failed_attempts[ip] = (3, timezone.now())
        
        result = self.middleware.is_ip_locked_out(ip)
        self.assertFalse(result)
    
    def test_is_ip_locked_out_over_threshold(self):
        """Test is_ip_locked_out over max attempts threshold"""
        ip = "192.168.1.1"
        self.middleware.failed_attempts[ip] = (6, timezone.now())
        
        result = self.middleware.is_ip_locked_out(ip)
        self.assertTrue(result)
    
    def test_is_ip_locked_out_expired_lockout(self):
        """Test is_ip_locked_out with expired lockout period"""
        ip = "192.168.1.1"
        old_time = timezone.now() - timedelta(seconds=self.middleware.lockout_duration + 100)
        self.middleware.failed_attempts[ip] = (6, old_time)
        
        result = self.middleware.is_ip_locked_out(ip)
        self.assertFalse(result)
        
        # Check that entry was removed
        self.assertNotIn(ip, self.middleware.failed_attempts)
    
    def test_record_failed_attempt_new_ip(self):
        """Test record_failed_attempt for new IP"""
        ip = "192.168.1.1"
        self.middleware.record_failed_attempt(ip)
        
        self.assertIn(ip, self.middleware.failed_attempts)
        attempts, timestamp = self.middleware.failed_attempts[ip]
        self.assertEqual(attempts, 1)
    
    def test_record_failed_attempt_existing_ip(self):
        """Test record_failed_attempt for existing IP"""
        ip = "192.168.1.1"
        self.middleware.failed_attempts[ip] = (2, timezone.now() - timedelta(minutes=1))
        
        self.middleware.record_failed_attempt(ip)
        
        attempts, timestamp = self.middleware.failed_attempts[ip]
        self.assertEqual(attempts, 3)
    
    def test_log_successful_auth_with_device_token(self):
        """Test log_successful_auth with device token"""
        request = Mock()
        request.user = self.user
        request.device_token = Mock()
        request.device_token.device_id = "test-device-12345"
        request.device_token.biometric_verified = True
        
        ip = "192.168.1.1"
        self.middleware.failed_attempts[ip] = (3, timezone.now())
        
        self.middleware.log_successful_auth(request, ip)
        
        # Should clear failed attempts
        self.assertNotIn(ip, self.middleware.failed_attempts)
    
    def test_log_successful_auth_no_device_token(self):
        """Test log_successful_auth without device token"""
        # Create real request object without device_token attribute
        request = self.factory.get('/')
        request.user = self.user
        # device_token attribute is not set, so getattr should return None
        
        # Should not raise exception when device_token is None
        self.middleware.log_successful_auth(request, "192.168.1.1")
    
    def test_call_ip_locked_out(self):
        """Test middleware __call__ with locked out IP"""
        ip = "192.168.1.1"
        self.middleware.failed_attempts[ip] = (6, timezone.now())
        
        request = self.factory.get('/', REMOTE_ADDR=ip)
        response = self.middleware(request)
        
        self.assertEqual(response.status_code, 429)
        data = json.loads(response.content)
        self.assertEqual(data['code'], 'IP_LOCKED_OUT')
    
    def test_call_successful_with_auth(self):
        """Test middleware __call__ with successful authenticated request"""
        request = self.factory.get('/', REMOTE_ADDR="192.168.1.1")
        request.user = self.user
        request.device_token = Mock()
        request.device_token.device_id = "test-device-12345"
        request.device_token.biometric_verified = True
        
        response = self.middleware(request)
        
        self.assertEqual(response.status_code, 200)
    
    def test_call_unauthenticated(self):
        """Test middleware __call__ with unauthenticated request"""
        request = self.factory.get('/', REMOTE_ADDR="192.168.1.1")
        request.user = AnonymousUser()
        
        response = self.middleware(request)
        
        self.assertEqual(response.status_code, 200)


class AuthenticationIntegrationTest(TestCase):
    """Integration tests for authentication components"""
    
    def setUp(self):
        self.factory = RequestFactory()
        
        # Create test user and employee
        self.user = User.objects.create_user(
            username="testuser", email="test@test.com", password="pass123"
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Test", last_name="User",
            email="test@test.com",
            employment_type="full_time", role="employee"
        )
    
    def test_full_device_token_flow(self):
        """Test complete device token authentication flow"""
        # Create device token
        device_token = DeviceToken.objects.create(
            user=self.user,
            device_id="integration-test-device",
            token="integration-test-token",
            expires_at=timezone.now() + timedelta(days=30)
        )
        
        # Test with DeviceTokenAuthentication
        auth = DeviceTokenAuthentication()
        request = self.factory.get('/', HTTP_AUTHORIZATION='DeviceToken integration-test-token')
        
        result = auth.authenticate(request)
        
        self.assertIsNotNone(result)
        user, token = result
        self.assertEqual(user, self.user)
        self.assertEqual(token, device_token)
    
    def test_hybrid_auth_fallback_to_legacy(self):
        """Test HybridAuthentication falling back to legacy token"""
        # Create legacy token
        from rest_framework.authtoken.models import Token
        legacy_token = Token.objects.create(user=self.user)
        
        # Test with HybridAuthentication
        auth = HybridAuthentication()
        request = self.factory.get('/', HTTP_AUTHORIZATION=f'Token {legacy_token.key}')
        
        result = auth.authenticate(request)
        
        self.assertIsNotNone(result)
        user, token = result
        self.assertEqual(user, self.user)
        self.assertTrue(hasattr(request, 'is_legacy_auth'))
    
    def test_biometric_session_complete_flow(self):
        """Test complete biometric session authentication"""
        # Create device token and biometric session
        device_token = DeviceToken.objects.create(
            user=self.user,
            device_id="biometric-test-device",
            token="biometric-test-token",
            expires_at=timezone.now() + timedelta(days=30)
        )
        
        biometric_session = BiometricSession.objects.create(
            device_token=device_token,
            started_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=1),
            confidence_score=0.95  # Add required field
        )
        
        # Test biometric authentication
        auth = BiometricSessionAuthentication()
        request = self.factory.get('/', HTTP_AUTHORIZATION='DeviceToken biometric-test-token')
        
        result = auth.authenticate(request)
        
        self.assertIsNotNone(result)
        user, auth_data = result
        self.assertEqual(user, self.user)
        self.assertEqual(auth_data['device_token'], device_token)
        self.assertEqual(auth_data['biometric_session'], biometric_session)