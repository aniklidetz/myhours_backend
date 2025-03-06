from core.test_utils import create_test_employee
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from core.models import Employee, WorkLog, Salary
from django.utils import timezone

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

class SalaryAPITest(APITestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            first_name="John", 
            last_name="Doe", 
            email="john@example.com",
            employment_type="hourly"
        )
        
        self.salary = Salary.objects.create(
            employee=self.employee,
            hourly_rate=50.00,
            base_salary=0.00
        )
        
        # Create worklog for salary calculation
        self.worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.now(),
            check_out=timezone.now() + timezone.timedelta(hours=8)
        )
    
    def test_calculate_salary(self):
        url = reverse('salary-calculate', args=[self.salary.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('salary', response.data)
        
        # Check if salary was updated in database
        self.salary.refresh_from_db()
        self.assertEqual(self.salary.calculated_salary, 400.00)

class WorkLogAPITest(APITestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            first_name="John", 
            last_name="Doe", 
            email="john@example.com"
        )
        
        # Create a worklog
        self.check_in = timezone.now()
        self.check_out = self.check_in + timezone.timedelta(hours=8)
        self.worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=self.check_in,
            check_out=self.check_out
        )
    
    def test_filter_worklog_by_date(self):
        today = timezone.now().date()
        url = reverse('worklog-list')
        response = self.client.get(f"{url}?date={today}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        
        # Try with a different date
        yesterday = (timezone.now() - timezone.timedelta(days=1)).date()
        response = self.client.get(f"{url}?date={yesterday}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)
