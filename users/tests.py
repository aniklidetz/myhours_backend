from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from users.models import Employee
from decimal import Decimal


class EmployeeModelTest(TestCase):
    def test_employee_creation(self):
        employee = Employee.objects.create(
            first_name="John",
            last_name="Doe",
            email="john.doe@example.com",
            employment_type="hourly"
        )
        self.assertEqual(str(employee), "John Doe")
        self.assertTrue(employee.is_active)
        self.assertEqual(employee.employment_type, "hourly")


class EmployeeAPITest(APITestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            first_name="John",
            last_name="Doe", 
            email="john@example.com",
            employment_type="hourly"
        )
        
    def test_create_employee(self):
        url = reverse('employee-list')
        data = {
            'first_name': 'Jane',
            'last_name': 'Smith',
            'email': 'jane@example.com',
            'employment_type': 'monthly'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Employee.objects.count(), 2)
    
    def test_search_employee(self):
        url = reverse('employee-list')
        response = self.client.get(f"{url}?search=John")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        
        response = self.client.get(f"{url}?search=NonExistent")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)