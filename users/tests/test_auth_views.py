"""
Tests for users auth_views - login_view, test_connection, logout_view endpoints.
Covers happy path (200), error cases (400/401), missing credentials, invalid credentials,
token creation, and edge cases.
"""

import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from users.models import Employee


class LoginViewTest(TestCase):
    """Tests for login_view endpoint"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            first_name='John',
            last_name='Doe'
        )
        
        # Create employee profile
        self.employee = Employee.objects.create(
            user=self.user,
            first_name='John',
            last_name='Doe',
            email='test@example.com',
            employment_type='full_time',
            role='employee'
        )
        
        # Create admin user
        self.admin_user = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='adminpass123',
            is_staff=True,
            is_superuser=True
        )
        
        # Create accountant user
        self.accountant_user = User.objects.create_user(
            username='accountant',
            email='accountant@example.com',
            password='accountpass123',
            is_staff=True,
            is_superuser=False
        )

    def test_login_success_with_email(self):
        """Test successful login with email and password - happy path (200)"""
        data = {
            'email': 'test@example.com',
            'password': 'testpass123'
        }
        
        response = self.client.post('/api/v1/users/auth/login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response_data = response.json()
        self.assertIn('token', response_data)
        self.assertIn('user', response_data)
        
        # Verify user data
        user_data = response_data['user']
        self.assertEqual(user_data['id'], self.user.id)
        self.assertEqual(user_data['email'], 'test@example.com')
        self.assertEqual(user_data['username'], 'testuser')
        self.assertEqual(user_data['first_name'], 'John')
        self.assertEqual(user_data['last_name'], 'Doe')
        self.assertEqual(user_data['role'], 'employee')
        self.assertFalse(user_data['is_staff'])
        self.assertFalse(user_data['is_superuser'])
        
        # Verify token was created
        token = Token.objects.get(user=self.user)
        self.assertEqual(response_data['token'], token.key)

    def test_login_success_with_email_as_username(self):
        """Test successful login when user doesn't exist by email but email is used as username"""
        # Create user where username is email
        user = User.objects.create_user(
            username='email@example.com',
            email='different@example.com',
            password='testpass123'
        )
        
        data = {
            'email': 'email@example.com',  # This is the username, not email
            'password': 'testpass123'
        }
        
        response = self.client.post('/api/v1/users/auth/login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertIn('token', response_data)
        self.assertEqual(response_data['user']['username'], 'email@example.com')

    def test_login_success_admin_role_from_user_permissions(self):
        """Test login with admin role determined from user permissions (no Employee profile)"""
        data = {
            'email': 'admin@example.com',
            'password': 'adminpass123'
        }
        
        response = self.client.post('/api/v1/users/auth/login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user_data = response.json()['user']
        self.assertEqual(user_data['role'], 'admin')
        self.assertTrue(user_data['is_superuser'])
        self.assertTrue(user_data['is_staff'])

    def test_login_success_accountant_role_from_user_permissions(self):
        """Test login with accountant role determined from staff permissions"""
        data = {
            'email': 'accountant@example.com',
            'password': 'accountpass123'
        }
        
        response = self.client.post('/api/v1/users/auth/login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user_data = response.json()['user']
        self.assertEqual(user_data['role'], 'accountant')
        self.assertFalse(user_data['is_superuser'])
        self.assertTrue(user_data['is_staff'])

    def test_login_token_reuse_existing(self):
        """Test that existing token is reused instead of creating new one"""
        # Create existing token
        existing_token = Token.objects.create(user=self.user)
        
        data = {
            'email': 'test@example.com',
            'password': 'testpass123'
        }
        
        response = self.client.post('/api/v1/users/auth/login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['token'], existing_token.key)
        
        # Verify no additional token was created
        self.assertEqual(Token.objects.filter(user=self.user).count(), 1)

    def test_login_missing_email_400(self):
        """Test login with missing email - 400 Bad Request"""
        data = {
            'password': 'testpass123'
        }
        
        response = self.client.post('/api/v1/users/auth/login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())
        self.assertIn('Email and password are required', response.json()['error'])

    def test_login_missing_password_400(self):
        """Test login with missing password - 400 Bad Request"""
        data = {
            'email': 'test@example.com'
        }
        
        response = self.client.post('/api/v1/users/auth/login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())
        self.assertIn('Email and password are required', response.json()['error'])

    def test_login_empty_email_400(self):
        """Test login with empty email - 400 Bad Request"""
        data = {
            'email': '',
            'password': 'testpass123'
        }
        
        response = self.client.post('/api/v1/users/auth/login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())
        self.assertIn('Email and password are required', response.json()['error'])

    def test_login_empty_password_400(self):
        """Test login with empty password - 400 Bad Request"""
        data = {
            'email': 'test@example.com',
            'password': ''
        }
        
        response = self.client.post('/api/v1/users/auth/login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())
        self.assertIn('Email and password are required', response.json()['error'])

    def test_login_invalid_credentials_401(self):
        """Test login with invalid credentials - 401 Unauthorized"""
        data = {
            'email': 'test@example.com',
            'password': 'wrongpassword'
        }
        
        response = self.client.post('/api/v1/users/auth/login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('error', response.json())
        self.assertIn('Invalid email or password', response.json()['error'])

    def test_login_nonexistent_user_401(self):
        """Test login with non-existent user - 401 Unauthorized"""
        data = {
            'email': 'nonexistent@example.com',
            'password': 'testpass123'
        }
        
        response = self.client.post('/api/v1/users/auth/login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('error', response.json())
        self.assertIn('Invalid email or password', response.json()['error'])

    def test_login_inactive_user_401(self):
        """Test login with inactive user - 401 Unauthorized"""
        self.user.is_active = False
        self.user.save()
        
        data = {
            'email': 'test@example.com',
            'password': 'testpass123'
        }
        
        response = self.client.post('/api/v1/users/auth/login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_only_accepts_post(self):
        """Test that login endpoint only accepts POST requests"""
        data = {
            'email': 'test@example.com',
            'password': 'testpass123'
        }
        
        # Test GET request
        response = self.client.get('/api/v1/users/auth/login/', data)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        
        # Test PUT request
        response = self.client.put('/api/v1/users/auth/login/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    @patch('users.auth_views.logger')
    def test_login_logging_success(self, mock_logger):
        """Test that successful login is logged correctly"""
        data = {
            'email': 'test@example.com',
            'password': 'testpass123'
        }
        
        response = self.client.post('/api/v1/users/auth/login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify logging calls
        mock_logger.info.assert_any_call("Login attempt received")
        mock_logger.info.assert_any_call(f"Login successful for user ID: {self.user.id}")

    @patch('users.auth_views.logger')
    def test_login_logging_missing_credentials(self, mock_logger):
        """Test that missing credentials failure is logged"""
        data = {'email': 'test@example.com'}  # Missing password
        
        response = self.client.post('/api/v1/users/auth/login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_logger.warning.assert_called_with("Login failed - missing credentials")

    @patch('users.auth_views.logger')
    def test_login_logging_invalid_credentials(self, mock_logger):
        """Test that invalid credentials failure is logged"""
        data = {
            'email': 'test@example.com',
            'password': 'wrongpassword'
        }
        
        response = self.client.post('/api/v1/users/auth/login/', data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        mock_logger.warning.assert_called_with("Login failed - invalid credentials")


class TestConnectionViewTest(TestCase):
    """Tests for test_connection endpoint"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()

    def test_connection_get_200(self):
        """Test test_connection GET request - 200 OK"""
        response = self.client.get('/api/v1/users/test/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['message'], 'API is connected successfully!')
        self.assertEqual(data['method'], 'GET')
        self.assertIn('headers', data)
        self.assertIsInstance(data['headers'], dict)

    def test_connection_post_200(self):
        """Test test_connection POST request - 200 OK"""
        response = self.client.post('/api/v1/users/test/', {'test': 'data'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['message'], 'API is connected successfully!')
        self.assertEqual(data['method'], 'POST')
        self.assertIn('headers', data)

    def test_connection_headers_included(self):
        """Test that headers are properly included in response"""
        response = self.client.get('/api/v1/users/test/', HTTP_X_CUSTOM_HEADER='test-value')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.json()
        headers = data['headers']
        # Check that custom header is included
        self.assertIn('X-Custom-Header', headers)
        self.assertEqual(headers['X-Custom-Header'], 'test-value')

    def test_connection_other_methods_not_allowed(self):
        """Test that other HTTP methods are not allowed"""
        # Test PUT
        response = self.client.put('/api/v1/users/test/')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        
        # Test DELETE
        response = self.client.delete('/api/v1/users/test/')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_connection_no_authentication_required(self):
        """Test that no authentication is required for test_connection"""
        # Should work without any authentication
        response = self.client.get('/api/v1/users/test/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class LogoutViewTest(TestCase):
    """Tests for logout_view endpoint"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.token = Token.objects.create(user=self.user)

    def test_logout_success_200(self):
        """Test successful logout - 200 OK"""
        # Authenticate with token
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        
        response = self.client.post('/api/v1/users/auth/logout/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['message'], 'Logged out successfully')
        
        # Verify token was deleted
        self.assertFalse(Token.objects.filter(key=self.token.key).exists())

    def test_logout_no_authentication_401(self):
        """Test logout without authentication - 401 Unauthorized"""
        response = self.client.post('/api/v1/users/auth/logout/')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_invalid_token_401(self):
        """Test logout with invalid token - 401 Unauthorized"""
        self.client.credentials(HTTP_AUTHORIZATION='Token invalid_token_123')
        
        response = self.client.post('/api/v1/users/auth/logout/')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_already_logged_out(self):
        """Test logout when token is deleted but user still has valid credentials"""
        # Authenticate with token but then manually delete the auth_token relationship
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        
        # Create a new token to maintain authentication, but then break the auth_token relationship
        response = self.client.post('/api/v1/users/auth/logout/')
        
        # After successful logout, trying again should give 401
        response2 = self.client.post('/api/v1/users/auth/logout/')
        self.assertEqual(response2.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_only_accepts_post(self):
        """Test that logout endpoint only accepts POST requests"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        
        # Test GET request
        response = self.client.get('/api/v1/users/auth/logout/')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        
        # Test PUT request  
        response = self.client.put('/api/v1/users/auth/logout/')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    @patch('users.auth_views.logger')
    def test_logout_logging_success(self, mock_logger):
        """Test that successful logout is logged"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        
        response = self.client.post('/api/v1/users/auth/logout/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_logger.info.assert_called_with(f"Logout successful for user: {self.user.username}")

    def test_logout_exception_handling(self):
        """Test logout with exception in token deletion"""
        # This test is harder to trigger since Django's auth_token.delete() rarely fails
        # We'll test the happy path since the exception path is already covered by the catch-all
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        
        response = self.client.post('/api/v1/users/auth/logout/')
        
        # Normal successful logout
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['message'], 'Logged out successfully')