# biometrics/tests.py
import base64
import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from tests.base import BaseAPITestCase, UnauthenticatedAPITestCase
from users.models import Employee
from worktime.models import WorkLog
from biometrics.services.biometrics import BiometricService
from biometrics.services.face_recognition_service import FaceRecognitionService
from django.utils import timezone


class BiometricServiceTest(TestCase):
    """Test cases for BiometricService"""
    
    def setUp(self):
        self.employee = Employee.objects.create(
            first_name='John',
            last_name='Doe',
            email='john.doe@example.com',
            employment_type='hourly'
        )
        
    @patch('biometrics.services.biometrics.settings.MONGO_DB')
    def test_get_collection(self, mock_mongo_db):
        """Test getting MongoDB collection"""
        # Mock MongoDB collection
        mock_collection = MagicMock()
        mock_mongo_db.__getitem__.return_value = mock_collection
        
        collection = BiometricService.get_collection()
        
        self.assertIsNotNone(collection)
        mock_mongo_db.__getitem__.assert_called_with('face_encodings')
    
    @patch('biometrics.services.biometrics.BiometricService.get_collection')
    def test_save_face_encoding(self, mock_get_collection):
        """Test saving face encodings"""
        # Mock collection
        mock_collection = MagicMock()
        mock_get_collection.return_value = mock_collection
        
        # Mock find_one to return None (no existing document)
        mock_collection.find_one.return_value = None
        
        # Mock insert_one result
        mock_result = MagicMock()
        mock_result.inserted_id = 'abc123'
        mock_collection.insert_one.return_value = mock_result
        
        # Test face encoding
        test_encoding = [0.1, 0.2, 0.3, 0.4, 0.5]
        
        result = BiometricService.save_face_encoding(
            employee_id=self.employee.id,
            face_encoding=test_encoding
        )
        
        self.assertEqual(result, 'abc123')
        mock_collection.insert_one.assert_called_once()


class FaceRecognitionServiceTest(TestCase):
    """Test cases for FaceRecognitionService"""
    
    def test_decode_image(self):
        """Test decoding base64 image"""
        # Create a simple test image (1x1 red pixel PNG)
        test_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        
        result = FaceRecognitionService.decode_image(test_image_base64)
        
        self.assertIsNotNone(result)
    
    @patch('biometrics.services.face_recognition_service.FaceRecognitionService.FACE_CASCADE')
    def test_extract_face_features(self, mock_cascade):
        """Test extracting face features"""
        import numpy as np
        
        # Mock face detection
        mock_cascade.detectMultiScale.return_value = [(10, 10, 100, 100)]
        
        # Create a dummy image
        test_image = np.zeros((200, 200, 3), dtype=np.uint8)
        
        result = FaceRecognitionService.extract_face_features(test_image)
        
        self.assertIsNotNone(result)


class BiometricAPITest(BaseAPITestCase):
    """Test cases for biometric API endpoints"""
    
    def setUp(self):
        super().setUp()
        
        # Test image data (longer base64 string to pass validation)
        self.test_image = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
                          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
                          "additional_padding_to_make_string_longer_than_100_chars_for_validation_purposes")
    
    @patch('biometrics.services.face_recognition_service.FaceRecognitionService.save_employee_face')
    def test_face_registration(self, mock_save_face):
        """Test face registration endpoint"""
        mock_save_face.return_value = 'test_document_id'
        
        url = reverse('face-register')
        data = {
            'employee_id': self.employee.id,
            'image': self.test_image
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertIn('Face registered', response.data['message'])
    
    @patch('biometrics.services.face_recognition_service.FaceRecognitionService.recognize_employee')
    def test_face_recognition_check_in(self, mock_recognize):
        """Test face recognition check-in endpoint"""
        mock_recognize.return_value = self.employee.id
        
        url = reverse('face-check-in')
        data = {
            'image': self.test_image,
            'location': 'Office'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['employee_id'], self.employee.id)
    
    @patch('biometrics.services.face_recognition_service.FaceRecognitionService.recognize_employee')
    def test_face_recognition_check_out(self, mock_recognize):
        """Test face recognition check-out endpoint"""
        mock_recognize.return_value = self.employee.id
        
        # First create a check-in
        check_in_time = timezone.now()
        worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=check_in_time,
            location_check_in='Office'
        )
        
        url = reverse('face-check-out')
        data = {
            'image': self.test_image,
            'location': 'Office'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['employee_id'], self.employee.id)
    
    def test_face_registration_missing_data(self, ):
        """Test face registration endpoint with missing data"""
        url = reverse('face-register')
        data = {
            'employee_id': self.employee.id
            # Missing 'image' field
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    def test_face_recognition_missing_image(self):
        """Test face recognition endpoints with missing image"""
        url = reverse('face-check-in')
        data = {
            'location': 'Office'
            # Missing 'image' field
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
    
    @patch('biometrics.services.face_recognition_service.FaceRecognitionService.recognize_employee')
    def test_face_recognition_no_match(self, mock_recognize):
        """Test face recognition with no matching face"""
        mock_recognize.return_value = None
        
        url = reverse('face-check-in')
        data = {
            'image': self.test_image,
            'location': 'Office'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Face not recognized', response.data['error'])
    
    @patch('biometrics.services.face_recognition_service.FaceRecognitionService.recognize_employee')
    def test_face_recognition_multiple_check_in(self, mock_recognize):
        """Test multiple check-ins"""
        mock_recognize.return_value = self.employee.id
        
        # Create existing check-in
        WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.now(),
            location_check_in='Office'
        )
        
        url = reverse('face-check-in')
        data = {
            'image': self.test_image,
            'location': 'Office'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('already has an open shift', response.data['error'])
    
    @patch('biometrics.services.face_recognition_service.FaceRecognitionService.recognize_employee')
    def test_face_recognition_check_out_without_check_in(self, mock_recognize):
        """Test check-out without a prior check-in"""
        mock_recognize.return_value = self.employee.id
        
        url = reverse('face-check-out')
        data = {
            'image': self.test_image,
            'location': 'Office'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('No open shift found', response.data['error'])


class BiometricAPIUnauthenticatedTest(UnauthenticatedAPITestCase):
    """Test biometric API endpoints without authentication"""
    
    def test_face_registration_unauthenticated(self):
        """Test face registration without authentication"""
        url = reverse('face-register')
        data = {
            'employee_id': self.employee.id,
            'image': 'test_image_data'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_face_recognition_unauthenticated(self):
        """Test face recognition without authentication"""
        url = reverse('face-check-in')
        data = {
            'image': 'test_image_data',
            'location': 'Office'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)