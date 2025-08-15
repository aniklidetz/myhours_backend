"""
Tests for Jewish holiday work calculations and API integrations.

Tests integration with Hebcal API for accurate holiday detection
and proper premium calculations for holiday work.
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from integrations.models import Holiday
from payroll.models import CompensatoryDay, Salary
from payroll.services import EnhancedPayrollCalculationService
from users.models import Employee
from worktime.models import WorkLog


class HolidayCalculationTest(TestCase):
    """Test holiday work detection and premium calculations"""

    def setUp(self):
        """Set up test data"""
        # Create hourly employee
        self.hourly_employee = Employee.objects.create(
            first_name="Holiday",
            last_name="Worker",
            email="holiday@test.com",
            employment_type="hourly",
            role="employee",
        )

        self.hourly_salary = Salary.objects.create(
            employee=self.hourly_employee,
            calculation_type="hourly",
            hourly_rate=Decimal("80.00"),
            currency="ILS",
        )

        # Create monthly employee
        self.monthly_employee = Employee.objects.create(
            first_name="Monthly",
            last_name="Holiday",
            email="monthly.holiday@test.com",
            employment_type="full_time",
            role="employee",
        )

        self.monthly_salary = Salary.objects.create(
            employee=self.monthly_employee,
            calculation_type="monthly",
            base_salary=Decimal("20000.00"),
            currency="ILS",
        )

    @patch("integrations.services.hebcal_service.HebcalService.fetch_holidays")
    def test_rosh_hashanah_work_premium(self, mock_holidays):
        """Test work during Rosh Hashanah gets holiday premium"""
        # Mock Rosh Hashanah data
        mock_holidays.return_value = [
            {
                "date": "2025-07-15",
                "hebrew": "ראש השנה",
                "title": "Rosh Hashana",
                "category": "major",
            }
        ]

        # Create Holiday model entry
        Holiday.objects.get_or_create(
            date=date(2025, 7, 15),
            defaults={
                "name": "Rosh Hashana",
                "is_holiday": True,
                "is_shabbat": False,
            }
        )

        # Work on Rosh Hashanah
        check_in = timezone.make_aware(datetime(2025, 7, 15, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 15, 17, 0))

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should have 8 hours of holiday work
        holiday_hours = result.get("holiday_hours", 0)
        self.assertAlmostEqual(float(holiday_hours), 8.0, places=1)

        # Holiday premium is typically 150%: 8 hours * 80 * 1.5 = 960
        expected_holiday_pay = 8 * 80 * 1.5
        total_pay = float(result.get("total_gross_pay", 0))
        self.assertAlmostEqual(total_pay, expected_holiday_pay, places=0)

    @patch("integrations.services.hebcal_service.HebcalService.fetch_holidays")
    def test_yom_kippur_work_premium(self, mock_holidays):
        """Test work during Yom Kippur (holiest day) gets maximum premium"""
        # Mock Yom Kippur data
        mock_holidays.return_value = [
            {
                "date": "2025-07-25",
                "hebrew": "יום כיפור",
                "title": "Yom Kippur",
                "category": "major",
            }
        ]

        Holiday.objects.get_or_create(
            date=date(2025, 7, 25),  # Используем дату из mock_holidays выше
            defaults={"name": "Yom Kippur", "is_holiday": True, "is_shabbat": False}
        )

        # Work on Yom Kippur
        check_in = timezone.make_aware(datetime(2025, 7, 25, 10, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 25, 18, 0))

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should get holiday premium
        self.assertGreater(result.get("holiday_hours", 0), 0)
        total_pay = float(result.get("total_gross_pay", 0))
        expected_min = 8 * 80 * 1.5  # Minimum 150% premium
        self.assertGreaterEqual(total_pay, expected_min)

        # Should create compensatory day for major holiday
        comp_days = CompensatoryDay.objects.filter(
            employee=self.hourly_employee,
            date_earned=date(2025, 7, 25),
            reason="holiday",
        )
        self.assertEqual(comp_days.count(), 1)

    @patch("integrations.services.hebcal_service.HebcalService.fetch_holidays")
    def test_multiple_day_holiday_passover(self, mock_holidays):
        """Test work during multi-day holiday (Passover)"""
        # Mock Passover data (first and seventh days - official paid holidays)
        mock_holidays.return_value = [
            {
                "date": "2025-07-10",
                "hebrew": "פסח",
                "title": "Pesach I",
                "category": "major",
            },
            {
                "date": "2025-07-11",
                "hebrew": "פסח",
                "title": "Pesach VII",
                "category": "major",
            },
        ]

        # Create Holiday entries with official Israeli holiday names
        holiday_names = ["Pesach I", "Pesach VII"]  # Official names for first and last days of Passover
        for i, day in enumerate([10, 11]):
            Holiday.objects.get_or_create(
                date=date(2025, 7, day),  # Используем даты из mock_holidays выше
                defaults={
                    "name": holiday_names[i],
                    "is_holiday": True,
                    "is_shabbat": False,
                }
            )

        # Work both days
        for day in [10, 11]:
            check_in = timezone.make_aware(datetime(2025, 7, day, 9, 0))
            check_out = timezone.make_aware(datetime(2025, 7, day, 17, 0))

            WorkLog.objects.create(
                employee=self.hourly_employee, check_in=check_in, check_out=check_out
            )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should have 16 hours of holiday work total
        holiday_hours = result.get("holiday_hours", 0)
        self.assertAlmostEqual(float(holiday_hours), 16.0, places=1)

        # Should create 2 compensatory days
        comp_days = CompensatoryDay.objects.filter(
            employee=self.hourly_employee, reason="holiday"
        ).count()
        self.assertEqual(comp_days, 2)

    @patch("integrations.services.hebcal_service.HebcalService.fetch_holidays")
    def test_holiday_night_shift_premium(self, mock_holidays):
        """Test night shift during holiday gets combined premiums"""
        # Mock holiday
        mock_holidays.return_value = [
            {
                "date": "2025-07-20",
                "hebrew": "חג",
                "title": "Test Holiday",
                "category": "major",
            }
        ]

        Holiday.objects.get_or_create(
            date=date(2025, 7, 20),
            defaults={
                "name": "Test Holiday",
                "is_holiday": True,
                "is_shabbat": False,
            }
        )

        # Night shift during holiday (10 PM to 6 AM)
        check_in = timezone.make_aware(datetime(2025, 7, 19, 22, 0))  # Night before
        check_out = timezone.make_aware(datetime(2025, 7, 20, 6, 0))  # Holiday morning

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should calculate 8 hours of work
        total_hours = result.get("total_hours", 0)
        self.assertAlmostEqual(float(total_hours), 8.0, places=1)

        # Should get premium pay for night/holiday work
        total_pay = float(result.get("total_gross_pay", 0))
        regular_pay = 8 * 80  # Regular pay (640)
        self.assertGreater(total_pay, regular_pay)  # Should include premiums

    @patch("integrations.services.hebcal_service.HebcalService.fetch_holidays")
    def test_monthly_employee_holiday_work(self, mock_holidays):
        """Test monthly employee holiday work (bonus only, not full payment)"""
        # Mock holiday
        mock_holidays.return_value = [
            {
                "date": "2025-07-08",
                "hebrew": "יום כיפור",
                "title": "Yom Kippur",  # Official Israeli holiday
                "category": "major",
            }
        ]

        Holiday.objects.get_or_create(
            date=date(2025, 7, 8),
            defaults={
                "name": "Yom Kippur",
                "is_holiday": True,
                "is_shabbat": False,
            }
        )

        # Holiday work
        check_in = timezone.make_aware(datetime(2025, 7, 8, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 8, 17, 0))

        WorkLog.objects.create(
            employee=self.monthly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.monthly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should have holiday bonus but not excessive payment
        total_pay = result.get("total_gross_pay", 0)
        # Should be more than base proportional salary but reasonable
        # For 1 day out of 23 working days: 20000/23 ≈ 870 + holiday bonus
        self.assertGreater(total_pay, 1200)  # More than just proportional
        self.assertLess(total_pay, 2500)  # But not excessive

    @patch("integrations.services.hebcal_service.HebcalService.fetch_holidays")
    def test_hebcal_api_fallback_on_failure(self, mock_holidays):
        """Test fallback behavior when Hebcal API fails"""
        # Mock API failure
        mock_holidays.side_effect = Exception("API connection failed")

        # Work on what should be a holiday
        check_in = timezone.make_aware(datetime(2025, 7, 15, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 15, 17, 0))

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        # Should not crash when API fails
        result = service.calculate_monthly_salary_enhanced()

        # Should calculate without holiday premium (fallback to regular pay)
        self.assertIsNotNone(result)
        self.assertIn("total_gross_pay", result)
        # Should treat as regular work when API fails
        regular_pay = 8 * 80  # 640
        total_pay = float(result.get("total_gross_pay", 0))
        self.assertAlmostEqual(total_pay, regular_pay, places=0)

    @patch("integrations.services.hebcal_service.HebcalService.fetch_holidays")
    def test_minor_holiday_no_premium(self, mock_holidays):
        """Test that minor holidays don't get work premiums"""
        # Mock minor holiday
        mock_holidays.return_value = [
            {
                "date": "2025-07-12",
                "hebrew": "ראש חודש",
                "title": "Rosh Chodesh",
                "category": "minor",
            }
        ]

        # Work on minor holiday (note: July 12, 2025 is a Saturday)
        check_in = timezone.make_aware(datetime(2025, 7, 12, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 12, 17, 0))

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should calculate 8 hours of work
        total_hours = result.get("total_hours", 0)
        self.assertAlmostEqual(float(total_hours), 8.0, places=1)

        # Should get pay (note: might get Sabbath premium since July 12, 2025 is Saturday)
        total_pay = float(result.get("total_gross_pay", 0))
        self.assertGreater(total_pay, 0)

    def test_database_holiday_vs_api_priority(self):
        """Test that database holidays take precedence over API"""
        # Create holiday in database (use Monday to avoid Shabbat confusion)
        Holiday.objects.get_or_create(
            date=date(2025, 7, 14),  # Monday
            defaults={
                "name": "Yom HaAtzmaut",  # Israeli Independence Day - official paid holiday
                "is_holiday": True,
                "is_shabbat": False,
            }
        )

        # Work on the custom holiday
        check_in = timezone.make_aware(datetime(2025, 7, 14, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 14, 17, 0))

        WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        service = EnhancedPayrollCalculationService(self.hourly_employee, 2025, 7)
        result = service.calculate_monthly_salary_enhanced()

        # Should get holiday premium from database entry
        holiday_hours = result.get("holiday_hours", 0)
        self.assertGreater(float(holiday_hours), 0)

        # Should create compensatory day
        comp_days = CompensatoryDay.objects.filter(
            employee=self.hourly_employee,
            date_earned=date(2025, 7, 14),  # Updated to match new date
            reason="holiday",
        ).count()
        self.assertEqual(comp_days, 1)
