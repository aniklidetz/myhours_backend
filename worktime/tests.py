from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.utils import timezone
from users.models import Employee
from worktime.models import WorkLog
from decimal import Decimal


class WorkLogModelTest(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            first_name="John",
            last_name="Doe",
            email="john.doe@example.com"
        )
        
    def test_worklog_creation(self):
        # Create a worklog spanning 8 hours
        check_in = timezone.now()
        check_out = check_in + timezone.timedelta(hours=8)
        
        worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=check_in,
            check_out=check_out
        )
        
        self.assertEqual(worklog.get_total_hours(), 8.0)
        self.assertEqual(worklog.employee, self.employee)
    
    def test_worklog_without_checkout(self):
        worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.now()
        )
        
        self.assertEqual(worklog.get_total_hours(), 0)
        self.assertIsNone(worklog.check_out)


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