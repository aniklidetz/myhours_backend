"""
Tests for core exception handling - custom exception handler and API error classes.
"""

import uuid
from unittest.mock import MagicMock, patch

from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    ParseError,
    PermissionDenied,
    Throttled,
    UnsupportedMediaType,
)
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ValidationError
from django.http import Http404
from django.test import RequestFactory, TestCase

from core.exceptions import (
    APIError,
    AuthenticationError,
    BiometricError,
    PermissionError,
    custom_exception_handler,
    format_error_details,
    get_error_code,
    get_error_message,
)


class CustomExceptionHandlerTest(TestCase):
    """Tests for custom_exception_handler function"""

    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='test123'
        )

    def create_context(self, path='/test/', method='GET'):
        """Helper to create request context"""
        request = self.factory.get(path)
        request.user = self.user
        request.method = method
        request.path = path
        return {'request': request}

    @patch('core.exceptions.logger')
    def test_drf_exception_handling(self, mock_logger):
        """Test handling of DRF exceptions"""
        exc = NotFound(detail="Resource not found")
        context = self.create_context()
        
        response = custom_exception_handler(exc, context)
        
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        
        # Check response structure
        self.assertIn('error', response.data)
        self.assertIn('code', response.data)
        self.assertIn('message', response.data)
        self.assertIn('details', response.data)
        self.assertIn('error_id', response.data)
        self.assertIn('timestamp', response.data)
        
        self.assertTrue(response.data['error'])
        self.assertEqual(response.data['code'], 'RESOURCE_NOT_FOUND')
        
        # Check that logger was called
        mock_logger.error.assert_called_once()

    @patch('core.exceptions.logger')
    def test_http404_handling(self, mock_logger):
        """Test handling of Django Http404"""
        exc = Http404("Page not found")
        context = self.create_context()
        
        # Mock the DRF exception handler to return None for Http404
        with patch('core.exceptions.exception_handler', return_value=None):
            response = custom_exception_handler(exc, context)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(response.data['error'])
        self.assertEqual(response.data['code'], 'RESOURCE_NOT_FOUND')
        self.assertEqual(response.data['message'], 'The requested resource was not found.')
        
        mock_logger.error.assert_called_once()

    @patch('core.exceptions.logger')
    def test_django_validation_error_handling(self, mock_logger):
        """Test handling of Django ValidationError"""
        exc = ValidationError("Invalid data")
        context = self.create_context()
        
        response = custom_exception_handler(exc, context)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data['error'])
        self.assertEqual(response.data['code'], 'VALIDATION_ERROR')
        self.assertEqual(response.data['message'], 'Validation failed.')
        
        mock_logger.error.assert_called_once()

    @patch('core.exceptions.logger')
    def test_django_validation_error_with_message_dict(self, mock_logger):
        """Test handling of Django ValidationError with message_dict"""
        exc = ValidationError({'field1': ['Error 1'], 'field2': ['Error 2']})
        context = self.create_context()
        
        response = custom_exception_handler(exc, context)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'VALIDATION_ERROR')
        self.assertIsInstance(response.data['details'], dict)

    @patch('core.exceptions.logger')
    def test_generic_exception_handling(self, mock_logger):
        """Test handling of generic exceptions"""
        exc = RuntimeError("Something went wrong")
        context = self.create_context()
        
        response = custom_exception_handler(exc, context)
        
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertTrue(response.data['error'])
        self.assertEqual(response.data['code'], 'INTERNAL_SERVER_ERROR')
        self.assertEqual(response.data['message'], 'An internal server error occurred.')
        self.assertIsNone(response.data['details'])
        
        # Should log with exc_info=True for unhandled exceptions
        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args
        self.assertTrue(call_args.kwargs.get('exc_info'))

    def test_error_id_generation(self):
        """Test that error IDs are generated and included"""
        exc = NotFound("Test error")
        context = self.create_context()
        
        response = custom_exception_handler(exc, context)
        
        self.assertIn('error_id', response.data)
        error_id = response.data['error_id']
        self.assertIsInstance(error_id, str)
        self.assertEqual(len(error_id), 8)  # First 8 chars of UUID

    def test_context_with_anonymous_user(self):
        """Test handling with anonymous user"""
        exc = NotFound("Test error")
        request = self.factory.get('/test/')
        request.user = AnonymousUser()
        request.method = 'GET'
        request.path = '/test/'
        context = {'request': request}
        
        response = custom_exception_handler(exc, context)
        
        self.assertIsNotNone(response)
        self.assertTrue(response.data['error'])

    def test_context_without_request(self):
        """Test handling without request context"""
        exc = NotFound("Test error")
        context = {}
        
        # Should not crash even without request
        response = custom_exception_handler(exc, context)
        
        self.assertIsNotNone(response)
        self.assertTrue(response.data['error'])

    @patch('core.exceptions.exception_handler')
    def test_drf_handler_called_first(self, mock_drf_handler):
        """Test that DRF's exception handler is called first"""
        mock_response = MagicMock()
        mock_response.status_code = status.HTTP_400_BAD_REQUEST
        mock_response.data = {'detail': 'Test error'}
        mock_drf_handler.return_value = mock_response
        
        exc = DRFValidationError("Test error")
        context = self.create_context()
        
        response = custom_exception_handler(exc, context)
        
        # Verify DRF handler was called
        mock_drf_handler.assert_called_once_with(exc, context)
        
        # Verify our custom structure is applied
        self.assertIn('error', response.data)
        self.assertIn('code', response.data)


class GetErrorCodeTest(TestCase):
    """Tests for get_error_code function"""

    def test_known_exception_codes(self):
        """Test error codes for known exceptions"""
        test_cases = [
            (DRFValidationError(), 'VALIDATION_ERROR'),
            (PermissionDenied(), 'PERMISSION_DENIED'),
            (NotAuthenticated(), 'AUTHENTICATION_REQUIRED'),
            (AuthenticationFailed(), 'AUTHENTICATION_FAILED'),
            (NotFound(), 'RESOURCE_NOT_FOUND'),
            (MethodNotAllowed('GET'), 'METHOD_NOT_ALLOWED'),
            (ParseError(), 'PARSE_ERROR'),
            (UnsupportedMediaType('application/json'), 'UNSUPPORTED_MEDIA_TYPE'),
            (Throttled(), 'RATE_LIMIT_EXCEEDED'),
        ]
        
        for exc, expected_code in test_cases:
            with self.subTest(exception=exc.__class__.__name__):
                self.assertEqual(get_error_code(exc), expected_code)

    def test_unknown_exception_code(self):
        """Test error code for unknown exception"""
        exc = RuntimeError("Unknown error")
        self.assertEqual(get_error_code(exc), 'UNKNOWN_ERROR')

    def test_custom_exception_code(self):
        """Test error code for custom exception"""
        class CustomException(Exception):
            pass
        
        exc = CustomException()
        self.assertEqual(get_error_code(exc), 'UNKNOWN_ERROR')


class GetErrorMessageTest(TestCase):
    """Tests for get_error_message function"""

    def test_dict_with_detail(self):
        """Test extracting message from dict with detail"""
        data = {'detail': 'This is the error message'}
        self.assertEqual(get_error_message(data), 'This is the error message')

    def test_dict_with_non_field_errors(self):
        """Test extracting message from dict with non_field_errors"""
        data = {'non_field_errors': ['First error', 'Second error']}
        self.assertEqual(get_error_message(data), 'First error')

    def test_dict_with_empty_non_field_errors(self):
        """Test dict with empty non_field_errors"""
        data = {'non_field_errors': []}
        self.assertEqual(get_error_message(data), 'Validation error')

    def test_dict_with_field_errors_list(self):
        """Test extracting message from dict with field errors as list"""
        data = {'field_name': ['Field error message']}
        self.assertEqual(get_error_message(data), 'Field error message')

    def test_dict_with_field_errors_string(self):
        """Test extracting message from dict with field errors as string"""
        data = {'field_name': 'Field error message'}
        self.assertEqual(get_error_message(data), 'Field error message')

    def test_dict_with_no_errors(self):
        """Test dict with no recognizable error format"""
        data = {'some_key': []}
        self.assertEqual(get_error_message(data), 'Validation error')

    def test_list_with_errors(self):
        """Test extracting message from list"""
        data = ['First error', 'Second error']
        self.assertEqual(get_error_message(data), 'First error')

    def test_empty_list(self):
        """Test empty list"""
        data = []
        self.assertEqual(get_error_message(data), '[]')

    def test_string_data(self):
        """Test string data"""
        data = 'Simple error message'
        self.assertEqual(get_error_message(data), 'Simple error message')

    def test_other_data_types(self):
        """Test other data types"""
        data = 123
        self.assertEqual(get_error_message(data), '123')


class FormatErrorDetailsTest(TestCase):
    """Tests for format_error_details function"""

    def test_dict_with_detail_removed(self):
        """Test that detail is removed from dict"""
        data = {
            'detail': 'Main error message',
            'field1': ['Field error'],
            'field2': 'Another error'
        }
        
        result = format_error_details(data)
        
        self.assertIsInstance(result, dict)
        self.assertNotIn('detail', result)
        self.assertIn('field1', result)
        self.assertIn('field2', result)

    def test_dict_with_only_detail(self):
        """Test dict with only detail returns None"""
        data = {'detail': 'Only detail'}
        
        result = format_error_details(data)
        
        self.assertIsNone(result)

    def test_dict_without_detail(self):
        """Test dict without detail is returned as-is"""
        data = {
            'field1': ['Error 1'],
            'field2': 'Error 2'
        }
        
        result = format_error_details(data)
        
        self.assertEqual(result, data)

    def test_empty_dict(self):
        """Test empty dict returns None"""
        data = {}
        
        result = format_error_details(data)
        
        self.assertIsNone(result)

    def test_list_data(self):
        """Test list data is returned as-is"""
        data = ['Error 1', 'Error 2']
        
        result = format_error_details(data)
        
        self.assertEqual(result, data)

    def test_string_data(self):
        """Test string data returns None"""
        data = 'Simple error'
        
        result = format_error_details(data)
        
        self.assertIsNone(result)

    def test_other_data_types(self):
        """Test other data types return None"""
        data = 123
        
        result = format_error_details(data)
        
        self.assertIsNone(result)


class APIErrorTest(TestCase):
    """Tests for APIError custom exception class"""

    def test_basic_api_error(self):
        """Test basic APIError creation"""
        error = APIError("Something went wrong")
        
        self.assertEqual(str(error), "Something went wrong")
        self.assertEqual(error.message, "Something went wrong")
        self.assertEqual(error.code, "API_ERROR")
        self.assertEqual(error.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNone(error.details)

    def test_api_error_with_custom_code(self):
        """Test APIError with custom code"""
        error = APIError("Custom error", code="CUSTOM_ERROR")
        
        self.assertEqual(error.code, "CUSTOM_ERROR")

    def test_api_error_with_custom_status_code(self):
        """Test APIError with custom status code"""
        error = APIError("Server error", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        self.assertEqual(error.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def test_api_error_with_details(self):
        """Test APIError with details"""
        details = {"field1": "Invalid value", "field2": "Required"}
        error = APIError("Validation failed", details=details)
        
        self.assertEqual(error.details, details)

    def test_api_error_all_parameters(self):
        """Test APIError with all parameters"""
        details = {"validation": "failed"}
        error = APIError(
            message="Custom message",
            code="CUSTOM_CODE",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details
        )
        
        self.assertEqual(error.message, "Custom message")
        self.assertEqual(error.code, "CUSTOM_CODE")
        self.assertEqual(error.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(error.details, details)


class BiometricErrorTest(TestCase):
    """Tests for BiometricError exception class"""

    def test_basic_biometric_error(self):
        """Test basic BiometricError creation"""
        error = BiometricError("Biometric verification failed")
        
        self.assertEqual(str(error), "Biometric verification failed")
        self.assertEqual(error.message, "Biometric verification failed")
        self.assertEqual(error.code, "BIOMETRIC_ERROR")
        self.assertEqual(error.status_code, status.HTTP_400_BAD_REQUEST)

    def test_biometric_error_with_custom_code(self):
        """Test BiometricError with custom code"""
        error = BiometricError("Face not detected", code="FACE_NOT_DETECTED")
        
        self.assertEqual(error.code, "FACE_NOT_DETECTED")

    def test_biometric_error_with_details(self):
        """Test BiometricError with details"""
        details = {"quality_score": 0.3, "minimum_required": 0.7}
        error = BiometricError("Low quality image", details=details)
        
        self.assertEqual(error.details, details)

    def test_biometric_error_inheritance(self):
        """Test that BiometricError inherits from APIError"""
        error = BiometricError("Test error")
        self.assertIsInstance(error, APIError)


class AuthenticationErrorTest(TestCase):
    """Tests for AuthenticationError exception class"""

    def test_basic_authentication_error(self):
        """Test basic AuthenticationError creation"""
        error = AuthenticationError("Invalid credentials")
        
        self.assertEqual(str(error), "Invalid credentials")
        self.assertEqual(error.message, "Invalid credentials")
        self.assertEqual(error.code, "AUTHENTICATION_ERROR")
        self.assertEqual(error.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authentication_error_with_custom_code(self):
        """Test AuthenticationError with custom code"""
        error = AuthenticationError("Token expired", code="TOKEN_EXPIRED")
        
        self.assertEqual(error.code, "TOKEN_EXPIRED")

    def test_authentication_error_with_details(self):
        """Test AuthenticationError with details"""
        details = {"expires_at": "2023-12-01T10:00:00Z"}
        error = AuthenticationError("Token expired", details=details)
        
        self.assertEqual(error.details, details)

    def test_authentication_error_inheritance(self):
        """Test that AuthenticationError inherits from APIError"""
        error = AuthenticationError("Test error")
        self.assertIsInstance(error, APIError)


class PermissionErrorTest(TestCase):
    """Tests for PermissionError exception class"""

    def test_basic_permission_error(self):
        """Test basic PermissionError creation"""
        error = PermissionError("Access denied")
        
        self.assertEqual(str(error), "Access denied")
        self.assertEqual(error.message, "Access denied")
        self.assertEqual(error.code, "PERMISSION_ERROR")
        self.assertEqual(error.status_code, status.HTTP_403_FORBIDDEN)

    def test_permission_error_with_custom_code(self):
        """Test PermissionError with custom code"""
        error = PermissionError("Admin required", code="ADMIN_REQUIRED")
        
        self.assertEqual(error.code, "ADMIN_REQUIRED")

    def test_permission_error_with_details(self):
        """Test PermissionError with details"""
        details = {"required_role": "admin", "current_role": "employee"}
        error = PermissionError("Insufficient permissions", details=details)
        
        self.assertEqual(error.details, details)

    def test_permission_error_inheritance(self):
        """Test that PermissionError inherits from APIError"""
        error = PermissionError("Test error")
        self.assertIsInstance(error, APIError)


class ExceptionHandlerIntegrationTest(TestCase):
    """Integration tests for exception handling"""

    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='test123'
        )

    def test_custom_api_error_handling(self):
        """Test that custom APIError is handled by DRF's handler"""
        from rest_framework.views import exception_handler as drf_handler
        
        error = APIError("Custom API error", code="CUSTOM_ERROR")
        request = self.factory.get('/test/')
        request.user = self.user
        context = {'request': request}
        
        # Test that our custom error works with DRF handler
        # (Note: DRF handler might return None for non-DRF exceptions)
        response = drf_handler(error, context)
        
        # If DRF doesn't handle it, our custom handler should
        if response is None:
            response = custom_exception_handler(error, context)
            
        self.assertIsNotNone(response)

    def test_chained_exception_handling(self):
        """Test exception handling with chained exceptions"""
        try:
            try:
                raise ValueError("Original error")
            except ValueError as e:
                raise APIError("Wrapped error") from e
        except APIError as exc:
            request = self.factory.get('/test/')
            request.user = self.user
            context = {'request': request}
            
            response = custom_exception_handler(exc, context)
            
            self.assertIsNotNone(response)
            self.assertTrue(response.data['error'])

    @patch('core.exceptions.uuid.uuid4')
    def test_error_id_uniqueness(self, mock_uuid):
        """Test that error IDs are properly generated"""
        mock_uuid.return_value = MagicMock()
        mock_uuid.return_value.__str__.return_value = "12345678-1234-1234-1234-123456789abc"
        
        exc = NotFound("Test error")
        request = self.factory.get('/test/')
        request.user = self.user
        context = {'request': request}
        
        response = custom_exception_handler(exc, context)
        
        self.assertEqual(response.data['error_id'], "12345678")
        mock_uuid.assert_called_once()

    def test_request_info_extraction(self):
        """Test that request information is properly extracted"""
        exc = NotFound("Test error")
        request = self.factory.post('/api/test/?param=value')
        request.user = self.user
        request.method = 'POST'
        request.path = '/api/test/'
        context = {'request': request}
        
        # Should not crash and should extract request info for logging
        response = custom_exception_handler(exc, context)
        
        self.assertIsNotNone(response)
        self.assertTrue(response.data['error'])