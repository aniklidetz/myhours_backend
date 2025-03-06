from core.test_utils import create_test_employee
from django.test import TestCase
from django.utils import timezone
from decimal import Decimal
from core.models import Employee, WorkLog, Salary

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
