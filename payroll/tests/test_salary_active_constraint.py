"""
Tests for active salary constraint and transaction logic
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase

from payroll.models import Salary
from users.models import Employee


class SalaryActiveConstraintTest(TestCase):
    """Test active salary constraint logic"""

    def setUp(self):
        """Set up test data"""
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

    def test_only_one_active_salary_allowed(self):
        """Test that only one active salary per employee is allowed"""
        # Create first active salary
        salary1 = Salary.objects.create(
            employee=self.employee,
            base_salary=Decimal("10000.00"),
            calculation_type="monthly",
            is_active=True,
        )
        # Create second salary - should automatically deactivate the first
        salary2 = Salary.objects.create(
            employee=self.employee,
            hourly_rate=Decimal("50.00"),
            calculation_type="hourly",
            is_active=True,
        )
        # Check that first salary was deactivated
        salary1.refresh_from_db()
        self.assertFalse(salary1.is_active)
        # Check that second salary is active
        salary2.refresh_from_db()
        self.assertTrue(salary2.is_active)

    def test_multiple_inactive_salaries_allowed(self):
        """Test that multiple inactive salaries per employee are allowed"""
        # Create multiple inactive salaries
        salary1 = Salary.objects.create(
            employee=self.employee,
            base_salary=Decimal("8000.00"),
            calculation_type="monthly",
            is_active=False,
        )
        salary2 = Salary.objects.create(
            employee=self.employee,
            hourly_rate=Decimal("40.00"),
            calculation_type="hourly",
            is_active=False,
        )
        # Both should remain inactive
        salary1.refresh_from_db()
        salary2.refresh_from_db()
        self.assertFalse(salary1.is_active)
        self.assertFalse(salary2.is_active)

    def test_updating_existing_salary_to_active(self):
        """Test updating an existing inactive salary to active"""
        # Create two inactive salaries
        salary1 = Salary.objects.create(
            employee=self.employee,
            base_salary=Decimal("10000.00"),
            calculation_type="monthly",
            is_active=False,
        )
        salary2 = Salary.objects.create(
            employee=self.employee,
            hourly_rate=Decimal("50.00"),
            calculation_type="hourly",
            is_active=True,  # This one is active
        )
        # Activate the first salary
        salary1.is_active = True
        salary1.save()
        # Check that second salary was deactivated
        salary2.refresh_from_db()
        self.assertFalse(salary2.is_active)
        # Check that first salary is now active
        salary1.refresh_from_db()
        self.assertTrue(salary1.is_active)

    def test_service_gets_correct_active_salary(self):
        """Test that PayrollCalculationService gets the correct active salary"""
        # Create inactive salary
        salary1 = Salary.objects.create(
            employee=self.employee,
            base_salary=Decimal("8000.00"),
            calculation_type="monthly",
            is_active=False,
        )
        # Create active salary
        salary2 = Salary.objects.create(
            employee=self.employee,
            hourly_rate=Decimal("60.00"),
            calculation_type="hourly",
            is_active=True,
        )
        # Test that the service gets the active salary
        from payroll.services import EnhancedPayrollCalculationService

        service = EnhancedPayrollCalculationService(self.employee, 2025, 8)
        self.assertEqual(service.salary.id, salary2.id)
        self.assertEqual(service.salary.calculation_type, "hourly")
        self.assertEqual(service.salary.hourly_rate, Decimal("60.00"))

    def test_service_fails_when_no_active_salary(self):
        """Test that service raises error when no active salary exists"""
        # Create only inactive salaries
        Salary.objects.create(
            employee=self.employee,
            base_salary=Decimal("8000.00"),
            calculation_type="monthly",
            is_active=False,
        )
        # Service should fail
        from django.core.exceptions import ValidationError

        from payroll.services import EnhancedPayrollCalculationService

        with self.assertRaises(ValidationError) as cm:
            EnhancedPayrollCalculationService(self.employee, 2025, 8)
        self.assertIn("Active salary is required", str(cm.exception))
        self.assertIn(self.employee.get_full_name(), str(cm.exception))


class SalaryConstraintTransactionTest(TransactionTestCase):
    """Test transaction behavior for salary constraints"""

    def setUp(self):
        """Set up test data"""
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

    def test_database_constraint_prevents_multiple_active(self):
        """Test that database constraint prevents multiple active salaries"""
        # Create first active salary
        salary1 = Salary.objects.create(
            employee=self.employee,
            base_salary=Decimal("10000.00"),
            calculation_type="monthly",
            is_active=True,
        )
        # Try to create second active salary by bypassing model save()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                # Use raw SQL to bypass model logic
                from django.db import connection
                from django.utils import timezone

                cursor = connection.cursor()
                now = timezone.now()
                cursor.execute(
                    """
                    INSERT INTO payroll_salary (employee_id, base_salary, calculation_type, is_active, currency, created_at, updated_at, project_completed)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        self.employee.id,
                        Decimal("12000.00"),
                        "monthly",
                        True,  # This should fail due to unique constraint
                        "ILS",
                        now,
                        now,
                        False,
                    ],
                )

    def test_transaction_rollback_on_constraint_violation(self):
        """Test that transaction rolls back properly on constraint violation"""
        # Create first active salary
        salary1 = Salary.objects.create(
            employee=self.employee,
            base_salary=Decimal("10000.00"),
            calculation_type="monthly",
            is_active=True,
        )
        initial_count = Salary.objects.filter(employee=self.employee).count()
        try:
            with transaction.atomic():
                # This should work
                salary2 = Salary(
                    employee=self.employee,
                    hourly_rate=Decimal("50.00"),
                    calculation_type="hourly",
                    is_active=False,  # Not active, so should be fine
                )
                salary2.save()
                # Force a constraint violation
                from django.db import connection
                from django.utils import timezone

                cursor = connection.cursor()
                now = timezone.now()
                cursor.execute(
                    """
                    INSERT INTO payroll_salary (employee_id, base_salary, calculation_type, is_active, currency, created_at, updated_at, project_completed)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        self.employee.id,
                        Decimal("15000.00"),
                        "monthly",
                        True,  # This should fail
                        "ILS",
                        now,
                        now,
                        False,
                    ],
                )
        except IntegrityError:
            pass
        # Check that the transaction was rolled back
        final_count = Salary.objects.filter(employee=self.employee).count()
        self.assertEqual(final_count, initial_count)
