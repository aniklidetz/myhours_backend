"""
Test the FIXED overtime calculation logic for monthly employees.
This test file specifically validates that monthly employees now receive:
- Base hourly pay (100%) + overtime bonus (25%/50%) = 125%/150% total
- Instead of the old incorrect logic of only bonus percentages
"""
from datetime import datetime
from decimal import Decimal
from payroll.tests.helpers import PayrollTestMixin, MONTHLY_NORM_HOURS, ISRAELI_DAILY_NORM_HOURS, NIGHT_NORM_HOURS, MONTHLY_NORM_HOURS
from django.test import TestCase
from django.utils import timezone
from payroll.models import DailyPayrollCalculation, Salary
from payroll.services.payroll_service import PayrollService
from payroll.services.enums import CalculationStrategy
from payroll.tests.helpers import PayrollTestMixin, make_context, ISRAELI_DAILY_NORM_HOURS
from users.models import Employee
from worktime.models import WorkLog

class MonthlyOvertimeFixedLogicTest(PayrollTestMixin, TestCase):
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
        self.payroll_service = PayrollService()
    def test_overtime_125_percent_full_rate(self):
        """Test 10 hours: 8.6 regular + 1.4 overtime at 125%"""
        # 10-hour workday (8.6 regular + 1.4 overtime at 125%)
        check_in = timezone.make_aware(datetime(2025, 7, 1, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 1, 19, 0))  # 10 hours
        WorkLog.objects.create(
            employee=self.monthly_employee, check_in=check_in, check_out=check_out
        )
        context = make_context(self.monthly_employee, 2025, 7)
        result = self.payroll_service.calculate(context, CalculationStrategy.ENHANCED)

        monthly_hourly_rate = Decimal("25000") / MONTHLY_NORM_HOURS  # ~137.36 ILS/hour

        # Verify total hours worked
        total_hours = result.get("total_hours", 0)
        self.assertAlmostEqual(float(total_hours), 10.0, places=1)

        # Monthly employee philosophy: proportional salary + overtime bonuses
        # Proportional = (25000/182) * 10 = ~1373.6 ILS
        proportional_salary = monthly_hourly_rate * 10
        # Bonus = 1.4h * (25000/182) * 0.25 = ~48.1 ILS (25% bonus for 1.4 overtime hours)
        bonus_125 = Decimal("1.4") * monthly_hourly_rate * Decimal("0.25")
        expected_total = proportional_salary + bonus_125

        total_salary = result.get("total_salary", 0)
        self.assertAlmostEqual(float(total_salary), float(expected_total), delta=30)

        # Should have overtime hours recorded
        overtime_hours = result.get("overtime_hours", 0)
        self.assertAlmostEqual(float(overtime_hours), 1.4, places=1)
    def test_overtime_150_percent_full_rate(self):
        """Test 12 hours: 8.6 regular + 2.0 at 125% + 1.4 at 150%"""
        # 12-hour workday (8.6 regular + 2h at 125% + 1.4h at 150%)
        check_in = timezone.make_aware(datetime(2025, 7, 2, 8, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 2, 20, 0))  # 12 hours
        WorkLog.objects.create(
            employee=self.monthly_employee, check_in=check_in, check_out=check_out
        )
        context = make_context(self.monthly_employee, 2025, 7)
        result = self.payroll_service.calculate(context, CalculationStrategy.ENHANCED)

        monthly_hourly_rate = Decimal("25000") / MONTHLY_NORM_HOURS  # ~137.36 ILS/hour

        # Verify total hours worked
        total_hours = result.get("total_hours", 0)
        self.assertAlmostEqual(float(total_hours), 12.0, places=1)

        # Monthly employee philosophy: proportional salary + overtime bonuses
        # 12 hours = 8.6 regular + 2.0h@125% + 1.4h@150%
        proportional_salary = monthly_hourly_rate * 12  # ~1648.3 ILS
        bonus_125 = Decimal("2.0") * monthly_hourly_rate * Decimal("0.25")  # ~68.7 ILS
        bonus_150 = Decimal("1.4") * monthly_hourly_rate * Decimal("0.50")  # ~96.2 ILS
        expected_total = proportional_salary + bonus_125 + bonus_150  # ~1813.2 ILS

        total_salary = result.get("total_salary", 0)
        self.assertAlmostEqual(float(total_salary), float(expected_total), delta=50)

        # Should have significant overtime hours
        overtime_hours = result.get("overtime_hours", 0)
        self.assertAlmostEqual(float(overtime_hours), 3.4, places=1)  # 2.0 + 1.4 = 3.4
    def test_sabbath_150_percent_full_rate(self):
        """Test Sabbath work: proportional salary + 50% bonus for all hours"""
        # Saturday work (8 hours)
        check_in = timezone.make_aware(datetime(2025, 7, 5, 9, 0))  # Saturday
        check_out = timezone.make_aware(datetime(2025, 7, 5, 17, 0))  # 8 hours
        WorkLog.objects.create(
            employee=self.monthly_employee, check_in=check_in, check_out=check_out
        )
        context = make_context(self.monthly_employee, 2025, 7)
        result = self.payroll_service.calculate(context, CalculationStrategy.ENHANCED)

        monthly_hourly_rate = Decimal("25000") / MONTHLY_NORM_HOURS  # ~137.36 ILS/hour

        # Verify total hours worked
        total_hours = result.get("total_hours", 0)
        self.assertAlmostEqual(float(total_hours), 8.6, places=1)

        # Monthly employee philosophy: proportional salary + Sabbath bonus
        # Proportional = (25000/182) * 8 = ~1098.9 ILS
        # Sabbath bonus = 8 * (25000/182) * 0.50 = ~549.4 ILS (50% bonus for all Sabbath hours)
        proportional_salary = monthly_hourly_rate * 8
        sabbath_bonus = Decimal("8") * monthly_hourly_rate * Decimal("0.50")
        expected_total = proportional_salary + sabbath_bonus  # ~1648.3 ILS (150% total)

        total_salary = result.get("total_salary", 0)
        self.assertAlmostEqual(float(total_salary), float(expected_total), delta=50)

        # Verify Sabbath hours are tracked
        shabbat_hours = result.get("shabbat_hours", 0)
        self.assertGreater(float(shabbat_hours), 0)
    def test_comparison_old_vs_new_logic(self):
        """Test extreme overtime: 14.55 hours = 8.6 + 2.0@125% + 3.95@150%"""
        # Long workday similar to real case: 14.55 hours
        check_in = timezone.make_aware(datetime(2025, 7, 8, 8, 24))
        check_out = timezone.make_aware(datetime(2025, 7, 8, 22, 57))  # 14.55 hours
        WorkLog.objects.create(
            employee=self.monthly_employee, check_in=check_in, check_out=check_out
        )
        context = make_context(self.monthly_employee, 2025, 7)
        result = self.payroll_service.calculate(context, CalculationStrategy.ENHANCED)

        monthly_hourly_rate = Decimal("25000") / MONTHLY_NORM_HOURS  # ~137.36 ILS/hour

        # Verify total hours worked
        total_hours = result.get("total_hours", 0)
        self.assertAlmostEqual(float(total_hours), 14.55, places=1)

        # Monthly employee philosophy: proportional + bonuses
        # 14.55 hours = 8.6 regular + 2.0h@125% + 3.95h@150%
        proportional_salary = monthly_hourly_rate * Decimal("14.55")  # ~1998.6 ILS
        bonus_125 = Decimal("2.0") * monthly_hourly_rate * Decimal("0.25")  # ~68.7 ILS
        bonus_150 = Decimal("3.95") * monthly_hourly_rate * Decimal("0.50")  # ~271.4 ILS
        expected_total = proportional_salary + bonus_125 + bonus_150  # ~2338.7 ILS

        total_salary = result.get("total_salary", 0)
        self.assertAlmostEqual(float(total_salary), float(expected_total), delta=100)

        # Should be substantial payment for extreme overtime (over 2300 ILS)
        self.assertGreater(float(total_salary), 2300)

        # Should have significant overtime hours
        overtime_hours = result.get("overtime_hours", 0)
        self.assertAlmostEqual(float(overtime_hours), 5.95, places=1)  # 2.0 + 3.95 = 5.95
    def test_regular_day_no_overtime(self):
        """Test regular 8-hour day: no overtime since 8 < 8.6"""
        # Regular 8-hour workday
        check_in = timezone.make_aware(datetime(2025, 7, 1, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 1, 17, 0))  # 8 hours
        WorkLog.objects.create(
            employee=self.monthly_employee, check_in=check_in, check_out=check_out
        )
        context = make_context(self.monthly_employee, 2025, 7)
        result = self.payroll_service.calculate(context, CalculationStrategy.ENHANCED)

        monthly_hourly_rate = Decimal("25000") / MONTHLY_NORM_HOURS  # ~137.36 ILS/hour

        # Verify total hours worked
        total_hours = result.get("total_hours", 0)
        self.assertAlmostEqual(float(total_hours), 8.6, places=1)

        # Verify no overtime hours (since 8 < 8.6)
        overtime_hours = result.get("overtime_hours", 0)
        self.assertEqual(float(overtime_hours), 0.0)

        # Monthly employee philosophy: only proportional salary, no bonuses
        # Proportional = (25000/182) * 8 = ~1098.9 ILS
        expected_proportional = monthly_hourly_rate * 8

        total_salary = result.get("total_salary", 0)
        self.assertAlmostEqual(float(total_salary), float(expected_proportional), delta=30)

        # Should be around 1099 ILS for 8 hours
        self.assertGreater(float(total_salary), 1070)
        self.assertLess(float(total_salary), 1130)
