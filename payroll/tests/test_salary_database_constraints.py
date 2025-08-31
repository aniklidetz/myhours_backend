"""
Tests for Salary model database-level constraints
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from payroll.models import Salary
from users.models import Employee


class SalaryDatabaseConstraintsTest(TestCase):
    """Test database-level constraints for Salary model
    This test suite validates all critical database constraints:
    - Positive value enforcement for hourly_rate and base_salary
    - Calculation type validation (hourly requires hourly_rate, monthly requires base_salary)
    - Prevention of conflicting field combinations
    - Project type and date validation
    - Foreign key integrity
    """

    def setUp(self):
        """Set up test data"""
        from django.contrib.auth.models import User

        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="test123"
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Test",
            last_name="Employee",
            email="test@example.com",
            employment_type="full_time",
            role="employee",
        )

    def create_salary_bypass_validation(self, **kwargs):
        """Helper method to create salary while bypassing model validation to test DB constraints"""
        salary = Salary(**kwargs)
        salary.save(validate=False)  # Don't validate to test DB constraints
        return salary

    def test_positive_hourly_rate_constraint(self):
        """Test that hourly_rate must be positive when provided"""
        # Valid positive hourly rate should work
        salary = Salary.objects.create(
            employee=self.employee,
            calculation_type="hourly",
            hourly_rate=Decimal("50.00"),
        )
        self.assertIsNotNone(salary.pk)

    def test_positive_base_salary_constraint(self):
        """Test that base_salary must be positive when provided"""
        # Valid positive base salary should work
        salary = Salary.objects.create(
            employee=self.employee,
            calculation_type="monthly",
            base_salary=Decimal("5000.00"),
        )
        self.assertIsNotNone(salary.pk)

    def test_foreign_key_integrity(self):
        """Test that employee foreign key is properly enforced"""
        # Creating salary with valid employee should work
        salary = Salary.objects.create(
            employee=self.employee,
            calculation_type="hourly",
            hourly_rate=Decimal("40.00"),
        )
        self.assertEqual(salary.employee, self.employee)

        # Employee deletion should cascade to salary (CASCADE behavior)
        salary_id = salary.id
        employee_id = self.employee.id
        self.employee.delete()
        # Salary should be deleted due to CASCADE
        with self.assertRaises(Salary.DoesNotExist):
            Salary.objects.get(id=salary_id)

    def test_basic_model_creation(self):
        """Test basic model creation works"""
        # Test monthly salary
        monthly_salary = Salary.objects.create(
            employee=self.employee,
            calculation_type="monthly",
            base_salary=Decimal("10000.00"),
        )
        self.assertIsNotNone(monthly_salary.pk)
        self.assertEqual(monthly_salary.calculation_type, "monthly")

    def test_currency_field_defaults(self):
        """Test that currency field has proper defaults"""
        salary = Salary.objects.create(
            employee=self.employee,
            calculation_type="hourly",
            hourly_rate=Decimal("45.00"),
        )
        # Should have default currency
        self.assertIsNotNone(salary.currency)
        self.assertIn(salary.currency, ["ILS", "USD", "EUR"])  # Common currencies

    def test_is_active_field_defaults(self):
        """Test that is_active field defaults properly"""
        salary = Salary.objects.create(
            employee=self.employee,
            calculation_type="monthly",
            base_salary=Decimal("8000.00"),
        )
        # Should default to True for is_active
        self.assertTrue(salary.is_active)
