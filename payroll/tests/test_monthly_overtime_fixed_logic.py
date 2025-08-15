"""
Test the FIXED overtime calculation logic for monthly employees.

This test file specifically validates that monthly employees now receive:
- Base hourly pay (100%) + overtime bonus (25%/50%) = 125%/150% total
- Instead of the old incorrect logic of only bonus percentages
"""

from datetime import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from payroll.models import DailyPayrollCalculation, Salary
from payroll.services import EnhancedPayrollCalculationService
from users.models import Employee
from worktime.models import WorkLog


class MonthlyOvertimeFixedLogicTest(TestCase):
    """Test the fixed overtime calculation logic for monthly employees"""

    def setUp(self):
        """Set up test data"""
        # Create monthly employee
        self.monthly_employee = Employee.objects.create(
            first_name="Monthly",
            last_name="Fixed",
            email="monthly.fixed@test.com",
            employment_type="full_time",
            role="employee",
        )

        # Create salary: 25,000 ILS/month (same as Elior in real data)
        self.salary = Salary.objects.create(
            employee=self.monthly_employee,
            calculation_type="monthly",
            base_salary=Decimal("25000.00"),
            currency="ILS",
        )

    def test_overtime_125_percent_full_rate(self):
        """Test that first 2 overtime hours get full 125% rate (not just 25% bonus)"""
        # 10-hour workday (8.6 regular + 1.4 overtime at 125%)
        check_in = timezone.make_aware(datetime(2025, 7, 1, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 1, 19, 0))  # 10 hours

        worklog = WorkLog.objects.create(
            employee=self.monthly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.monthly_employee, 2025, 7)
        result = service.calculate_daily_bonuses_monthly(worklog, save_to_db=True)

        # Calculate expected values with NEW UNIFIED LOGIC
        monthly_hourly_rate = Decimal("25000") / Decimal("182")  # 137.36
        hours_worked = Decimal("10")

        # NEW UNIFIED LOGIC:
        # base_pay = ALL hours × monthly_hourly_rate (100% for all hours)
        expected_base_pay = hours_worked * monthly_hourly_rate  # 10 * 137.36 = 1373.6

        # bonus_pay = overtime bonus only (25% for 1.4 hours)
        overtime_hours = Decimal("1.4")  # 10 - 8.6
        expected_bonus_pay = (
            overtime_hours * monthly_hourly_rate * Decimal("0.25")
        )  # 25% bonus

        # total_pay = base_pay + bonus_pay
        expected_total_pay = expected_base_pay + expected_bonus_pay

        # Verify NEW unified structure
        self.assertAlmostEqual(
            float(result["base_pay"]), float(expected_base_pay), places=1
        )
        self.assertAlmostEqual(
            float(result["bonus_pay"]), float(expected_bonus_pay), places=1
        )
        self.assertAlmostEqual(
            float(result["total_pay"]), float(expected_total_pay), places=1
        )

        # Verify in database
        calc = DailyPayrollCalculation.objects.get(
            employee=self.monthly_employee, work_date=check_in.date()
        )
        self.assertAlmostEqual(float(calc.base_pay), float(expected_base_pay), places=1)
        self.assertAlmostEqual(
            float(calc.bonus_pay), float(expected_bonus_pay), places=1
        )

    def test_overtime_150_percent_full_rate(self):
        """Test that overtime beyond 2 hours gets full 150% rate (not just 50% bonus)"""
        # 12-hour workday (8.6 regular + 2 hours at 125% + 1.4 hours at 150%)
        check_in = timezone.make_aware(datetime(2025, 7, 2, 8, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 2, 20, 0))  # 12 hours

        worklog = WorkLog.objects.create(
            employee=self.monthly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.monthly_employee, 2025, 7)
        result = service.calculate_daily_bonuses_monthly(worklog, save_to_db=True)

        # Calculate expected values with NEW UNIFIED LOGIC
        monthly_hourly_rate = Decimal("25000") / Decimal("182")  # 137.36
        hours_worked = Decimal("12")

        # NEW UNIFIED LOGIC:
        # base_pay = ALL hours × monthly_hourly_rate (100% for all hours)
        expected_base_pay = hours_worked * monthly_hourly_rate  # 12 * 137.36 = 1648.32

        # bonus_pay = overtime bonuses only (25% for 2h + 50% for 1.4h)
        overtime_bonus_125 = (
            Decimal("2") * monthly_hourly_rate * Decimal("0.25")
        )  # 25% bonus for first 2h
        overtime_bonus_150 = (
            Decimal("1.4") * monthly_hourly_rate * Decimal("0.50")
        )  # 50% bonus for additional 1.4h
        expected_bonus_pay = overtime_bonus_125 + overtime_bonus_150

        # total_pay = base_pay + bonus_pay
        expected_total_pay = expected_base_pay + expected_bonus_pay

        # Verify NEW unified structure
        self.assertAlmostEqual(
            float(result["base_pay"]), float(expected_base_pay), places=1
        )
        self.assertAlmostEqual(
            float(result["bonus_pay"]), float(expected_bonus_pay), places=1
        )
        self.assertAlmostEqual(
            float(result["total_pay"]), float(expected_total_pay), places=1
        )

        # Verify in database
        calc = DailyPayrollCalculation.objects.get(
            employee=self.monthly_employee, work_date=check_in.date()
        )
        self.assertAlmostEqual(float(calc.base_pay), float(expected_base_pay), places=1)
        self.assertAlmostEqual(
            float(calc.bonus_pay), float(expected_bonus_pay), places=1
        )

    def test_sabbath_150_percent_full_rate(self):
        """Test that Sabbath work gets full 150% rate (not just 50% bonus)"""
        # Saturday work (8 hours)
        check_in = timezone.make_aware(datetime(2025, 7, 5, 9, 0))  # Saturday
        check_out = timezone.make_aware(datetime(2025, 7, 5, 17, 0))  # 8 hours

        worklog = WorkLog.objects.create(
            employee=self.monthly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.monthly_employee, 2025, 7)
        result = service.calculate_daily_bonuses_monthly(worklog, save_to_db=True)

        # Calculate expected values with NEW UNIFIED LOGIC
        monthly_hourly_rate = Decimal("25000") / Decimal("182")  # 137.36
        hours_worked = Decimal("8")

        # NEW UNIFIED LOGIC for Sabbath:
        # base_pay = ALL hours × monthly_hourly_rate (100% for all hours)
        expected_base_pay = hours_worked * monthly_hourly_rate  # 8 * 137.36 = 1098.88

        # bonus_pay = Sabbath bonus only (50% for all hours)
        sabbath_bonus = (
            hours_worked * monthly_hourly_rate * Decimal("0.50")
        )  # 50% bonus
        expected_bonus_pay = sabbath_bonus

        # total_pay = base_pay + bonus_pay (= 150% total)
        expected_total_pay = expected_base_pay + expected_bonus_pay

        # Verify NEW unified structure
        self.assertAlmostEqual(
            float(result["base_pay"]), float(expected_base_pay), places=1
        )
        self.assertAlmostEqual(
            float(result["bonus_pay"]), float(expected_bonus_pay), places=1
        )
        self.assertAlmostEqual(
            float(result["total_pay"]), float(expected_total_pay), places=1
        )

        # Verify in database
        calc = DailyPayrollCalculation.objects.get(
            employee=self.monthly_employee, work_date=check_in.date()
        )
        self.assertAlmostEqual(float(calc.base_pay), float(expected_base_pay), places=1)
        self.assertAlmostEqual(
            float(calc.bonus_pay), float(expected_bonus_pay), places=1
        )

    def test_comparison_old_vs_new_logic(self):
        """Test that demonstrates the difference between old and new logic"""
        # Long workday similar to Elior's July 8: 14.55 hours
        check_in = timezone.make_aware(datetime(2025, 7, 8, 8, 24))
        check_out = timezone.make_aware(datetime(2025, 7, 8, 22, 57))  # 14.55 hours

        worklog = WorkLog.objects.create(
            employee=self.monthly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.monthly_employee, 2025, 7)
        result = service.calculate_daily_bonuses_monthly(worklog, save_to_db=True)

        # Get actual values from the calculation
        actual_total_pay = result["total_pay"]
        actual_total_gross = result["total_gross_pay"]

        # Calculate OLD logic values for comparison
        monthly_hourly_rate = Decimal("25000") / Decimal("182")
        working_days_july = 23
        daily_base_salary = Decimal("25000") / working_days_july

        # OLD logic would have been (just bonuses):
        # Overtime 1: 2 * 137.36 * 0.25 = 68.68
        # Overtime 2: 5.55 * 137.36 * 0.50 = 381.17
        # Total overtime: 449.85
        # Total gross: 1086.96 + 449.85 = 1536.81

        old_logic_ot1 = Decimal("2") * monthly_hourly_rate * Decimal("0.25")
        old_logic_ot2 = Decimal("5.55") * monthly_hourly_rate * Decimal("0.50")
        old_logic_total_overtime = old_logic_ot1 + old_logic_ot2
        old_logic_total_gross = daily_base_salary + old_logic_total_overtime

        # Verify new logic gives significantly more than old logic
        self.assertGreater(
            actual_total_pay, old_logic_total_overtime * Decimal("2")
        )  # At least double
        self.assertGreater(
            actual_total_gross, old_logic_total_gross
        )  # Should be more than old logic

        # Should be substantial overtime payment (over 1000 ILS for overtime alone)
        self.assertGreater(actual_total_pay, Decimal("1000"))

        # Should be substantial total payment (over 2000 ILS total)
        self.assertGreater(actual_total_gross, Decimal("2000"))

        # Verify improvement over old logic
        improvement = actual_total_gross - old_logic_total_gross
        self.assertGreater(improvement, Decimal("500"))  # Over 500 ILS improvement

    def test_regular_day_no_overtime(self):
        """Test that regular 8-hour day has no overtime but proper base pay"""
        # Regular 8-hour workday
        check_in = timezone.make_aware(datetime(2025, 7, 1, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 1, 17, 0))  # 8 hours

        worklog = WorkLog.objects.create(
            employee=self.monthly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.monthly_employee, 2025, 7)
        result = service.calculate_daily_bonuses_monthly(worklog, save_to_db=True)

        # Calculate expected values with NEW UNIFIED LOGIC
        monthly_hourly_rate = Decimal("25000") / Decimal("182")  # 137.36
        hours_worked = Decimal("8")

        # NEW UNIFIED LOGIC for regular day:
        # base_pay = ALL hours × monthly_hourly_rate (100% for all hours)
        expected_base_pay = hours_worked * monthly_hourly_rate  # 8 * 137.36 = 1098.88

        # bonus_pay = 0 (no overtime bonuses)
        expected_bonus_pay = Decimal("0")

        # total_pay = base_pay + bonus_pay
        expected_total_pay = expected_base_pay + expected_bonus_pay

        # Verify NEW unified structure
        self.assertAlmostEqual(
            float(result["base_pay"]), float(expected_base_pay), places=1
        )
        self.assertEqual(result["bonus_pay"], expected_bonus_pay)
        self.assertAlmostEqual(
            float(result["total_pay"]), float(expected_total_pay), places=1
        )

        # Verify in database
        calc = DailyPayrollCalculation.objects.get(
            employee=self.monthly_employee, work_date=check_in.date()
        )
        self.assertAlmostEqual(float(calc.base_pay), float(expected_base_pay), places=1)
        self.assertEqual(calc.bonus_pay, expected_bonus_pay)
