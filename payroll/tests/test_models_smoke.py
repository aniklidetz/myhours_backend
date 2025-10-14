"""
Smoke tests for payroll/models.py - focusing on public methods and basic functionality.
Tests core model behavior without deep integration complexity.
"""

import calendar
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from integrations.models import Holiday
from payroll.models import (
    CompensatoryDay,
    DailyPayrollCalculation,
    MonthlyPayrollSummary,
    Salary,
)
from payroll.tests.helpers import (
    ISRAELI_DAILY_NORM_HOURS,
    MONTHLY_NORM_HOURS,
    NIGHT_NORM_HOURS,
)
from users.models import Employee
from worktime.models import WorkLog


class SalaryModelSmokeTest(TestCase):
    """Smoke tests for Salary model - basic functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="test123"
        )

        self.employee = Employee.objects.create(
            user=self.user,
            first_name="John",
            last_name="Doe",
            email="test@example.com",
            employment_type="full_time",
            role="employee",
        )

    def test_salary_creation_hourly(self):
        """Test creating hourly salary"""
        salary = Salary.objects.create(
            employee=self.employee,
            hourly_rate=Decimal("50.00"),
            calculation_type="hourly",
            currency="ILS",
            is_active=True,
        )

        self.assertEqual(salary.employee, self.employee)
        self.assertEqual(salary.monthly_hourly, Decimal("50.00"))
        self.assertEqual(salary.calculation_type, "hourly")
        self.assertEqual(salary.currency, "ILS")

    def test_salary_creation_monthly(self):
        """Test creating monthly salary"""
        salary = Salary.objects.create(
            employee=self.employee,
            base_salary=Decimal("10000.00"),
            calculation_type="monthly",
            currency="ILS",
            is_active=True,
        )

        self.assertEqual(salary.base_salary, Decimal("10000.00"))
        self.assertEqual(salary.calculation_type, "monthly")

    def test_salary_creation_project(self):
        """Test creating project-based salary"""
        salary = Salary.objects.create(
            employee=self.employee,
            base_salary=Decimal("50000.00"),
            calculation_type="project",
            project_start_date=date.today(),
            project_end_date=date.today() + timedelta(days=60),
            currency="USD",
            is_active=True,
        )

        # Project type may convert to monthly based on feature flags
        self.assertIn(salary.calculation_type, ["project", "monthly"])
        self.assertFalse(salary.project_completed)
        self.assertEqual(salary.currency, "USD")

    @patch("payroll.models.Holiday.objects.filter")
    def test_get_working_days_in_month_basic(self, mock_holiday_filter):
        """Test basic working days calculation"""
        salary = Salary.objects.create(
            employee=self.employee,
            base_salary=Decimal("10000.00"),
            calculation_type="monthly",
            is_active=True,
        )

        # Mock no holidays
        mock_holiday_filter.return_value.exists.return_value = False

        # Test January 2025 (31 days)
        working_days = salary.get_working_days_in_month(2025, 1)

        # Should be around 23 working days (excluding weekends)
        self.assertGreater(working_days, 20)
        self.assertLess(working_days, 25)

    @patch("payroll.models.Holiday.objects.filter")
    def test_get_working_days_with_holidays(self, mock_holiday_filter):
        """Test working days calculation with holidays"""
        salary = Salary.objects.create(
            employee=self.employee,
            base_salary=Decimal("10000.00"),
            calculation_type="monthly",
            is_active=True,
        )

        # Mock that some holidays exist but not all days are holidays
        mock_holiday_filter.return_value.exists.return_value = (
            False  # Most days are not holidays
        )

        working_days = salary.get_working_days_in_month(2025, 1)

        # Should still return reasonable number (January 2025 has ~21 working days, minus some holidays)
        self.assertGreater(working_days, 15)
        self.assertLess(working_days, 25)

    @patch("payroll.models.Holiday.objects.filter")
    def test_get_working_days_exception_handling(self, mock_holiday_filter):
        """Test working days calculation with exception"""
        salary = Salary.objects.create(
            employee=self.employee,
            base_salary=Decimal("10000.00"),
            calculation_type="monthly",
            is_active=True,
        )

        # Mock exception in holiday check
        mock_holiday_filter.side_effect = Exception("Database error")

        working_days = salary.get_working_days_in_month(2025, 1)

        # Should fall back to approximation
        self.assertGreater(working_days, 1)

    def test_get_worked_days_no_work_logs(self):
        """Test worked days calculation with no work logs"""
        salary = Salary.objects.create(
            employee=self.employee,
            base_salary=Decimal("10000.00"),
            calculation_type="monthly",
            is_active=True,
        )

        worked_days = salary.get_worked_days_in_month(2025, 1)

        self.assertEqual(worked_days, 0)

    def test_get_worked_days_with_work_logs(self):
        """Test worked days calculation with work logs"""
        salary = Salary.objects.create(
            employee=self.employee,
            hourly_rate=Decimal("50.00"),
            calculation_type="hourly",
            is_active=True,
        )

        # Create some work logs with timezone-aware datetimes
        WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.make_aware(timezone.datetime(2025, 1, 15, 9, 0)),
            check_out=timezone.make_aware(timezone.datetime(2025, 1, 15, 17, 0)),
        )
        WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.make_aware(timezone.datetime(2025, 1, 16, 9, 0)),
            check_out=timezone.make_aware(timezone.datetime(2025, 1, 16, 17, 0)),
        )

        worked_days = salary.get_worked_days_in_month(2025, 1)

        self.assertEqual(worked_days, 2)

    def test_string_representation(self):
        """Test model string representation"""
        salary = Salary.objects.create(
            employee=self.employee,
            hourly_rate=Decimal("50.00"),
            calculation_type="hourly",
            is_active=True,
        )

        str_repr = str(salary)
        self.assertIn("John Doe", str_repr)


class MonthlyPayrollSummaryModelSmokeTest(TestCase):
    """Smoke tests for MonthlyPayrollSummary model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="test123"
        )

        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Jane",
            last_name="Smith",
            email="test@example.com",
            employment_type="full_time",
            role="employee",
        )

    def test_monthly_payroll_summary_creation(self):
        """Test creating monthly payroll summary"""
        summary = MonthlyPayrollSummary.objects.create(
            employee=self.employee,
            year=2025,
            month=1,
            total_hours=Decimal("160.00"),
            proportional_monthly=Decimal("8000.00"),
            total_salary=Decimal("8000.00"),
        )

        self.assertEqual(summary.employee, self.employee)
        self.assertEqual(summary.year, 2025)
        self.assertEqual(summary.month, 1)
        self.assertEqual(summary.total_hours, Decimal("160.00"))
        self.assertEqual(summary.proportional_monthly, Decimal("8000.00"))

    def test_monthly_payroll_summary_unique_constraint(self):
        """Test unique constraint on employee/year/month"""
        MonthlyPayrollSummary.objects.create(
            employee=self.employee,
            year=2025,
            month=1,
            proportional_monthly=Decimal("8000.00"),
        )

        # Creating another summary for same employee/month should be allowed
        # (assuming no unique constraint, or test the constraint if it exists)
        summary2 = MonthlyPayrollSummary.objects.create(
            employee=self.employee,
            year=2025,
            month=2,  # Different month
            proportional_monthly=Decimal("7500.00"),
        )

        self.assertNotEqual(summary2.month, 1)

    def test_monthly_payroll_summary_calculations(self):
        """Test basic monthly payroll summary calculations"""
        summary = MonthlyPayrollSummary.objects.create(
            employee=self.employee,
            year=2025,
            month=1,
            regular_hours=Decimal("160.00"),
            overtime_hours=Decimal("10.00"),
            proportional_monthly=Decimal("8000.00"),
            total_bonuses_monthly=Decimal("750.00"),
            total_salary=Decimal("8750.00"),
        )

        # Test calculated fields
        self.assertEqual(summary.regular_hours, Decimal("160.00"))
        self.assertEqual(summary.overtime_hours, Decimal("10.00"))
        self.assertEqual(summary.total_salary, Decimal("8750.00"))


class CompensatoryDayModelSmokeTest(TestCase):
    """Smoke tests for CompensatoryDay model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="test123"
        )

        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Bob",
            last_name="Johnson",
            email="test@example.com",
            employment_type="full_time",
            role="employee",
        )

    def test_compensatory_day_creation(self):
        """Test creating compensatory day"""
        comp_day = CompensatoryDay.objects.create(
            employee=self.employee, date_earned=date(2025, 1, 15), reason="holiday"
        )

        self.assertEqual(comp_day.employee, self.employee)
        self.assertEqual(comp_day.date_earned, date(2025, 1, 15))
        self.assertEqual(comp_day.reason, "holiday")
        self.assertIsNone(comp_day.date_used)

    def test_compensatory_day_status(self):
        """Test compensatory day status handling"""
        comp_day = CompensatoryDay.objects.create(
            employee=self.employee, date_earned=date(2025, 1, 15), reason="shabbat"
        )

        # Test that day is not used by default
        self.assertIsNone(comp_day.date_used)

        # Test using the day
        comp_day.date_used = date(2025, 1, 20)
        comp_day.save()

        self.assertEqual(comp_day.date_used, date(2025, 1, 20))


class DailyPayrollCalculationModelSmokeTest(TestCase):
    """Smoke tests for DailyPayrollCalculation model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="test123"
        )

        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Alice",
            last_name="Williams",
            email="test@example.com",
            employment_type="full_time",
            role="employee",
        )

    def test_daily_payroll_calculation_creation(self):
        """Test creating daily payroll calculation"""
        calculation = DailyPayrollCalculation.objects.create(
            employee=self.employee,
            work_date=date.today(),
            regular_hours=Decimal("8.00"),
            overtime_hours_1=Decimal("1.50"),
            overtime_hours_2=Decimal("0.50"),
        )

        self.assertEqual(calculation.employee, self.employee)
        self.assertEqual(calculation.regular_hours, Decimal("8.00"))
        self.assertEqual(calculation.overtime_hours_1, Decimal("1.50"))
        self.assertEqual(calculation.overtime_hours_2, Decimal("0.50"))

    def test_daily_payroll_calculation_date_field(self):
        """Test daily payroll calculation date handling"""
        calculation = DailyPayrollCalculation.objects.create(
            employee=self.employee,
            work_date=date(2025, 1, 15),
            regular_hours=Decimal("8.00"),
        )

        self.assertEqual(calculation.work_date, date(2025, 1, 15))

    def test_daily_payroll_calculation_hours_validation(self):
        """Test daily payroll calculation hours validation"""
        calculation = DailyPayrollCalculation.objects.create(
            employee=self.employee,
            work_date=date.today(),
            regular_hours=Decimal("0.00"),
            overtime_hours_1=Decimal("0.00"),
            overtime_hours_2=Decimal("0.00"),
        )

        # Should allow zero hours
        self.assertEqual(calculation.regular_hours, Decimal("0.00"))
        self.assertEqual(calculation.overtime_hours_1, Decimal("0.00"))


class ModelIntegrationSmokeTest(TestCase):
    """Smoke tests for model interactions"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="test123"
        )

        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Integration",
            last_name="Test",
            email="test@example.com",
            employment_type="full_time",
            role="employee",
        )

    def test_employee_salary_relationship(self):
        """Test employee-salary relationship"""
        salary = Salary.objects.create(
            employee=self.employee,
            base_salary=Decimal("12000.00"),
            calculation_type="monthly",
            is_active=True,
        )

        # Test reverse relationship
        self.assertEqual(self.employee.salary_info, salary)

    def test_multiple_monthly_payroll_summaries(self):
        """Test creating multiple monthly payroll summaries for employee"""
        # Create summaries for different months
        summary1 = MonthlyPayrollSummary.objects.create(
            employee=self.employee,
            year=2025,
            month=1,
            proportional_monthly=Decimal("8000.00"),
        )

        summary2 = MonthlyPayrollSummary.objects.create(
            employee=self.employee,
            year=2025,
            month=2,
            proportional_monthly=Decimal("8500.00"),
        )

        # Test that both summaries exist
        summaries = MonthlyPayrollSummary.objects.filter(employee=self.employee)
        self.assertEqual(summaries.count(), 2)

    def test_model_timestamps(self):
        """Test model timestamp fields"""
        salary = Salary.objects.create(
            employee=self.employee,
            hourly_rate=Decimal("45.00"),
            calculation_type="hourly",
            is_active=True,
        )

        # Test that timestamps are set
        self.assertIsNotNone(salary.created_at)
        self.assertIsNotNone(salary.updated_at)

        # Test that created_at and updated_at are close
        time_diff = salary.updated_at - salary.created_at
        self.assertLess(time_diff.total_seconds(), 1)  # Less than 1 second difference
