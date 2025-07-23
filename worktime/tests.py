from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from tests.base import BaseAPITestCase, UnauthenticatedAPITestCase
from users.models import Employee
from worktime.models import WorkLog
from django.utils import timezone
from datetime import timedelta


class WorkLogModelTest(TestCase):
    """Test cases for WorkLog model"""
    
    def setUp(self):
        self.employee = Employee.objects.create(
            first_name='John',
            last_name='Doe',
            email='john.doe@example.com',
            employment_type='hourly'
        )
    
    def test_worklog_creation(self):
        """Test creating a work log"""
        check_in_time = timezone.now()
        check_out_time = check_in_time + timedelta(hours=8)
        
        worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=check_in_time,
            check_out=check_out_time
        )
        
        self.assertEqual(worklog.employee, self.employee)
        self.assertEqual(worklog.check_in, check_in_time)
        self.assertEqual(worklog.check_out, check_out_time)
        self.assertEqual(worklog.get_total_hours(), 8.0)
    
    def test_worklog_without_checkout(self):
        """Test creating a work log without checkout"""
        check_in_time = timezone.now()
        
        worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=check_in_time
        )
        
        self.assertEqual(worklog.employee, self.employee)
        self.assertEqual(worklog.check_in, check_in_time)
        self.assertIsNone(worklog.check_out)
        self.assertTrue(worklog.is_current_session())


class WorkLogAPITest(BaseAPITestCase):
    """Test cases for WorkLog API endpoints"""
    
    def setUp(self):
        super().setUp()
        
        # Create test work logs
        base_time = timezone.now()
        
        for i in range(3):
            check_in = base_time + timedelta(days=i)
            check_out = check_in + timedelta(hours=8)
            
            WorkLog.objects.create(
                employee=self.employee,
                check_in=check_in,
                check_out=check_out
            )
    
    def test_filter_worklog_by_date(self):
        """Test filtering work logs by date"""
        url = reverse('worklog-list')
        today = timezone.now().date()
        
        response = self.client.get(url, {'check_in__date': today.isoformat()})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
    
    def test_list_worklogs(self):
        """Test listing work logs"""
        url = reverse('worklog-list')
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertGreaterEqual(len(response.data['results']), 1)


class WorkLogAPIUnauthenticatedTest(UnauthenticatedAPITestCase):
    """Test WorkLog API endpoints without authentication"""
    
    def test_list_worklogs_unauthenticated(self):
        """Test listing work logs without authentication"""
        url = reverse('worklog-list')
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)