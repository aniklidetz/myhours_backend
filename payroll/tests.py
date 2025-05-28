from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from django.utils import timezone
from users.models import Employee
from worktime.models import WorkLog
from payroll.models import Salary
from decimal import Decimal


class SalaryModelTest(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            first_name="John",
            last_name="Doe",
            email="john.doe@example.com",
            employment_type="hourly"
        )
        
        self.salary = Salary.objects.create(
            employee=self.employee,
            base_salary=Decimal('0.00'),
            hourly_rate=Decimal('50.00'),
            currency="ILS"
        )
        
        # Create a work log for this employee
        check_in = timezone.now() - timezone.timedelta(days=1)
        WorkLog.objects.create(
            employee=self.employee,
            check_in=check_in,
            check_out=check_in + timezone.timedelta(hours=8)
        )
        
    def test_salary_calculation(self):
        # Create a work log in the current month and year to ensure correct calculation
        now = timezone.now()
        check_in = timezone.datetime(now.year, now.month, now.day, 9, 0)  # 9:00 AM
        check_out = timezone.datetime(now.year, now.month, now.day, 17, 0)  # 5:00 PM (8 hours)
        
        WorkLog.objects.create(
            employee=self.employee,
            check_in=check_in,
            check_out=check_out
        )
        
        # Now run the calculation
        result = self.salary.calculate_salary()
        
        # With 8 hours at rate 50, the salary should be 400
        self.assertEqual(result, Decimal('400.00'))
        
    def test_hourly_salary_calculation(self):
        # Get current month and year
        now = timezone.now()
        
        # Create a work log in the current month
        check_in = timezone.datetime(now.year, now.month, now.day, 9, 0)
        check_out = timezone.datetime(now.year, now.month, now.day, 17, 0)  # 8 hours
        
        WorkLog.objects.create(
            employee=self.employee,
            check_in=check_in,
            check_out=check_out
        )
        
        # Call the hourly salary calculation method directly
        result = self.salary._calculate_hourly_salary(now.month, now.year)
        
        # Check the result
        self.assertEqual(result['total_salary'], Decimal('400.00'))
        self.assertEqual(result['regular_hours'], 8)


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
            hourly_rate=Decimal('50.00'),
            base_salary=Decimal('0.00')
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
        
        # Make sure the response includes at least a message
        self.assertIn('message', response.data)