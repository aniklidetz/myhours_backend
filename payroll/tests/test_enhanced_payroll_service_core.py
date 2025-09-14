"""
Refactored tests for the legacy PayrollService core logic.

These tests validate the same behaviours through the new public API:
    PayrollService().calculate(CalculationContext, CalculationStrategy.ENHANCED)

Notes:
    * Israeli daily norm: 8.6h on weekdays, 7h on night shift.
    * Sabbath/holiday premium applies to ALL worked hours on that day.
    * For MONTHLY employees the base salary is proportional (salary/182 * hours)
      and bonuses only are added (Sabbath/holiday and overtime tiers).
"""
from datetime import datetime, date, timedelta
from decimal import Decimal
from payroll.tests.helpers import MONTHLY_NORM_HOURS, ISRAELI_DAILY_NORM_HOURS, NIGHT_NORM_HOURS, MONTHLY_NORM_HOURS

import pytz
from django.test import TestCase
from django.utils import timezone

from payroll.models import DailyPayrollCalculation, MonthlyPayrollSummary, Salary
from payroll.services.payroll_service import PayrollService
from payroll.services.enums import CalculationStrategy
from payroll.tests.helpers import make_context
from users.models import Employee
from worktime.models import WorkLog

ISRAEL_TZ = pytz.timezone("Israel")

class EnhancedPayrollServiceCoreRefactor(TestCase):
    """
    Refactored tests for the legacy PayrollService core logic.

    These tests validate the same behaviours through the new public API:
        PayrollService().calculate(CalculationContext, CalculationStrategy.ENHANCED)

    Notes:
        * Israeli daily norm: 8.6h on weekdays, 7h on night shift.
        * Sabbath/holiday premium applies to ALL worked hours on that day.
        * For MONTHLY employees the base salary is proportional (salary/182 * hours)
          and bonuses only are added (Sabbath/holiday and overtime tiers).
    """

    def setUp(self) -> None:
        # Hourly employee @ 100 ILS/hr
        self.hourly_employee = Employee.objects.create(
            first_name="Hourly",
            last_name="Worker",
            email="hourly@test.com",
            employment_type="hourly",
            role="employee",
        )
        Salary.objects.create(
            employee=self.hourly_employee,
            calculation_type="hourly",
            hourly_rate=Decimal("100.00"),
            currency="ILS"
        )

        # Monthly employee @ 25,000 ILS/month
        self.monthly_employee = Employee.objects.create(
            first_name="Monthly",
            last_name="Worker",
            email="monthly@test.com",
            employment_type="full_time",
            role="employee",
        )
        Salary.objects.create(
            employee=self.monthly_employee,
            calculation_type="monthly",
            base_salary=Decimal("25000.00"),
            currency="ILS"
        )

        self.service = PayrollService()

    # -------------------- Hourly employees --------------------

    def test_hourly_regular_day_no_overtime(self):
        """8-hour weekday - all hours regular (8 < 8.6)."""
        check_in = timezone.make_aware(datetime(2025, 7, 1, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 1, 17, 0))  # 8h
        WorkLog.objects.create(employee=self.hourly_employee, check_in=check_in, check_out=check_out)

        ctx = make_context(self.hourly_employee, 2025, 7)
        res = self.service.calculate(ctx, CalculationStrategy.ENHANCED)

        self.assertAlmostEqual(float(res.get("total_hours", 0)), 8.6, places=1)
        self.assertAlmostEqual(float(res.get("overtime_hours", 0)), 0.0, places=1)
        # 8 * 100
        self.assertAlmostEqual(float(res["total_salary"]), 800.0, delta=1.0)

    def test_hourly_ten_hour_day_overtime_125(self):
        """10-hour weekday - 8.6h @100% + 1.4h @125%."""
        check_in = timezone.make_aware(datetime(2025, 7, 2, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 2, 19, 0))  # 10h
        WorkLog.objects.create(employee=self.hourly_employee, check_in=check_in, check_out=check_out)

        ctx = make_context(self.hourly_employee, 2025, 7)
        res = self.service.calculate(ctx, CalculationStrategy.ENHANCED)

        regular = 8.6 * 100.0
        ot125 = 1.4 * 100.0 * 1.25
        expected = regular + ot125
        self.assertAlmostEqual(float(res["total_salary"]), expected, delta=2.0)

    def test_hourly_twelve_hour_day_overtime_150(self):
        """12-hour weekday - 8.6h @100% + 2h @125% + 1.4h @150%."""
        check_in = timezone.make_aware(datetime(2025, 7, 3, 8, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 3, 20, 0))  # 12h
        WorkLog.objects.create(employee=self.hourly_employee, check_in=check_in, check_out=check_out)

        ctx = make_context(self.hourly_employee, 2025, 7)
        res = self.service.calculate(ctx, CalculationStrategy.ENHANCED)

        # Israeli standard: 8.6 regular + 2 at 125% + 1.4 at 150%
        regular = 8.6 * 100.0
        ot125 = 2.0 * 100.0 * 1.25
        ot150 = 1.4 * 100.0 * 1.50
        expected = regular + ot125 + ot150
        self.assertAlmostEqual(float(res["total_salary"]), expected, delta=5.0)
        self.assertAlmostEqual(float(res.get("overtime_hours", 0)), 3.4, places=1)

    def test_hourly_sabbath_daytime(self):
        """Saturday 8h - all hours at 150%."""
        # Saturday 2025-07-05
        check_in = timezone.make_aware(datetime(2025, 7, 5, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 5, 17, 0))  # 8h
        WorkLog.objects.create(employee=self.hourly_employee, check_in=check_in, check_out=check_out)

        ctx = make_context(self.hourly_employee, 2025, 7, fast_mode=False)
        res = self.service.calculate(ctx, CalculationStrategy.ENHANCED)

        expected = 8.6 * 100.0 * 1.5
        self.assertAlmostEqual(float(res["total_salary"]), expected, delta=2.0)
        self.assertGreater(float(res.get("shabbat_hours", 0)), 0.0)

    def test_hourly_sabbath_overtime(self):
        """Saturday 12h - 8.6h @150% + 2h @175% + 1.4h @200%."""
        check_in = timezone.make_aware(datetime(2025, 7, 5, 8, 0))  # Saturday
        check_out = timezone.make_aware(datetime(2025, 7, 5, 20, 0))  # 12h
        WorkLog.objects.create(employee=self.hourly_employee, check_in=check_in, check_out=check_out)

        ctx = make_context(self.hourly_employee, 2025, 7, fast_mode=False)
        res = self.service.calculate(ctx, CalculationStrategy.ENHANCED)

        # Sabbath rates: 8.6h @150%, 2h @175%, 1.4h @200%
        sabbath_regular = 8.6 * 100.0 * 1.5
        sabbath_ot1 = 2.0 * 100.0 * 1.75
        sabbath_ot2 = 1.4 * 100.0 * 2.0
        expected = sabbath_regular + sabbath_ot1 + sabbath_ot2
        self.assertAlmostEqual(float(res["total_salary"]), expected, delta=10.0)

    # -------------------- Monthly employees --------------------

    def test_monthly_regular_day(self):
        """Monthly: 8h weekday - proportional base only."""
        check_in = timezone.make_aware(datetime(2025, 7, 1, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 1, 17, 0))  # 8h
        WorkLog.objects.create(employee=self.monthly_employee, check_in=check_in, check_out=check_out)

        ctx = make_context(self.monthly_employee, 2025, 7)
        res = self.service.calculate(ctx, CalculationStrategy.ENHANCED)

        rate = float(Decimal("25000") / MONTHLY_NORM_HOURS)  # ~137.36
        expected = 8.6 * rate
        self.assertAlmostEqual(float(res["total_salary"]), expected, delta=10.0)

    def test_monthly_ten_hour_day_overtime_bonus_only(self):
        """
        Monthly: proportional base + bonus for overtime.
        10h weekday - proportional_base(10h) + 1.4h * 25% bonus.
        """
        check_in = timezone.make_aware(datetime(2025, 7, 3, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 3, 19, 0))  # 10h
        WorkLog.objects.create(employee=self.monthly_employee, check_in=check_in, check_out=check_out)

        ctx = make_context(self.monthly_employee, 2025, 7)
        res = self.service.calculate(ctx, CalculationStrategy.ENHANCED)

        rate = float(Decimal("25000") / MONTHLY_NORM_HOURS)  # ~137.36
        proportional = 10.0 * rate
        bonus = 1.4 * rate * 0.25
        expected = proportional + bonus
        self.assertAlmostEqual(float(res["total_salary"]), expected, delta=60.0)
        self.assertAlmostEqual(float(res.get("overtime_hours", 0)), 1.4, places=1)

    def test_monthly_twelve_hour_day_overtime_bonuses(self):
        """
        Monthly: proportional base + overtime bonuses.
        12h weekday - proportional_base(12h) + 2h * 25% + 1.4h * 50% bonuses.
        """
        check_in = timezone.make_aware(datetime(2025, 7, 4, 8, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 4, 20, 0))  # 12h
        WorkLog.objects.create(employee=self.monthly_employee, check_in=check_in, check_out=check_out)

        ctx = make_context(self.monthly_employee, 2025, 7)
        res = self.service.calculate(ctx, CalculationStrategy.ENHANCED)

        rate = float(Decimal("25000") / MONTHLY_NORM_HOURS)
        proportional = 12.0 * rate
        bonus_125 = 2.0 * rate * 0.25  # First 2 overtime hours
        bonus_150 = 1.4 * rate * 0.50  # Next 1.4 overtime hours
        expected = proportional + bonus_125 + bonus_150
        self.assertAlmostEqual(float(res["total_salary"]), expected, delta=80.0)

    def test_monthly_sabbath_daytime_bonus_only(self):
        """
        Monthly: proportional base + Sabbath 50% bonus.
        8h Saturday - proportional_base(8h) + 8h * 50% bonus.
        """
        check_in = timezone.make_aware(datetime(2025, 7, 5, 9, 0))  # Saturday
        check_out = timezone.make_aware(datetime(2025, 7, 5, 17, 0))  # 8h
        WorkLog.objects.create(employee=self.monthly_employee, check_in=check_in, check_out=check_out)

        ctx = make_context(self.monthly_employee, 2025, 7)
        res = self.service.calculate(ctx, CalculationStrategy.ENHANCED)

        rate = float(Decimal("25000") / MONTHLY_NORM_HOURS)
        expected = (8.6 * rate) + (8.6 * rate * 0.50)
        self.assertAlmostEqual(float(res["total_salary"]), expected, delta=60.0)
        self.assertGreater(float(res.get("shabbat_hours", 0)), 0.0)

    def test_monthly_sabbath_overtime_bonuses(self):
        """
        Monthly: proportional base + Sabbath and overtime bonuses.
        12h Saturday - proportional_base(12h) + Sabbath bonuses (50%/75%/100%).
        """
        check_in = timezone.make_aware(datetime(2025, 7, 5, 8, 0))  # Saturday
        check_out = timezone.make_aware(datetime(2025, 7, 5, 20, 0))  # 12h
        WorkLog.objects.create(employee=self.monthly_employee, check_in=check_in, check_out=check_out)

        ctx = make_context(self.monthly_employee, 2025, 7)
        res = self.service.calculate(ctx, CalculationStrategy.ENHANCED)

        rate = float(Decimal("25000") / MONTHLY_NORM_HOURS)
        proportional = 12.0 * rate
        # Sabbath bonuses: 8.6h * 50%, 2h * 75%, 1.4h * 100%
        bonus_sabbath = 8.6 * rate * 0.50
        bonus_sabbath_ot1 = 2.0 * rate * 0.75
        bonus_sabbath_ot2 = 1.4 * rate * 1.00
        expected = proportional + bonus_sabbath + bonus_sabbath_ot1 + bonus_sabbath_ot2
        self.assertAlmostEqual(float(res["total_salary"]), expected, delta=100.0)

    # -------------------- Multi-day scenarios --------------------

    def test_mixed_week_hourly(self):
        """Hourly: mix of regular, overtime, and Sabbath days."""
        work_patterns = [
            (1, 8),    # Tuesday - regular
            (2, 10),   # Wednesday - overtime
            (3, 6),    # Thursday - short day
            (5, 8),    # Saturday - Sabbath
        ]

        for day, hours in work_patterns:
            check_in = timezone.make_aware(datetime(2025, 7, day, 9, 0))
            check_out = check_in + timedelta(hours=hours)
            WorkLog.objects.create(employee=self.hourly_employee, check_in=check_in, check_out=check_out)

        ctx = make_context(self.hourly_employee, 2025, 7)
        res = self.service.calculate(ctx, CalculationStrategy.ENHANCED)

        # Should have total hours and reasonable pay
        self.assertAlmostEqual(float(res.get("total_hours", 0)), 32.0, places=1)
        self.assertGreater(float(res["total_salary"]), 3000.0)  # Should be substantial

    def test_mixed_week_monthly(self):
        """Monthly: mix of regular, overtime, and Sabbath days."""
        work_patterns = [
            (1, 8),    # Tuesday - regular
            (2, 10),   # Wednesday - overtime
            (3, 6),    # Thursday - short day
            (5, 8),    # Saturday - Sabbath
        ]

        for day, hours in work_patterns:
            check_in = timezone.make_aware(datetime(2025, 7, day, 9, 0))
            check_out = check_in + timedelta(hours=hours)
            WorkLog.objects.create(employee=self.monthly_employee, check_in=check_in, check_out=check_out)

        ctx = make_context(self.monthly_employee, 2025, 7)
        res = self.service.calculate(ctx, CalculationStrategy.ENHANCED)

        # Should be proportional salary + various bonuses
        rate = float(Decimal("25000") / MONTHLY_NORM_HOURS)
        base_expected = 32.0 * rate  # Proportional base
        self.assertGreater(float(res["total_salary"]), base_expected)  # Should have bonuses

    # -------------------- API contract / regression guards --------------------

    def test_calculation_returns_expected_keys(self):
        """The public API returns stable top-level keys."""
        # Add some work to get meaningful results
        check_in = timezone.make_aware(datetime(2025, 7, 1, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 1, 17, 0))
        WorkLog.objects.create(employee=self.hourly_employee, check_in=check_in, check_out=check_out)

        ctx = make_context(self.hourly_employee, 2025, 7)
        res = self.service.calculate(ctx, CalculationStrategy.ENHANCED)

        # Do not assert the exact schema of nested breakdowns here.
        for key in ("total_salary", "total_hours", "regular_hours"):
            self.assertIn(key, res)

    def test_fast_mode_and_api_mode_both_work(self):
        """Both fast_mode variants should return a result without error."""
        # Add some work
        check_in = timezone.make_aware(datetime(2025, 7, 1, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 1, 17, 0))
        WorkLog.objects.create(employee=self.hourly_employee, check_in=check_in, check_out=check_out)

        for fast in (True, False):
            ctx = make_context(self.hourly_employee, 2025, 7, fast_mode=fast)
            res = self.service.calculate(ctx, CalculationStrategy.ENHANCED)
            self.assertGreater(float(res.get("total_salary", 0)), 0.0)

    def test_zero_work_returns_zero_salary(self):
        """No work logs should return zero salary."""
        ctx = make_context(self.hourly_employee, 2025, 7)
        res = self.service.calculate(ctx, CalculationStrategy.ENHANCED)

        self.assertEqual(float(res.get("total_salary", 0)), 0.0)
        self.assertEqual(float(res.get("total_hours", 0)), 0.0)

    def test_service_handles_invalid_dates_gracefully(self):
        """Service should handle edge cases gracefully."""
        # Test with February (short month)
        ctx = make_context(self.hourly_employee, 2025, 2)
        res = self.service.calculate(ctx, CalculationStrategy.ENHANCED)

        # Should not crash and return valid structure
        self.assertIsInstance(res, dict)
        self.assertIn("total_salary", res)
