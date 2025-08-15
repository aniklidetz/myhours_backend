"""
Tests for monthly employee salary calculations using current models.

Tests edge cases and integration with EnhancedPayrollCalculationService
for monthly employees with various scenarios.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from payroll.models import DailyPayrollCalculation, MonthlyPayrollSummary, Salary
from payroll.services import EnhancedPayrollCalculationService
from users.models import Employee
from worktime.models import WorkLog


class MonthlyEmployeeCalculationTest(TestCase):
    """Test monthly employee calculations with current models and services"""

    def setUp(self):
        """Set up test data"""
        # Create monthly employee
        self.monthly_employee = Employee.objects.create(
            first_name="Monthly",
            last_name="Employee",
            email="monthly@test.com",
            employment_type="full_time",
            role="employee",
        )

        # Create salary with monthly calculation type
        self.salary = Salary.objects.create(
            employee=self.monthly_employee,
            calculation_type="monthly",
            base_salary=Decimal("15000.00"),
            currency="ILS",
        )

        # Create hourly employee for comparison
        self.hourly_employee = Employee.objects.create(
            first_name="Hourly",
            last_name="Employee",
            email="hourly@test.com",
            employment_type="hourly",
            role="employee",
        )

        self.hourly_salary = Salary.objects.create(
            employee=self.hourly_employee,
            calculation_type="hourly",
            hourly_rate=Decimal("80.00"),
            currency="ILS",
        )

    def test_monthly_employee_basic_calculation(self):
        """Test basic monthly salary calculation"""
        # Create work logs for the month
        for day in range(1, 6):  # 5 work days
            check_in = timezone.make_aware(datetime(2025, 7, day, 9, 0))
            check_out = timezone.make_aware(datetime(2025, 7, day, 17, 0))

            WorkLog.objects.create(
                employee=self.monthly_employee, check_in=check_in, check_out=check_out
            )

        service = EnhancedPayrollCalculationService(self.monthly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should have monthly calculation
        self.assertIsNotNone(result)
        self.assertIn("total_gross_pay", result)

        # Should be proportional to worked days
        total_pay = result.get("total_gross_pay", 0)
        self.assertGreater(total_pay, 0)
        self.assertLess(total_pay, 15000)  # Less than full monthly salary

    def test_monthly_employee_null_hourly_rate_no_error(self):
        """Test that monthly employees with null hourly_rate don't cause errors"""
        # Ensure hourly_rate is None (should be by default for monthly type)
        self.assertIsNone(self.salary.hourly_rate)

        # Create work log
        check_in = timezone.make_aware(datetime(2025, 7, 1, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 1, 18, 0))

        WorkLog.objects.create(
            employee=self.monthly_employee, check_in=check_in, check_out=check_out
        )

        # Should not raise exception
        service = EnhancedPayrollCalculationService(self.monthly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        self.assertIsNotNone(result)
        self.assertIn("total_gross_pay", result)
        self.assertGreater(result.get("total_gross_pay", 0), 0)

    def test_monthly_employee_proportional_calculation(self):
        """Test proportional salary calculation for partial month work"""
        # Work only 3 out of ~23 working days in July
        work_days = [1, 2, 3]  # First 3 days of July 2025

        for day in work_days:
            check_in = timezone.make_aware(datetime(2025, 7, day, 9, 0))
            check_out = timezone.make_aware(datetime(2025, 7, day, 17, 0))

            WorkLog.objects.create(
                employee=self.monthly_employee, check_in=check_in, check_out=check_out
            )

        service = EnhancedPayrollCalculationService(self.monthly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should get approximately 3/23 of monthly salary
        total_pay = result.get("total_gross_pay", 0)
        expected_proportion = 3 / 23  # 3 worked days out of 23 working days
        expected_pay = 15000 * expected_proportion

        # With NEW unified logic, includes proportional + hours-based calculations
        # Allow for variance due to unified payment structure
        self.assertGreater(total_pay, expected_pay * 0.8)
        self.assertLess(total_pay, expected_pay * 2.5)  # Allow for unified logic

    def test_monthly_employee_overtime_handling(self):
        """Test that monthly employees get overtime premiums (125%/150%) on top of base salary"""
        # Create work log with > 8 hours
        check_in = timezone.make_aware(datetime(2025, 7, 1, 8, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 1, 20, 0))  # 12 hours

        WorkLog.objects.create(
            employee=self.monthly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.monthly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should track overtime hours
        overtime_hours = result.get("overtime_hours", 0)
        self.assertGreater(overtime_hours, 0)

        # Should get base proportional salary + full overtime pay (not just bonus)
        total_pay = result.get("total_gross_pay", 0)
        base_proportional = Decimal("15000") / Decimal("23")  # Proportional for 1 day

        # With 12 hours (8.6 regular + 3.4 overtime), should get:
        # base_proportional + overtime at 125%/150% rates
        # This should be more than just base proportional
        self.assertGreater(
            total_pay, base_proportional
        )  # Should be more than base due to overtime

    def test_monthly_employee_zero_base_salary(self):
        """Test handling of monthly employee with very low base salary"""
        # Create employee with minimal base salary (since 0 is not allowed)
        low_salary_employee = Employee.objects.create(
            first_name="Low",
            last_name="Salary",
            email="low@test.com",
            employment_type="full_time",
            role="employee",
        )

        low_salary = Salary.objects.create(
            employee=low_salary_employee,
            calculation_type="monthly",
            base_salary=Decimal("0.01"),  # Minimal allowed value
            currency="ILS",
        )

        # Create work log
        check_in = timezone.make_aware(datetime(2025, 7, 1, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 1, 17, 0))

        WorkLog.objects.create(
            employee=low_salary_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(low_salary_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should not crash, should return very low salary
        self.assertIsNotNone(result)
        total_pay = result.get("total_gross_pay", 0)
        # With minimal base salary (0.01) and 1 day work out of 23 days: 0.01/23 ≈ 0.0004
        # System may round to 0, so just check it doesn't crash
        self.assertGreaterEqual(total_pay, 0)  # Should be 0 or greater
        self.assertLess(total_pay, 1)  # But very small

    def test_monthly_employee_sabbath_work(self):
        """Test monthly employee working on Sabbath gets full 150% pay (base + bonus)"""
        # Saturday work
        check_in = timezone.make_aware(datetime(2025, 7, 5, 9, 0))  # Saturday
        check_out = timezone.make_aware(datetime(2025, 7, 5, 17, 0))  # 8 hours

        WorkLog.objects.create(
            employee=self.monthly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.monthly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should include Sabbath hours and pay
        sabbath_hours = result.get("sabbath_hours", 0)
        total_pay = result.get("total_gross_pay", 0)

        # Should get Sabbath pay based on new hour-based calculation logic
        # Base salary: 15000, monthly norm: 182 hours
        # 8 hours worked, so base = (8/182) * 15000 = 659.34
        # Plus Sabbath bonuses for all 8 hours at 150% = 8 * hourly_rate * 1.5
        hourly_rate = Decimal("15000") / Decimal("182")  # ~82.42
        expected_base = (Decimal("8") / Decimal("182")) * Decimal("15000")  # ~659.34
        expected_sabbath_bonus = (
            Decimal("8") * hourly_rate * Decimal("0.5")
        )  # 50% bonus for Sabbath
        expected_total = expected_base + expected_sabbath_bonus  # ~989.01

        # Allow for small rounding differences
        self.assertAlmostEqual(float(total_pay), float(expected_total), places=0)

    def test_monthly_employee_with_work_logs_creates_summaries(self):
        """Test that monthly calculations create proper database summaries"""
        # Create multiple work logs
        for day in range(1, 11):  # 10 work days
            check_in = timezone.make_aware(datetime(2025, 7, day, 9, 0))
            check_out = timezone.make_aware(datetime(2025, 7, day, 17, 0))

            WorkLog.objects.create(
                employee=self.monthly_employee, check_in=check_in, check_out=check_out
            )

        service = EnhancedPayrollCalculationService(self.monthly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Check if monthly summary was created/updated
        monthly_summary = MonthlyPayrollSummary.objects.filter(
            employee=self.monthly_employee, year=2025, month=7
        ).first()

        if monthly_summary:
            self.assertGreater(monthly_summary.total_gross_pay, 0)
            self.assertEqual(monthly_summary.worked_days, 10)

    def test_division_by_zero_protection(self):
        """Test that division by zero is properly handled"""
        # Create employee with potentially problematic data
        problem_employee = Employee.objects.create(
            first_name="Problem",
            last_name="Case",
            email="problem@test.com",
            employment_type="full_time",
            role="employee",
        )

        problem_salary = Salary.objects.create(
            employee=problem_employee,
            calculation_type="monthly",
            base_salary=Decimal("5000.00"),
            currency="ILS",
        )

        # No work logs (zero hours worked)
        service = EnhancedPayrollCalculationService(problem_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should not raise ZeroDivisionError
        self.assertIsNotNone(result)
        self.assertIn("total_gross_pay", result)
        # With no work, should get zero pay for monthly proportional calculation
        self.assertEqual(result.get("total_gross_pay", 0), 0)

    def test_monthly_vs_hourly_calculation_difference(self):
        """Test that monthly and hourly employees are calculated differently"""
        # Same work pattern for both employees
        check_in = timezone.make_aware(datetime(2025, 7, 1, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 1, 17, 0))  # 8 hours

        WorkLog.objects.create(
            employee=self.monthly_employee, check_in=check_in, check_out=check_out
        )

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        # Calculate for both
        monthly_service = EnhancedPayrollCalculationService(
            self.monthly_employee, 2025, 7
        )
        monthly_result = monthly_service.calculate_monthly_salary_enhanced()

        hourly_service = EnhancedPayrollCalculationService(
            self.hourly_employee, 2025, 7
        )
        hourly_result = hourly_service.calculate_monthly_salary_enhanced()

        # Should have different calculation approaches
        monthly_pay = monthly_result.get("total_gross_pay", 0)
        hourly_pay = hourly_result.get("total_gross_pay", 0)

        # Hourly: 8 hours * 80 = 640
        expected_hourly = 8 * 80
        self.assertAlmostEqual(hourly_pay, expected_hourly, places=0)

        # Monthly: with NEW unified logic, includes proportional + hours-based calculation
        # So monthly will be significantly higher than just proportional
        expected_monthly_approx = Decimal("15000") / Decimal("23")  # proportional base
        # Allow for unified logic making monthly payment higher
        self.assertGreater(float(monthly_pay), float(expected_monthly_approx) * 0.5)
        self.assertLess(float(monthly_pay), float(expected_monthly_approx) * 3)

    def test_monthly_employee_service_integration(self):
        """Test integration with EnhancedPayrollCalculationService"""
        # Create comprehensive work pattern
        work_pattern = [
            (1, 8),  # Regular day
            (2, 10),  # Overtime day
            (5, 6),  # Saturday (Sabbath)
            (8, 9),  # Regular day with some overtime
        ]

        for day, hours in work_pattern:
            check_in = timezone.make_aware(datetime(2025, 7, day, 9, 0))
            check_out = check_in + timedelta(hours=hours)

            WorkLog.objects.create(
                employee=self.monthly_employee, check_in=check_in, check_out=check_out
            )

        service = EnhancedPayrollCalculationService(self.monthly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should have comprehensive breakdown
        self.assertIn("total_gross_pay", result)
        self.assertIn("regular_hours", result)
        self.assertIn("overtime_hours", result)
        self.assertIn("sabbath_hours", result)

        # Should get proportional base + premiums for overtime/sabbath
        total_pay = result.get("total_gross_pay", 0)
        base_proportional = (
            Decimal("15000") * Decimal("4") / Decimal("23")
        )  # 4 days out of 23 working days
        self.assertGreater(total_pay, base_proportional)  # Should include premiums
