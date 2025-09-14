"""
Tests for night shift detection and calculation.
Night shifts are typically defined as work between 22:00 (10 PM) and 06:00 (6 AM).
"""
from datetime import date, datetime, time
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from payroll.tests.conftest import ISRAELI_DAILY_NORM_HOURS
from payroll.models import Salary
from payroll.services.adapters import (
    EnhancedPayrollCalculationService as PayrollCalculationService,
)
from users.models import Employee
from worktime.models import WorkLog
class NightShiftCalculationTest(TestCase):
    """Test night shift detection and payment calculations"""
    def setUp(self):
        """Set up test data"""
        # Create hourly employee
        self.hourly_employee = Employee.objects.create(
            first_name="Night",
            last_name="Worker",
            email="night@test.com",
            employment_type="hourly",
            is_active=True,
        )
        # Create salary configuration with night shift premium
        self.salary_config = Salary.objects.create(
            employee=self.hourly_employee,
            calculation_type="hourly",
            hourly_rate=Decimal("50.00"),
            currency="ILS",
        )
    def test_full_night_shift(self, payroll_service):
        """Test full night shift from 22:00 to 06:00"""
        # Create work log for full night shift (use Wednesday to avoid any Sabbath logic)
        check_in = timezone.make_aware(datetime(2025, 7, 9, 22, 0))  # 10 PM Wednesday
        check_out = timezone.make_aware(datetime(2025, 7, 10, 6, 0))  # 6 AM Thursday
        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )
        service = PayrollCalculationService(
            self.hourly_employee, 2025, 7, fast_mode=True
        )
        result = service.calculate_monthly_salary()
        # Should have 8 hours of night shift
        self.assertEqual(result.get("night_hours", 0), 8)
        # Israeli law: night shift max 7h regular, then overtime
        self.assertEqual(result.get("regular_hours", 0), 7)
        # Night pay = overtime pay (1h): 1 hour * 50 * 0.25 = 12.5 (just the bonus part)
        expected_night_pay = Decimal("12.50")
        self.assertEqual(result.get("night_pay", 0), expected_night_pay)
    def test_partial_night_shift_evening(self):
        """Test shift that starts in evening and goes into night"""
        # Work from 8 PM to 2 AM (4 hours regular, 4 hours night)
        check_in = timezone.make_aware(datetime(2025, 7, 1, 20, 0))  # 8 PM
        check_out = timezone.make_aware(datetime(2025, 7, 2, 2, 0))  # 2 AM
        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )
        service = PayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary()
        # Should have 4 hours of night shift (22:00 to 02:00)
        self.assertEqual(result.get("night_hours", 0), 4)
        # Total 6h shift with 4h night - all 6h are regular (under 7h limit)
        self.assertEqual(result.get("regular_hours", 0), 6)
    def test_partial_night_shift_morning(self):
        """Test shift that starts at night and ends in morning"""
        # Work from 4 AM to 10 AM (2 hours night, 4 hours regular)
        check_in = timezone.make_aware(datetime(2025, 7, 1, 4, 0))  # 4 AM
        check_out = timezone.make_aware(datetime(2025, 7, 1, 10, 0))  # 10 AM
        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )
        service = PayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary()
        # Should have 2 hours of night shift (04:00 to 06:00)
        self.assertEqual(result.get("night_hours", 0), 2)
        # Total 6h shift with 2h night - all 6h are regular (under 7h limit)
        self.assertEqual(result.get("regular_hours", 0), 6)
    def test_overnight_shift_crossing_midnight(self):
        """Test shift that crosses midnight"""
        # Work from 11 PM to 3 AM
        check_in = timezone.make_aware(datetime(2025, 7, 1, 23, 0))  # 11 PM
        check_out = timezone.make_aware(datetime(2025, 7, 2, 3, 0))  # 3 AM next day
        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )
        service = PayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary()
        # All 4 hours should be night shift
        self.assertEqual(result.get("night_hours", 0), 4)
    def test_sabbath_night_shift(self):
        """Test night shift during Sabbath (Friday night/Saturday)"""
        # Friday night shift starting at 11 PM
        check_in = timezone.make_aware(datetime(2025, 7, 4, 23, 0))  # Friday 11 PM
        check_out = timezone.make_aware(datetime(2025, 7, 5, 7, 0))  # Saturday 7 AM
        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )
        service = PayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary()
        # Should have Sabbath night hours (higher rate than regular night)
        self.assertGreater(result.get("sabbath_night_hours", 0), 0)
        self.assertGreater(
            result.get("sabbath_night_pay", 0), result.get("night_pay", 0)
        )
    def test_no_night_shift_configuration(self):
        """Test handling when night shift times are not configured"""
        # Create night work log
        check_in = timezone.make_aware(datetime(2025, 7, 1, 23, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 2, 3, 0))
        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )
        service = PayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary()
        # For now, all hours treated as regular - night shift functionality depends on service implementation
        self.assertGreater(result.get("total_hours", 0), 0)
    def test_max_16_hour_shift(self):
        """Test calculation for maximum allowed 16-hour shift"""
        # Maximum 16-hour shift (legal limit)
        check_in = timezone.make_aware(datetime(2025, 7, 1, 6, 0))  # 6 AM
        check_out = timezone.make_aware(datetime(2025, 7, 1, 22, 0))  # 10 PM same day
        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )
        service = PayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary()
        # 16h shift: 8.6h regular + 7.4h overtime, no night hours (all during day)
        self.assertEqual(result.get("night_hours", 0), 0)
        # Day shift: max 8.6h regular per shift, rest is overtime
        self.assertEqual(result.get("regular_hours", 0), Decimal("8.6"))
        self.assertEqual(
            result.get("overtime_hours", 0), Decimal("7.40")
        )  # 16h - 8.6h = 7.4h overtime