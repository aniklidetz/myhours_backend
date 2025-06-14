# users/tests.py
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from tests.base import BaseTestCase, BaseAPITestCase
from users.models import Employee
from tests.fixtures import TestFixtures


class EmployeeModelTest(BaseTestCase):
    """Employee model test"""
    
    def test_employee_creation(self):
        """Test employee creation"""
        # Use unique email to avoid conflicts
        employee = Employee.objects.create(
            first_name="Jane",
            last_name="Smith",
            email="jane.smith.test@example.com",
            employment_type="hourly"
        )
        
        self.assertEqual(employee.first_name, "Jane")
        self.assertEqual(employee.last_name, "Smith")
        self.assertEqual(employee.email, "jane.smith.test@example.com")
    
    def test_employee_get_full_name(self):
        """Test get_full_name method"""
        # Use the employee from BaseTestCase
        full_name = self.employee.get_full_name()
        self.assertEqual(full_name, "John Doe")


class EmployeeAPITest(BaseAPITestCase):
    """Employee API test"""
    
    def setUp(self):
        super().setUp()
        # Create a unique test employee to avoid email conflicts
        self.test_employee = Employee.objects.create(
            first_name="Test",
            last_name="User",
            email="test.user.unique@example.com",
            employment_type="monthly"
        )
    
    def test_create_employee_authenticated(self):
        """Test employee creation with authentication"""
        url = reverse('employee-list')
        data = {
            'first_name': 'Alice',
            'last_name': 'Johnson',
            'email': 'alice.johnson@example.com',
            'employment_type': 'hourly'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Employee.objects.filter(email='alice.johnson@example.com').count(), 1)
    
    def test_create_employee_unauthenticated(self):
        """Test employee creation without authentication"""
        # Create unauthenticated client
        from rest_framework.test import APIClient
        client = APIClient()
        
        url = reverse('employee-list')
        data = {
            'first_name': 'Bob',
            'last_name': 'Wilson',
            'email': 'bob.wilson@example.com',
            'employment_type': 'hourly'
        }
        
        response = client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_search_employee(self):
        """Test employee search"""
        url = reverse('employee-list')
        
        response = self.client.get(url, {'search': 'Test'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        # Should find our test employee
        found = any(emp['first_name'] == 'Test' for emp in response.data['results'])
        self.assertTrue(found)