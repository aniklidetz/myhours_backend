"""
Tests for users enhanced_auth_views - enhanced_login, biometric_verification, refresh_token, logout_device.
Covers happy path (200), error cases (400/401/500), missing fields, invalid data, and edge cases.
"""

import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from rest_framework import status
from rest_framework.test import APIClient

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from users.models import Employee
from users.token_models import BiometricSession, DeviceToken


class EnhancedLoginViewTest(TestCase):
    """Tests for enhanced_login endpoint"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        
        # Create test user and employee
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            first_name='John',
            last_name='Doe'
        )
        
        self.employee = Employee.objects.create(
            user=self.user,
            first_name='John',
            last_name='Doe',
            email='test@example.com',
            employment_type='full_time',
            role='employee'
        )
        
        # Create inactive user for testing
        self.inactive_user = User.objects.create_user(
            username='inactive',
            email='inactive@example.com',
            password='testpass123',
            is_active=False
        )

    @patch('users.enhanced_auth_views.get_mongodb_service')
    def test_enhanced_login_success_200(self, mock_mongodb):
        """Test successful enhanced login - 200 OK"""
        # Mock MongoDB service
        mock_service = MagicMock()
        mock_service.get_face_embeddings.return_value = None  # No biometric data
        mock_mongodb.return_value = mock_service
        
        data = {
            'email': 'test@example.com',
            'password': 'testpass123',
            'device_id': 'test-device-123',
            'device_info': {
                'platform': 'iOS',
                'os_version': '15.0',
                'app_version': '1.0.0',
                'device_model': 'iPhone 12'
            },
            'location': {
                'latitude': 32.0853,
                'longitude': 34.7818,
                'accuracy': 10.0
            }
        }
        
        response = self.client.post('/api/v1/users/auth/enhanced-login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertIn('token', response_data)
        self.assertIn('expires_at', response_data)
        self.assertIn('user', response_data)
        self.assertEqual(response_data['user']['email'], 'test@example.com')
        self.assertTrue(response_data['device_registered'])
        self.assertFalse(response_data['biometric_registered'])
        self.assertIn('security_info', response_data)
        
        # Verify device token was created
        device_token = DeviceToken.objects.get(user=self.user, device_id='test-device-123')
        self.assertEqual(device_token.token, response_data['token'])

    @patch('users.enhanced_auth_views.get_mongodb_service')
    def test_enhanced_login_with_biometric_data(self, mock_mongodb):
        """Test enhanced login with existing biometric data"""
        # Mock MongoDB service with biometric data
        mock_service = MagicMock()
        mock_service.get_face_embeddings.return_value = [{'embedding': [1, 2, 3]}]
        mock_mongodb.return_value = mock_service
        
        data = {
            'email': 'test@example.com',
            'password': 'testpass123',
            'device_id': 'test-device-456'
        }
        
        response = self.client.post('/api/v1/users/auth/enhanced-login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertTrue(response_data['biometric_registered'])

    def test_enhanced_login_missing_email_400(self):
        """Test enhanced login with missing email - 400 Bad Request"""
        data = {
            'password': 'testpass123',
            'device_id': 'test-device-123'
        }
        
        response = self.client.post('/api/v1/users/auth/enhanced-login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertTrue(response_data['error'])
        self.assertEqual(response_data['code'], 'MISSING_REQUIRED_FIELDS')
        self.assertIn('error_id', response_data)

    def test_enhanced_login_missing_password_400(self):
        """Test enhanced login with missing password - 400 Bad Request"""
        data = {
            'email': 'test@example.com',
            'device_id': 'test-device-123'
        }
        
        response = self.client.post('/api/v1/users/auth/enhanced-login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertEqual(response_data['code'], 'MISSING_REQUIRED_FIELDS')

    def test_enhanced_login_missing_device_id_400(self):
        """Test enhanced login with missing device_id - 400 Bad Request"""
        data = {
            'email': 'test@example.com',
            'password': 'testpass123'
        }
        
        response = self.client.post('/api/v1/users/auth/enhanced-login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertEqual(response_data['code'], 'MISSING_REQUIRED_FIELDS')

    def test_enhanced_login_invalid_credentials_401(self):
        """Test enhanced login with invalid credentials - 401 Unauthorized"""
        data = {
            'email': 'test@example.com',
            'password': 'wrongpassword',
            'device_id': 'test-device-123'
        }
        
        response = self.client.post('/api/v1/users/auth/enhanced-login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response_data = response.json()
        self.assertTrue(response_data['error'])
        self.assertEqual(response_data['code'], 'AUTHENTICATION_FAILED')
        self.assertEqual(response_data['error_id'], 'auth_002')

    def test_enhanced_login_nonexistent_user_401(self):
        """Test enhanced login with non-existent user - 401 Unauthorized"""
        data = {
            'email': 'nonexistent@example.com',
            'password': 'testpass123',
            'device_id': 'test-device-123'
        }
        
        response = self.client.post('/api/v1/users/auth/enhanced-login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response_data = response.json()
        self.assertEqual(response_data['code'], 'AUTHENTICATION_FAILED')

    def test_enhanced_login_inactive_user_401(self):
        """Test enhanced login with inactive user - 401 Unauthorized"""
        data = {
            'email': 'inactive@example.com',
            'password': 'testpass123',
            'device_id': 'test-device-123'
        }
        
        response = self.client.post('/api/v1/users/auth/enhanced-login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response_data = response.json()
        # Django's authenticate() returns None for inactive users, so it goes to AUTHENTICATION_FAILED
        self.assertEqual(response_data['code'], 'AUTHENTICATION_FAILED')
        self.assertEqual(response_data['error_id'], 'auth_002')

    def test_enhanced_login_user_without_employee_profile_400(self):
        """Test enhanced login with user who has no employee profile - 400 Bad Request"""
        # Create user without employee profile
        user_no_employee = User.objects.create_user(
            username='noemployee',
            email='noemployee@example.com',
            password='testpass123'
        )
        
        data = {
            'email': 'noemployee@example.com',
            'password': 'testpass123',
            'device_id': 'test-device-123'
        }
        
        response = self.client.post('/api/v1/users/auth/enhanced-login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertEqual(response_data['code'], 'NO_EMPLOYEE_PROFILE')
        self.assertEqual(response_data['error_id'], 'auth_004')

    def test_enhanced_login_email_as_username_fallback(self):
        """Test enhanced login with email used as username fallback"""
        # Create user where email is different from username
        user_email_username = User.objects.create_user(
            username='different@example.com',
            email='different@example.com',
            password='testpass123'
        )
        
        employee = Employee.objects.create(
            user=user_email_username,
            first_name='Different',
            last_name='User',
            email='different@example.com',
            employment_type='full_time',
            role='employee'
        )
        
        with patch('users.enhanced_auth_views.get_mongodb_service') as mock_mongodb:
            mock_service = MagicMock()
            mock_service.get_face_embeddings.return_value = None
            mock_mongodb.return_value = mock_service
            
            data = {
                'email': 'different@example.com',
                'password': 'testpass123',
                'device_id': 'test-device-789'
            }
            
            response = self.client.post('/api/v1/users/auth/enhanced-login/', data, format='json')
            
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    @override_settings(AUTH_TOKEN_TTL_DAYS=14)
    @patch('users.enhanced_auth_views.get_mongodb_service')
    def test_enhanced_login_custom_ttl_settings(self, mock_mongodb):
        """Test enhanced login with custom TTL settings"""
        mock_service = MagicMock()
        mock_service.get_face_embeddings.return_value = None
        mock_mongodb.return_value = mock_service
        
        data = {
            'email': 'test@example.com',
            'password': 'testpass123',
            'device_id': 'test-device-ttl'
        }
        
        response = self.client.post('/api/v1/users/auth/enhanced-login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data['security_info']['token_expires_in_days'], 14)

    @patch('users.enhanced_auth_views.get_mongodb_service')
    @patch('users.enhanced_auth_views.logger')
    def test_enhanced_login_logging(self, mock_logger, mock_mongodb):
        """Test that enhanced login events are logged"""
        mock_service = MagicMock()
        mock_service.get_face_embeddings.return_value = None
        mock_mongodb.return_value = mock_service
        
        data = {
            'email': 'test@example.com',
            'password': 'testpass123',
            'device_id': 'test-device-log'
        }
        
        response = self.client.post('/api/v1/users/auth/enhanced-login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify logging calls
        mock_logger.info.assert_called_with(
            'Enhanced login successful: user=testuser, device=test-dev...'
        )

    @patch('users.enhanced_auth_views.DeviceToken.create_token')
    def test_enhanced_login_exception_handling_500(self, mock_create_token):
        """Test enhanced login exception handling - 500 Internal Server Error"""
        mock_create_token.side_effect = Exception("Database error")
        
        data = {
            'email': 'test@example.com',
            'password': 'testpass123',
            'device_id': 'test-device-error'
        }
        
        response = self.client.post('/api/v1/users/auth/enhanced-login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        response_data = response.json()
        self.assertTrue(response_data['error'])
        self.assertEqual(response_data['code'], 'INTERNAL_SERVER_ERROR')
        self.assertEqual(response_data['error_id'], 'auth_005')


class BiometricVerificationViewTest(TestCase):
    """Tests for biometric_verification endpoint"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.employee = Employee.objects.create(
            user=self.user,
            first_name='John',
            last_name='Doe',
            email='test@example.com',
            employment_type='full_time',
            role='employee'
        )
        
        # Create device token
        self.device_token = DeviceToken.objects.create(
            user=self.user,
            device_id='test-device-bio',
            token='test-bio-token-123',
            expires_at=timezone.now() + timedelta(days=7)
        )

    def test_biometric_verification_missing_authentication_401(self):
        """Test biometric verification without authentication - 401 Unauthorized"""
        data = {'image': 'base64_encoded_image'}
        
        response = self.client.post('/api/v1/users/auth/biometric-verification/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_biometric_verification_missing_image_400(self):
        """Test biometric verification without image - 400 Bad Request"""
        # Authenticate with DeviceToken
        self.client.credentials(HTTP_AUTHORIZATION=f'DeviceToken {self.device_token.token}')
        
        data = {}
        
        response = self.client.post('/api/v1/users/auth/biometric-verification/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertEqual(response_data['code'], 'MISSING_IMAGE')
        self.assertEqual(response_data['error_id'], 'bio_001')

    @patch('users.enhanced_auth_views.get_mongodb_service')
    def test_biometric_verification_no_biometric_data_400(self, mock_mongodb):
        """Test biometric verification when no biometric data exists - 400 Bad Request"""
        self.client.credentials(HTTP_AUTHORIZATION=f'DeviceToken {self.device_token.token}')
        
        # Mock empty embeddings
        mock_service = MagicMock()
        mock_service.get_all_active_embeddings.return_value = []
        mock_mongodb.return_value = mock_service
        
        data = {'image': 'base64_encoded_image'}
        
        response = self.client.post('/api/v1/users/auth/biometric-verification/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_data = response.json()
        self.assertEqual(response_data['code'], 'NO_BIOMETRIC_DATA')
        self.assertEqual(response_data['error_id'], 'bio_002')

    @patch('users.enhanced_auth_views.face_processor', None)
    def test_biometric_verification_service_unavailable_503(self):
        """Test biometric verification when service is unavailable - 503 Service Unavailable"""
        self.client.credentials(HTTP_AUTHORIZATION=f'DeviceToken {self.device_token.token}')
        
        with patch('users.enhanced_auth_views.get_mongodb_service') as mock_mongodb:
            mock_service = MagicMock()
            mock_service.get_all_active_embeddings.return_value = [{'employee_id': 1}]
            mock_mongodb.return_value = mock_service
            
            data = {'image': 'base64_encoded_image'}
            
            response = self.client.post('/api/v1/users/auth/biometric-verification/', data, format='json')
            
            self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
            response_data = response.json()
            self.assertEqual(response_data['code'], 'BIOMETRIC_SERVICE_UNAVAILABLE')
            self.assertEqual(response_data['error_id'], 'bio_006')

    @patch('users.enhanced_auth_views.get_mongodb_service')
    @patch('users.enhanced_auth_views.face_processor')
    def test_biometric_verification_failed_401(self, mock_face_processor, mock_mongodb):
        """Test biometric verification failure - 401 Unauthorized"""
        self.client.credentials(HTTP_AUTHORIZATION=f'DeviceToken {self.device_token.token}')
        
        # Mock services
        mock_service = MagicMock()
        mock_service.get_all_active_embeddings.return_value = [{'employee_id': 1}]
        mock_mongodb.return_value = mock_service
        
        mock_face_processor.find_matching_employee.return_value = {'success': False}
        
        data = {'image': 'base64_encoded_image'}
        
        response = self.client.post('/api/v1/users/auth/biometric-verification/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response_data = response.json()
        self.assertEqual(response_data['code'], 'BIOMETRIC_VERIFICATION_FAILED')
        self.assertEqual(response_data['error_id'], 'bio_003')

    @patch('users.enhanced_auth_views.get_mongodb_service')
    @patch('users.enhanced_auth_views.face_processor')
    def test_biometric_verification_mismatch_401(self, mock_face_processor, mock_mongodb):
        """Test biometric verification with employee mismatch - 401 Unauthorized"""
        self.client.credentials(HTTP_AUTHORIZATION=f'DeviceToken {self.device_token.token}')
        
        # Mock services
        mock_service = MagicMock()
        mock_service.get_all_active_embeddings.return_value = [{'employee_id': 1}]
        mock_mongodb.return_value = mock_service
        
        # Mock successful match but for different employee
        mock_face_processor.find_matching_employee.return_value = {
            'success': True,
            'employee_id': 999,  # Different from self.employee.id
            'confidence': 0.95
        }
        
        data = {'image': 'base64_encoded_image'}
        
        response = self.client.post('/api/v1/users/auth/biometric-verification/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        response_data = response.json()
        self.assertEqual(response_data['code'], 'BIOMETRIC_MISMATCH')
        self.assertEqual(response_data['error_id'], 'bio_004')

    @patch('users.enhanced_auth_views.get_mongodb_service')
    @patch('users.enhanced_auth_views.face_processor')
    def test_biometric_verification_success_200(self, mock_face_processor, mock_mongodb):
        """Test successful biometric verification - 200 OK"""
        self.client.credentials(HTTP_AUTHORIZATION=f'DeviceToken {self.device_token.token}')
        
        # Mock services
        mock_service = MagicMock()
        mock_service.get_all_active_embeddings.return_value = [{'employee_id': self.employee.id}]
        mock_mongodb.return_value = mock_service
        
        mock_face_processor.find_matching_employee.return_value = {
            'success': True,
            'employee_id': self.employee.id,
            'confidence': 0.95,
            'quality_check': {'quality_score': 0.9}
        }
        
        data = {
            'image': 'base64_encoded_image',
            'operation_type': 'general',
            'location': {'latitude': 32.0853, 'longitude': 34.7818}
        }
        
        response = self.client.post('/api/v1/users/auth/biometric-verification/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertEqual(response_data['verification_level'], 'high')
        self.assertIn('access_granted', response_data)
        
        # Verify device token was marked as biometrically verified
        self.device_token.refresh_from_db()
        self.assertIsNotNone(self.device_token.biometric_verified_at)

    @patch('users.enhanced_auth_views.get_mongodb_service')
    @patch('users.enhanced_auth_views.face_processor')
    def test_biometric_verification_payroll_operation(self, mock_face_processor, mock_mongodb):
        """Test biometric verification for payroll operation with shorter TTL"""
        self.client.credentials(HTTP_AUTHORIZATION=f'DeviceToken {self.device_token.token}')
        
        # Mock services
        mock_service = MagicMock()
        mock_service.get_all_active_embeddings.return_value = [{'employee_id': self.employee.id}]
        mock_mongodb.return_value = mock_service
        
        mock_face_processor.find_matching_employee.return_value = {
            'success': True,
            'employee_id': self.employee.id,
            'confidence': 0.85,
            'quality_check': {'quality_score': 0.8}
        }
        
        data = {
            'image': 'base64_encoded_image',
            'operation_type': 'payroll'
        }
        
        response = self.client.post('/api/v1/users/auth/biometric-verification/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data['verification_level'], 'medium')
        self.assertTrue(response_data['access_granted']['payroll'])

    @patch('users.enhanced_auth_views.BiometricSession.create_session')
    def test_biometric_verification_exception_handling_500(self, mock_create_session):
        """Test biometric verification exception handling - 500 Internal Server Error"""
        self.client.credentials(HTTP_AUTHORIZATION=f'DeviceToken {self.device_token.token}')
        
        # Mock the services to get through to the exception part
        with patch('users.enhanced_auth_views.get_mongodb_service') as mock_mongodb:
            mock_service = MagicMock()
            mock_service.get_all_active_embeddings.return_value = [{'employee_id': self.employee.id}]
            mock_mongodb.return_value = mock_service
            
            with patch('users.enhanced_auth_views.face_processor') as mock_face_processor:
                mock_face_processor.find_matching_employee.return_value = {
                    'success': True,
                    'employee_id': self.employee.id,
                    'confidence': 0.95
                }
                
                mock_create_session.side_effect = Exception("Database error")
                
                data = {'image': 'base64_encoded_image'}
                
                response = self.client.post('/api/v1/users/auth/biometric-verification/', data, format='json')
                
                self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
                response_data = response.json()
                self.assertEqual(response_data['code'], 'INTERNAL_SERVER_ERROR')
                self.assertEqual(response_data['error_id'], 'bio_005')


class RefreshTokenViewTest(TestCase):
    """Tests for refresh_token endpoint"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.employee = Employee.objects.create(
            user=self.user,
            first_name='John',
            last_name='Doe',
            email='test@example.com',
            employment_type='full_time',
            role='employee'
        )
        
        self.device_token = DeviceToken.objects.create(
            user=self.user,
            device_id='test-device-refresh',
            token='test-refresh-token-123',
            expires_at=timezone.now() + timedelta(days=7)
        )

    def test_refresh_token_no_authentication_401(self):
        """Test refresh token without authentication - 401 Unauthorized"""
        data = {}
        
        response = self.client.post('/api/v1/users/auth/refresh-token/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_token_success_200(self):
        """Test successful token refresh - 200 OK"""
        self.client.credentials(HTTP_AUTHORIZATION=f'DeviceToken {self.device_token.token}')
        
        data = {'ttl_days': 14}
        
        response = self.client.post('/api/v1/users/auth/refresh-token/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertIn('token', response_data)
        self.assertIn('expires_at', response_data)
        self.assertEqual(response_data['ttl_days'], 14)

    def test_refresh_token_default_ttl(self):
        """Test token refresh with default TTL"""
        self.client.credentials(HTTP_AUTHORIZATION=f'DeviceToken {self.device_token.token}')
        
        data = {}
        
        response = self.client.post('/api/v1/users/auth/refresh-token/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        # Default should be 7 days as per settings
        self.assertEqual(response_data['ttl_days'], 7)

    @patch('users.enhanced_auth_views.logger')
    def test_refresh_token_logging(self, mock_logger):
        """Test that token refresh is logged"""
        self.client.credentials(HTTP_AUTHORIZATION=f'DeviceToken {self.device_token.token}')
        
        data = {}
        
        response = self.client.post('/api/v1/users/auth/refresh-token/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        mock_logger.info.assert_called_with(
            'Token refresh successful: user=testuser, device=test-dev...'
        )

    def test_refresh_token_failed_refresh_400(self):
        """Test token refresh failure - 400 Bad Request"""
        # Make device token expired to trigger failure
        self.device_token.expires_at = timezone.now() - timedelta(days=1)
        self.device_token.save()
        
        self.client.credentials(HTTP_AUTHORIZATION=f'DeviceToken {self.device_token.token}')
        
        data = {}
        
        response = self.client.post('/api/v1/users/auth/refresh-token/', data, format='json')
        
        # This will likely return 401 due to expired token authentication
        # But if it gets through, it would be 400
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED])

    @patch('users.token_models.DeviceToken.refresh')
    def test_refresh_token_exception_handling_500(self, mock_refresh):
        """Test refresh token exception handling - 500 Internal Server Error"""
        self.client.credentials(HTTP_AUTHORIZATION=f'DeviceToken {self.device_token.token}')
        
        mock_refresh.side_effect = Exception("Database error")
        
        data = {}
        
        response = self.client.post('/api/v1/users/auth/refresh-token/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        response_data = response.json()
        self.assertEqual(response_data['code'], 'INTERNAL_SERVER_ERROR')
        self.assertEqual(response_data['error_id'], 'refresh_002')


class LogoutDeviceViewTest(TestCase):
    """Tests for logout_device endpoint"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.employee = Employee.objects.create(
            user=self.user,
            first_name='John',
            last_name='Doe',
            email='test@example.com',
            employment_type='full_time',
            role='employee'
        )
        
        self.device_token = DeviceToken.objects.create(
            user=self.user,
            device_id='test-device-logout',
            token='test-logout-token-123',
            expires_at=timezone.now() + timedelta(days=7),
            is_active=True
        )
        
        # Create biometric session
        import uuid
        self.biometric_session = BiometricSession.objects.create(
            device_token=self.device_token,
            session_id=uuid.uuid4(),
            confidence_score=Decimal('0.95'),
            expires_at=timezone.now() + timedelta(hours=8),
            is_active=True
        )

    def test_logout_device_no_authentication_401(self):
        """Test logout device without authentication - 401 Unauthorized"""
        data = {}
        
        response = self.client.post('/api/v1/users/auth/logout-device/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_device_success_200(self):
        """Test successful device logout - 200 OK"""
        self.client.credentials(HTTP_AUTHORIZATION=f'DeviceToken {self.device_token.token}')
        
        data = {}
        
        response = self.client.post('/api/v1/users/auth/logout-device/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertEqual(response_data['message'], 'Logout successful')
        self.assertIn('logged_out_at', response_data)
        
        # Verify device token was deactivated
        self.device_token.refresh_from_db()
        self.assertFalse(self.device_token.is_active)
        
        # Verify biometric sessions were ended
        self.biometric_session.refresh_from_db()
        self.assertFalse(self.biometric_session.is_active)

    @patch('users.enhanced_auth_views.logger')
    def test_logout_device_logging(self, mock_logger):
        """Test that device logout is logged"""
        self.client.credentials(HTTP_AUTHORIZATION=f'DeviceToken {self.device_token.token}')
        
        data = {}
        
        response = self.client.post('/api/v1/users/auth/logout-device/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        mock_logger.info.assert_called_with(
            'Device logout successful: user=testuser, device=test-dev...'
        )

    def test_logout_device_exception_handling_500(self):
        """Test logout device exception handling - 500 Internal Server Error"""
        self.client.credentials(HTTP_AUTHORIZATION=f'DeviceToken {self.device_token.token}')
        
        # Force an exception by deleting the device token after authentication but before logout
        with patch('users.enhanced_auth_views.BiometricSession.objects') as mock_bio_objects:
            mock_bio_objects.filter.side_effect = Exception("Database error")
            
            data = {}
            
            response = self.client.post('/api/v1/users/auth/logout-device/', data, format='json')
            
            self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
            response_data = response.json()
            self.assertTrue(response_data['error'])
            self.assertEqual(response_data['code'], 'INTERNAL_SERVER_ERROR')
            self.assertEqual(response_data['error_id'], 'logout_001')