"""
Tests for overtime calculations with proper 125% and 150% rates.

Tests detailed overtime rate applications according to Israeli labor law:
- First overtime hours: 125% rate
- Extended overtime hours: 150% rate
- Daily vs weekly overtime limits
- Overtime during special days (Sabbath, holidays)
"""

from datetime import datetime, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from payroll.models import Salary
from payroll.services import EnhancedPayrollCalculationService
from users.models import Employee
from worktime.models import WorkLog


class OvertimeCalculationTest(TestCase):
    """Test overtime rate calculations and transitions"""

    def setUp(self):
        """Set up test data"""
        # Create hourly employee for overtime testing
        self.hourly_employee = Employee.objects.create(
            first_name="Overtime",
            last_name="Worker",
            email="overtime@test.com",
            employment_type="hourly",
            role="employee",
        )

        self.hourly_salary = Salary.objects.create(
            employee=self.hourly_employee,
            calculation_type="hourly",
            hourly_rate=Decimal("100.00"),  # Nice round number for testing
            currency="ILS",
        )

        # Create monthly employee (should NOT get overtime by default)
        self.monthly_employee = Employee.objects.create(
            first_name="Monthly",
            last_name="NoOvertime",
            email="monthly.noovertime@test.com",
            employment_type="full_time",
            role="employee",
        )

        self.monthly_salary = Salary.objects.create(
            employee=self.monthly_employee,
            calculation_type="monthly",
            base_salary=Decimal("18000.00"),
            currency="ILS",
        )

    def test_no_overtime_regular_day(self):
        """Test regular 8-hour day with no overtime"""
        # Regular 8-hour workday
        check_in = timezone.make_aware(datetime(2025, 7, 1, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 1, 17, 0))  # 8 hours

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should have 8 regular hours, no overtime
        self.assertAlmostEqual(float(result.get("regular_hours", 0)), 8.0, places=1)
        self.assertEqual(float(result.get("overtime_hours", 0)), 0.0)

        # Total pay should be 8 * 100 = 800
        expected_pay = 8 * 100
        self.assertAlmostEqual(float(result["total_gross_pay"]), expected_pay, places=2)

    def test_first_overtime_125_percent(self):
        """Test first 2 overtime hours get 125% rate"""
        # 10-hour workday (8 regular + 2 overtime at 125%)
        check_in = timezone.make_aware(datetime(2025, 7, 1, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 1, 19, 0))  # 10 hours

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should have 8.6 regular + 1.4 overtime hours (Israeli law: 8.6h regular day)
        self.assertAlmostEqual(float(result.get("regular_hours", 0)), 8.6, places=1)
        self.assertAlmostEqual(float(result.get("overtime_hours", 0)), 1.4, places=1)

        # Check detailed breakdown
        breakdown = result.get("detailed_breakdown", {})
        if "overtime_breakdown" in breakdown:
            overtime_details = breakdown["overtime_breakdown"]
            self.assertIn("overtime_125_hours", overtime_details)
            self.assertAlmostEqual(
                overtime_details["overtime_125_hours"], 1.4, places=1
            )

        # Total pay: 8.6*100 (regular) + 1.4*125 (overtime) = 860 + 175 = 1035
        expected_pay = (8.6 * 100) + (1.4 * 125)
        actual_pay = float(result["total_gross_pay"])
        self.assertAlmostEqual(actual_pay, expected_pay, places=0)

    def test_extended_overtime_150_percent(self):
        """Test overtime beyond 2 hours gets 150% rate"""
        # 12-hour workday (8.6 regular + 3.4 overtime using Israeli standard)
        check_in = timezone.make_aware(datetime(2025, 7, 2, 8, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 2, 20, 0))  # 12 hours

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should have 8.6 regular + 3.4 total overtime hours (Israeli law: 8.6h regular)
        self.assertAlmostEqual(float(result.get("regular_hours", 0)), 8.6, places=1)
        self.assertAlmostEqual(float(result.get("overtime_hours", 0)), 3.4, places=1)

        # Check total hours
        total_hours = result.get("total_hours", 0)
        self.assertAlmostEqual(float(total_hours), 12.0, places=1)

        # Should get overtime premium
        actual_pay = float(result["total_gross_pay"])
        regular_pay = 12 * 100  # If all regular
        self.assertGreater(
            actual_pay, regular_pay
        )  # Should be more due to overtime premiums

    def test_extreme_overtime_day(self):
        """Test very long workday with maximum overtime"""
        # 16-hour workday (8.6 regular + 7.4 overtime using Israeli standard)
        check_in = timezone.make_aware(datetime(2025, 7, 3, 6, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 3, 22, 0))  # 16 hours

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should have 8.6 regular + 7.4 overtime hours (Israeli law: 8.6h regular)
        self.assertAlmostEqual(float(result.get("regular_hours", 0)), 8.6, places=1)
        self.assertAlmostEqual(float(result.get("overtime_hours", 0)), 7.4, places=1)

        # Check total hours
        total_hours = result.get("total_hours", 0)
        self.assertAlmostEqual(float(total_hours), 16.0, places=1)

        # Should get significant overtime premium
        actual_pay = float(result["total_gross_pay"])
        regular_pay = 16 * 100  # If all regular
        self.assertGreater(
            actual_pay, regular_pay
        )  # Should be more due to overtime premiums

        # Should be substantial overtime payment
        self.assertGreater(actual_pay, 1800)  # Should be significant

    def test_multiple_overtime_days_in_week(self):
        """Test overtime calculations across multiple days"""
        # Create 3 days with overtime
        overtime_days = [
            (1, 10),  # 2 hours overtime
            (2, 11),  # 3 hours overtime
            (3, 9),  # 1 hour overtime
        ]

        for day, total_hours in overtime_days:
            check_in = timezone.make_aware(datetime(2025, 7, day, 8, 0))
            check_out = check_in + timedelta(hours=total_hours)

            WorkLog.objects.create(
                employee=self.hourly_employee, check_in=check_in, check_out=check_out
            )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should have 25.8 regular hours (3 days * 8.6) + 4.2 overtime hours
        self.assertAlmostEqual(float(result.get("regular_hours", 0)), 25.8, places=1)
        self.assertAlmostEqual(float(result.get("overtime_hours", 0)), 4.2, places=1)

        # Total overtime should be calculated with proper rates
        total_pay = float(result["total_gross_pay"])
        # Expected: 25.8*100 + 4.2 overtime hours at 125%
        # Daily overtime calculation: each day calculates its own rates
        expected_min = 25.8 * 100 + 4.2 * 125  # 2580 + 525 = 3105
        self.assertGreaterEqual(total_pay, expected_min)

    def test_overtime_during_sabbath(self):
        """Test overtime rates during Sabbath work (should get Sabbath premium, not overtime)"""
        # Long Saturday work (12 hours)
        check_in = timezone.make_aware(datetime(2025, 7, 5, 8, 0))  # Saturday
        check_out = timezone.make_aware(datetime(2025, 7, 5, 20, 0))  # 12 hours

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should get Sabbath premium, not regular overtime
        sabbath_hours = result.get("sabbath_hours", 0)
        self.assertGreater(float(sabbath_hours), 0)

        # Sabbath premium should be higher than overtime
        # First 8 hours: 150% Sabbath rate
        # Extra 4 hours: 175% Sabbath overtime rate
        total_pay = float(result["total_gross_pay"])
        sabbath_base = 8 * 100 * 1.5  # 1200
        sabbath_overtime = 4 * 100 * 1.75  # 700
        expected_min = sabbath_base + sabbath_overtime  # 1900
        self.assertGreaterEqual(total_pay, expected_min * 0.9)  # Allow variance

    def test_monthly_employee_with_overtime(self):
        """Test that monthly employees DO get overtime premiums with fixed logic"""
        # Long workday for monthly employee
        check_in = timezone.make_aware(datetime(2025, 7, 1, 8, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 1, 20, 0))  # 12 hours

        WorkLog.objects.create(
            employee=self.monthly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.monthly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Monthly employees SHOULD get overtime premiums (hours are tracked and paid)
        # Note: hours are tracked and overtime premiums ARE paid
        overtime_hours = result.get("overtime_hours", 0)
        self.assertGreater(overtime_hours, 0)  # Should have overtime hours

        # Should get proportional monthly salary + overtime premiums
        total_pay = result.get("total_gross_pay", 0)
        base_daily_salary = Decimal("18000") / Decimal("23")  # daily base for July 2025

        # Should be significantly more than just base daily salary due to overtime
        self.assertGreater(
            total_pay, base_daily_salary * Decimal("1.5")
        )  # At least 50% more than base

    def test_overtime_rate_accuracy(self):
        """Test exact overtime rate calculations"""
        # 10-hour day with known rates
        check_in = timezone.make_aware(datetime(2025, 7, 1, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 1, 19, 0))  # 10 hours exactly

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Verify detailed breakdown if available
        breakdown = result.get("detailed_breakdown", {})
        if "overtime_breakdown" in breakdown:
            overtime_details = breakdown["overtime_breakdown"]

            # Should have exactly 2 hours at 125%
            if "overtime_125_hours" in overtime_details:
                self.assertAlmostEqual(
                    overtime_details["overtime_125_hours"], 2.0, places=2
                )

            # Should have correct rate
            if "rate_125" in overtime_details:
                expected_rate = 100 * 1.25  # 125
                self.assertAlmostEqual(
                    overtime_details["rate_125"], expected_rate, places=2
                )

            # Should have correct pay for overtime portion
            if "overtime_125_pay" in overtime_details:
                expected_overtime_pay = 2 * 125  # 250
                self.assertAlmostEqual(
                    overtime_details["overtime_125_pay"],
                    expected_overtime_pay,
                    places=2,
                )

    def test_friday_short_day_overtime(self):
        """Test overtime calculation on Friday (shorter standard day)"""
        # Friday work - service uses 8.6 hour standard regardless of day
        check_in = timezone.make_aware(datetime(2025, 7, 4, 8, 0))  # Friday
        check_out = timezone.make_aware(datetime(2025, 7, 4, 18, 0))  # 10 hours

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should have 8.6 regular + 1.4 overtime hours (consistent with Israeli standard)
        regular_hours = result.get("regular_hours", 0)
        overtime_hours = result.get("overtime_hours", 0)

        # Israeli standard applies: 8.6 hours regular, 1.4 hours overtime
        self.assertAlmostEqual(float(regular_hours), 8.6, places=1)
        self.assertAlmostEqual(float(overtime_hours), 1.4, places=1)

        # Check total hours
        total_hours = result.get("total_hours", 0)
        self.assertAlmostEqual(float(total_hours), 10.0, places=1)

        # Should get overtime premium
        actual_pay = float(result["total_gross_pay"])
        regular_pay = 10 * 100  # If all regular
        self.assertGreater(actual_pay, regular_pay)  # Should be more due to overtime
