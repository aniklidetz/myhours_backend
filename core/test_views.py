from core.test_utils import create_test_employee
from django.test import TestCase
from django.urls import reverse
from core.models import Employee, WorkLog, Salary
from django.utils import timezone

class ViewsetTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            first_name="John",
            last_name="Doe", 
            email="john@example.com"
        )
        
        self.salary = Salary.objects.create(
            employee=self.employee,
            hourly_rate=50.00
        )
        
        self.worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.now(),
            check_out=timezone.now() + timezone.timedelta(hours=4)
        )
    
    def test_employee_list_view(self):
        url = reverse('employee-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_worklog_list_view(self):
        url = reverse('worklog-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_salary_list_view(self):
        url = reverse('salary-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 1)
