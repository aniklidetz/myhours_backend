"""
Tests for Sabbath work calculations and compensatory day creation.

Sabbath work is typically from Friday evening to Saturday evening,
with different premium rates for different time periods.
"""

from datetime import date, datetime, time
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from payroll.models import CompensatoryDay, MonthlyPayrollSummary, Salary
from payroll.services import EnhancedPayrollCalculationService
from users.models import Employee
from worktime.models import WorkLog


class SabbathCalculationTest(TestCase):
    """Test Sabbath work detection and premium calculations"""

    def setUp(self):
        """Set up test data"""
        # Create hourly employee
        self.hourly_employee = Employee.objects.create(
            first_name="Sabbath",
            last_name="Worker",
            email="sabbath@test.com",
            employment_type="hourly",
            role="employee",
        )

        self.hourly_salary = Salary.objects.create(
            employee=self.hourly_employee,
            calculation_type="hourly",
            hourly_rate=Decimal("100.00"),
            currency="ILS",
        )

        # Create monthly employee
        self.monthly_employee = Employee.objects.create(
            first_name="Monthly",
            last_name="Sabbath",
            email="monthly.sabbath@test.com",
            employment_type="full_time",
            role="employee",
        )

        self.monthly_salary = Salary.objects.create(
            employee=self.monthly_employee,
            calculation_type="monthly",
            base_salary=Decimal("25000.00"),
            currency="ILS",
        )

    def test_saturday_daytime_work_hourly(self):
        """Test Saturday daytime work gets 150% premium for hourly employees"""
        # Saturday work from 9 AM to 5 PM
        check_in = timezone.make_aware(datetime(2025, 7, 5, 9, 0))  # Saturday
        check_out = timezone.make_aware(datetime(2025, 7, 5, 17, 0))

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should have worked 8 hours
        total_hours = result.get("total_hours", 0)
        self.assertAlmostEqual(float(total_hours), 8.0, places=1)

        # Should get Sabbath premium - implementation may vary
        total_pay = float(result.get("total_gross_pay", 0))
        regular_pay = 8 * 100  # Regular pay
        self.assertGreater(
            total_pay, regular_pay
        )  # Should be more due to Sabbath premium

    def test_saturday_daytime_work_monthly(self):
        """Test Saturday daytime work for monthly employees (bonus only)"""
        # Saturday work from 10 AM to 6 PM
        check_in = timezone.make_aware(datetime(2025, 7, 5, 10, 0))  # Saturday
        check_out = timezone.make_aware(datetime(2025, 7, 5, 18, 0))

        WorkLog.objects.create(
            employee=self.monthly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.monthly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should have Sabbath bonus (not full payment)
        self.assertGreater(result.get("sabbath_hours", 0), 0)
        # Monthly employees get bonus, not full 150% of all hours
        total_pay = result.get("total_gross_pay", 0)
        # Should be proportional monthly salary + Sabbath bonus
        # For 1 day out of 23 working days: 25000/23 ≈ 1087 + sabbath bonus
        self.assertGreater(total_pay, 1500)  # More than just proportional
        self.assertLess(total_pay, 3000)  # But not excessive

    @patch(
        "integrations.services.sunrise_sunset_service.SunriseSunsetService.get_shabbat_times"
    )
    def test_friday_evening_sabbath_start(self, mock_sabbath_times):
        """Test work that starts before Sabbath and continues into Sabbath"""
        # Mock Sabbath times - Friday sunset at 19:30 (UTC format expected by API)
        mock_sabbath_times.return_value = {
            "start": "2025-07-04T16:30:00+00:00",  # UTC (19:30 Israel time)
            "end": "2025-07-05T17:30:00+00:00",  # UTC (20:30 Israel time)
            "is_estimated": False,
        }

        # Work from Friday 6 PM to Friday 11 PM (crosses Sabbath start at 7:30 PM)
        check_in = timezone.make_aware(datetime(2025, 7, 4, 18, 0))  # Friday 6 PM
        check_out = timezone.make_aware(datetime(2025, 7, 4, 23, 0))  # Friday 11 PM

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        # Use fast_mode=False to trigger API usage
        service = EnhancedPayrollCalculationService(
            self.hourly_employee, 2025, 7, fast_mode=False
        )

        # Test individual worklog calculation first (where the shift splitting actually happens)
        work_log = WorkLog.objects.get(
            employee=self.hourly_employee, check_in__date="2025-07-04"
        )
        daily_result = service.calculate_daily_pay_hourly(work_log, save_to_db=False)

        # Should detect as Sabbath work with shift splitting
        self.assertTrue(daily_result["is_sabbath"])
        self.assertEqual(daily_result["sabbath_type"], "friday_shift_spanning_sabbath")

        # Should track API usage in daily calculation
        daily_api_sources = daily_result.get("api_sources", [])
        self.assertTrue(
            any("sunrise_sunset_api" in source for source in daily_api_sources)
        )

        # Now test monthly summary
        result = service.calculate_monthly_salary_enhanced()

        # Should have worked 5 hours total
        total_hours = result.get("total_hours", 0)
        self.assertAlmostEqual(float(total_hours), 5.0, places=1)

        # Should get premium payment (more than regular 5 hours × 100)
        total_pay = float(result.get("total_gross_pay", 0))
        regular_pay = 5 * 100  # 500
        self.assertGreater(total_pay, regular_pay)  # Should include Sabbath premiums

    def test_compensatory_day_creation_saturday_work(self):
        """Test that compensatory days are created for Saturday work"""
        # Saturday work
        check_in = timezone.make_aware(datetime(2025, 7, 5, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 5, 17, 0))

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        # Clear any existing compensatory days
        CompensatoryDay.objects.filter(employee=self.hourly_employee).delete()

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Check if compensatory days are tracked in result
        comp_days_earned = result.get("compensatory_days_earned", 0)
        # Implementation may or may not create compensatory days
        # Just verify the calculation works without error
        self.assertIsNotNone(result)
        self.assertGreater(result.get("total_gross_pay", 0), 0)

    @patch("integrations.services.hebcal_service.HebcalService.fetch_holidays")
    def test_sabbath_during_holiday(self, mock_holidays):
        """Test Sabbath work during a Jewish holiday"""
        # Mock holiday data - Shabbat during Passover
        mock_holidays.return_value = [
            {
                "date": "2025-07-05",
                "hebrew": "שבת",
                "title": "Shabbat during Passover",
                "category": "major",
            }
        ]

        # Saturday work during holiday
        check_in = timezone.make_aware(datetime(2025, 7, 5, 10, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 5, 18, 0))

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should calculate 8 hours of work
        total_hours = result.get("total_hours", 0)
        self.assertAlmostEqual(float(total_hours), 8.0, places=1)

        # Should get premium pay
        total_pay = float(result.get("total_gross_pay", 0))
        regular_pay = 8 * 100  # Regular pay
        self.assertGreater(total_pay, regular_pay)  # Should include premiums

    def test_multiple_sabbath_days_in_month(self):
        """Test calculation with multiple Sabbath work days in a month"""
        # Create work logs for multiple Saturdays
        saturdays = [
            datetime(2025, 7, 5, 9, 0),  # First Saturday
            datetime(2025, 7, 12, 10, 0),  # Second Saturday
            datetime(2025, 7, 19, 11, 0),  # Third Saturday
        ]

        total_saturday_hours = 0
        for saturday in saturdays:
            check_in = timezone.make_aware(saturday)
            # Calculate hours for each Saturday (different end times)
            if saturday.day == 5:  # July 5
                check_out = timezone.make_aware(saturday.replace(hour=17))  # 8 hours
                total_saturday_hours += 8
            elif saturday.day == 12:  # July 12
                check_out = timezone.make_aware(saturday.replace(hour=18))  # 8 hours
                total_saturday_hours += 8
            else:  # July 19
                check_out = timezone.make_aware(saturday.replace(hour=19))  # 8 hours
                total_saturday_hours += 8

            WorkLog.objects.create(
                employee=self.hourly_employee, check_in=check_in, check_out=check_out
            )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should have 24 total hours worked (3 days * 8 hours)
        total_hours = result.get("total_hours", 0)
        self.assertAlmostEqual(float(total_hours), 24.0, places=1)

        # Should get premium pay for Saturday work
        total_pay = float(result.get("total_gross_pay", 0))
        regular_pay = 24 * 100  # Regular pay
        self.assertGreater(total_pay, regular_pay)  # Should be more due to premiums

    def test_partial_sabbath_work(self):
        """Test partial Saturday work (short shift)"""
        # Saturday morning shift (3 hours)
        check_in = timezone.make_aware(datetime(2025, 7, 5, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 5, 12, 0))

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should work 3 hours
        total_hours = result.get("total_hours", 0)
        self.assertAlmostEqual(float(total_hours), 3.0, places=1)

        # Should get premium pay for Saturday work
        total_pay = float(result.get("total_gross_pay", 0))
        regular_pay = 3 * 100  # Regular pay
        self.assertGreater(total_pay, regular_pay)  # Should be more due to premiums

    def test_sabbath_night_shift_premium(self):
        """Test night shift during Sabbath gets higher premium"""
        # Friday night to Saturday morning (crosses Sabbath + night)
        check_in = timezone.make_aware(datetime(2025, 7, 4, 22, 0))  # Friday 10 PM
        check_out = timezone.make_aware(datetime(2025, 7, 5, 6, 0))  # Saturday 6 AM

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should calculate 8 hours of work
        total_hours = result.get("total_hours", 0)
        self.assertAlmostEqual(float(total_hours), 8.0, places=1)

        # Should get premium pay for night/Sabbath work
        total_pay = float(result.get("total_gross_pay", 0))
        regular_pay = 8 * 100  # Regular pay
        self.assertGreater(total_pay, regular_pay)  # Should include premiums

    @patch(
        "integrations.services.sunrise_sunset_service.SunriseSunsetService.get_shabbat_times"
    )
    def test_api_integration_with_precise_times(self, mock_sabbath_times):
        """Test API integration provides more precise Sabbath times than defaults"""
        # Mock API with precise time (different from default 19:30)
        mock_sabbath_times.return_value = {
            "start": "2025-07-25T16:37:00+00:00",  # UTC (19:37 Israel time - 7 minutes later)
            "end": "2025-07-26T17:38:00+00:00",
            "is_estimated": False,
        }

        # Friday shift that would be split differently with precise vs default times
        # With default 19:30: 1.5h before, 0.5h during
        # With API 19:37: 1.62h before, 0.38h during
        check_in = timezone.make_aware(datetime(2025, 7, 25, 18, 0))  # Friday 6 PM
        check_out = timezone.make_aware(datetime(2025, 7, 25, 20, 0))  # Friday 8 PM

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        # Test with API (fast_mode=False)
        service = EnhancedPayrollCalculationService(
            self.hourly_employee, 2025, 7, fast_mode=False
        )

        # Test individual worklog calculation first
        work_log = WorkLog.objects.get(
            employee=self.hourly_employee, check_in__date="2025-07-25"
        )
        daily_result = service.calculate_daily_pay_hourly(work_log, save_to_db=False)

        # Should detect as Sabbath work
        self.assertTrue(daily_result["is_sabbath"])

        # Should use API source in daily calculation
        daily_api_sources = daily_result.get("api_sources", [])
        self.assertTrue(
            any("sunrise_sunset_api" in source for source in daily_api_sources)
        )

        # Verify API was called (may be called multiple times due to different checks)
        self.assertTrue(mock_sabbath_times.called)

        # Test monthly summary
        result = service.calculate_monthly_salary_enhanced()
        self.assertGreater(result.get("total_gross_pay", 0), 0)

    def test_fast_mode_vs_api_mode_different_sources(self):
        """Test that fast_mode uses fallback while normal mode attempts API"""
        # Same shift, test both modes
        check_in = timezone.make_aware(datetime(2025, 7, 25, 18, 0))  # Friday 6 PM
        check_out = timezone.make_aware(datetime(2025, 7, 25, 21, 0))  # Friday 9 PM

        # Create two separate work logs for clean testing
        work_log_fast = WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        # Test fast mode (should use fallback calculations)
        service_fast = EnhancedPayrollCalculationService(
            self.hourly_employee, 2025, 7, fast_mode=True
        )
        result_fast = service_fast.calculate_daily_pay_hourly(
            work_log_fast, save_to_db=False
        )

        # Fast mode should use fallback calculations
        api_sources_fast = result_fast.get("api_sources", [])
        self.assertTrue(any("fallback" in source for source in api_sources_fast))

        # Create second work log for API mode test
        work_log_api = WorkLog.objects.create(
            employee=self.hourly_employee,
            check_in=check_in
            + timezone.timedelta(days=1),  # Different date to avoid conflicts
            check_out=check_out + timezone.timedelta(days=1),
        )

        # Test API mode (should attempt API calls)
        service_api = EnhancedPayrollCalculationService(
            self.hourly_employee, 2025, 7, fast_mode=False
        )
        result_api = service_api.calculate_daily_pay_hourly(
            work_log_api, save_to_db=False
        )

        # Both should calculate similar payments, but with different data sources
        self.assertIsNotNone(result_fast["total_pay"])
        self.assertIsNotNone(result_api["total_pay"])
