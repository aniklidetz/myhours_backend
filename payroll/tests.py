# payroll/tests.py
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from tests.base import BaseAPITestCase, UnauthenticatedAPITestCase
from users.models import Employee
from worktime.models import WorkLog
from payroll.models import Salary
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal


class SalaryModelTest(TestCase):
    """Test cases for Salary model"""
    
    def setUp(self):
        self.employee = Employee.objects.create(
            first_name='John',
            last_name='Doe',
            email='john.doe@example.com',
            employment_type='hourly'
        )
        
        self.salary = Salary.objects.create(
            employee=self.employee,
            base_salary=None,  # Must be None for hourly calculation type
            hourly_rate=Decimal('50.00'),
            calculation_type='hourly'
        )
    
    def test_salary_calculation(self):
        """Test basic salary calculation"""
        # Create work logs with proper timezone-aware datetimes
        check_in = timezone.make_aware(datetime(2025, 5, 29, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 5, 29, 17, 0))
        
        WorkLog.objects.create(
            employee=self.employee,
            check_in=check_in,
            check_out=check_out
        )
        
        # Test calculation
        result = self.salary.calculate_salary()
        self.assertIsNotNone(result)
        self.assertIsInstance(result, (int, float, Decimal))
    
    def test_hourly_salary_calculation(self):
        """Test hourly salary calculation with multiple work sessions"""
        base_date = timezone.now().date()
        
        # Create work logs for different days to avoid overlaps
        for i in range(3):
            work_date = base_date + timedelta(days=i)
            check_in = timezone.make_aware(
                datetime.combine(work_date, datetime.min.time().replace(hour=9))
            )
            check_out = timezone.make_aware(
                datetime.combine(work_date, datetime.min.time().replace(hour=17))
            )
            
            WorkLog.objects.create(
                employee=self.employee,
                check_in=check_in,
                check_out=check_out
            )
        
        # Test monthly calculation
        now = timezone.now()
        result = self.salary.calculate_monthly_salary(now.month, now.year)
        
        self.assertIsInstance(result, dict)
        self.assertIn('total_salary', result)
        self.assertGreater(result['total_salary'], 0)


class SalaryAPITest(BaseAPITestCase):
    """Test cases for Salary API endpoints"""
    
    def setUp(self):
        super().setUp()
        
        self.salary = Salary.objects.create(
            employee=self.employee,
            base_salary=None,  # Must be None for hourly calculation type
            hourly_rate=Decimal('50.00'),
            calculation_type='hourly'
        )
    
    def test_calculate_salary(self):
        """Test salary calculation endpoint - SKIPPED: endpoint not implemented"""
        self.skipTest("salary-calculate endpoint not implemented yet")


class SalaryAPIUnauthenticatedTest(UnauthenticatedAPITestCase):
    """Test salary API endpoints without authentication"""
    
    def setUp(self):
        super().setUp()
        
        self.salary = Salary.objects.create(
            employee=self.employee,
            base_salary=None,  # Must be None for hourly calculation type
            hourly_rate=Decimal('50.00'),
            calculation_type='hourly'
        )
    
    def test_calculate_salary_unauthenticated(self):
        """Test salary calculation without authentication - SKIPPED: endpoint not implemented"""
        self.skipTest("salary-calculate endpoint not implemented yet")