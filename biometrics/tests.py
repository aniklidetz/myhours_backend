from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.utils import timezone
from users.models import Employee
from worktime.models import WorkLog
import base64
import os
from unittest.mock import patch


class BiometricAPITest(APITestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            first_name="John",
            last_name="Doe",
            email="john@example.com"
        )
        
        # We'll use a mock image for face recognition tests
        self.sample_image_base64 = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/..."

    @patch('biometrics.services.face_recognition_service.FaceRecognitionService.save_employee_face')
    def test_face_registration(self, mock_save_face):
        # Mock the save_employee_face method to return a document ID
        mock_save_face.return_value = "123456789"
        
        url = reverse('face-register')
        data = {
            'employee_id': self.employee.id,
            'image': self.sample_image_base64
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['document_id'], "123456789")

    @patch('biometrics.services.face_recognition_service.FaceRecognitionService.recognize_employee')
    def test_face_recognition_check_in(self, mock_recognize):
        # Mock the recognize_employee method to return the employee ID
        mock_recognize.return_value = self.employee.id
        
        url = reverse('face-check-in')
        data = {
            'image': self.sample_image_base64,
            'location': '31.7767,35.2345'
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        
        # Verify a worklog was created
        worklog = WorkLog.objects.filter(employee=self.employee, check_out__isnull=True).first()
        self.assertIsNotNone(worklog)

    @patch('biometrics.services.face_recognition_service.FaceRecognitionService.recognize_employee')
    def test_face_recognition_check_out(self, mock_recognize):
        # Create an open worklog
        worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.now() - timezone.timedelta(hours=8)
        )
        
        # Mock the recognize_employee method to return the employee ID
        mock_recognize.return_value = self.employee.id
        
        url = reverse('face-check-out')
        data = {
            'image': self.sample_image_base64,
            'location': '31.7767,35.2345'
        }
        
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        
        # Verify the worklog was updated with check_out time
        worklog.refresh_from_db()
        self.assertIsNotNone(worklog.check_out)