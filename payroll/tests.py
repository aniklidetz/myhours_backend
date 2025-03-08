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
            currency="NIS"
        )
        
        # Create some work logs for this employee
        check_in = timezone.now() - timezone.timedelta(days=1)
        WorkLog.objects.create(
            employee=self.employee,
            check_in=check_in,
            check_out=check_in + timezone.timedelta(hours=8)
        )
        
    def test_salary_calculation(self):
        self.salary.calculate_salary()
        
        # With 8 hours at rate 50, salary should be 400
        self.assertEqual(self.salary.calculated_salary, Decimal('400.00'))
        
    def test_salary_with_bonus_and_deductions(self):
        self.salary.bonus = Decimal('100.00')
        self.salary.deductions = Decimal('50.00')
        self.salary.save()
        
        self.salary.calculate_salary()
        
        # 400 + 100 - 50 = 450
        self.assertEqual(self.salary.calculated_salary, Decimal('450.00'))


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