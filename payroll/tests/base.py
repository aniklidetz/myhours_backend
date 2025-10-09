"""
Base test classes for payroll tests with proper isolation and mocking.

This module provides base classes that ensure:
- Proper test isolation (Iron Isolation pattern)
- Mocked external API calls
- Consistent timezone handling
- Centralized Holiday cleanup
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytz
from django.test import TestCase
from django.utils import timezone

from integrations.models import Holiday
from payroll.models import DailyPayrollCalculation, MonthlyPayrollSummary
from users.models import Employee
from worktime.models import WorkLog


class PayrollTestBase(TestCase):
    """
    Base class for all payroll tests with proper isolation.

    Features:
    - Cleans up ALL Holiday records before and after tests
    - Provides Israeli timezone utilities
    - Ensures no data pollution between tests
    """

    ISRAEL_TZ = pytz.timezone("Asia/Jerusalem")

    @classmethod
    def setUpClass(cls):
        """Clean ALL test data before test class runs"""
        super().setUpClass()
        # Clean ALL holidays to ensure isolation from other test modules
        Holiday.objects.all().delete()
        DailyPayrollCalculation.objects.all().delete()
        MonthlyPayrollSummary.objects.all().delete()

    def setUp(self):
        """Clean data before each test"""
        super().setUp()
        # Clean ALL holidays before each test
        Holiday.objects.all().delete()
        WorkLog.objects.all().delete()
        DailyPayrollCalculation.objects.all().delete()
        MonthlyPayrollSummary.objects.all().delete()

    def tearDown(self):
        """Clean data after each test"""
        super().tearDown()
        # Clean ALL holidays after each test
        Holiday.objects.all().delete()
        WorkLog.objects.all().delete()
        DailyPayrollCalculation.objects.all().delete()
        MonthlyPayrollSummary.objects.all().delete()

    @classmethod
    def tearDownClass(cls):
        """Final cleanup after all tests in class"""
        Holiday.objects.all().delete()
        super().tearDownClass()

    def make_israel_aware(self, dt: datetime) -> datetime:
        """Convert datetime to Israeli timezone-aware datetime"""
        if dt.tzinfo is None:
            return self.ISRAEL_TZ.localize(dt)
        return dt.astimezone(self.ISRAEL_TZ)


class MockedShabbatTestBase(PayrollTestBase):
    """
    Base class for payroll tests that need mocked Shabbat times.

    Automatically mocks get_shabbat_times() to prevent external API calls.
    Provides helper method to set specific Shabbat times for tests.
    """

    def setUp(self):
        """Set up with mocked Shabbat service"""
        super().setUp()

        # Start patching get_shabbat_times
        self.shabbat_patcher = patch(
            'integrations.services.unified_shabbat_service.get_shabbat_times'
        )
        self.mock_get_shabbat_times = self.shabbat_patcher.start()

        # Default mock implementation - returns standard Shabbat times
        self.mock_get_shabbat_times.side_effect = self._default_shabbat_times

    def tearDown(self):
        """Stop patching"""
        self.shabbat_patcher.stop()
        super().tearDown()

    def _default_shabbat_times(self, friday_date: date):
        """
        Default mock implementation for get_shabbat_times.

        Returns standard Israeli Shabbat times:
        - Friday 17:30 (candle lighting)
        - Saturday 18:30 (havdalah)
        """
        # Ensure we have Friday
        if isinstance(friday_date, datetime):
            friday_date = friday_date.date()

        # Adjust to Friday if needed
        if friday_date.weekday() > 4:  # Saturday or Sunday
            friday_date = friday_date - timedelta(days=friday_date.weekday() - 4)
        elif friday_date.weekday() < 4:  # Monday-Thursday
            friday_date = friday_date + timedelta(days=4 - friday_date.weekday())

        saturday_date = friday_date + timedelta(days=1)

        # Standard Israeli Shabbat times
        shabbat_start = self.ISRAEL_TZ.localize(
            datetime.combine(friday_date, datetime.strptime("17:30", "%H:%M").time())
        )
        shabbat_end = self.ISRAEL_TZ.localize(
            datetime.combine(saturday_date, datetime.strptime("18:30", "%H:%M").time())
        )

        return {
            "shabbat_start": shabbat_start.isoformat(),
            "shabbat_end": shabbat_end.isoformat(),
            "friday_date": friday_date.isoformat(),
            "calculation_method": "mocked",
            "coordinates": {"lat": 31.7683, "lng": 35.2137}
        }

    def set_shabbat_times(self, friday_date: date, start_time: str, end_time: str):
        """
        Set specific Shabbat times for a test.

        Args:
            friday_date: The Friday date
            start_time: Start time in "HH:MM" format (Friday)
            end_time: End time in "HH:MM" format (Saturday)
        """
        saturday_date = friday_date + timedelta(days=1)

        shabbat_start = self.ISRAEL_TZ.localize(
            datetime.combine(friday_date, datetime.strptime(start_time, "%H:%M").time())
        )
        shabbat_end = self.ISRAEL_TZ.localize(
            datetime.combine(saturday_date, datetime.strptime(end_time, "%H:%M").time())
        )

        # Update mock to return these specific times
        def specific_times(date_arg):
            return {
                "shabbat_start": shabbat_start.isoformat(),
                "shabbat_end": shabbat_end.isoformat(),
                "friday_date": friday_date.isoformat(),
                "calculation_method": "mocked_custom",
                "coordinates": {"lat": 31.7683, "lng": 35.2137}
            }

        self.mock_get_shabbat_times.side_effect = specific_times

    def create_shabbat_holiday(self, friday_date: date, saturday_date: date = None):
        """
        Create Holiday records for Shabbat with proper times.

        Args:
            friday_date: The Friday date
            saturday_date: Optional Saturday date (defaults to friday_date + 1)
        """
        from datetime import timedelta

        if saturday_date is None:
            saturday_date = friday_date + timedelta(days=1)

        # Get Shabbat times from mock
        times = self._default_shabbat_times(friday_date)
        shabbat_start = datetime.fromisoformat(times["shabbat_start"])
        shabbat_end = datetime.fromisoformat(times["shabbat_end"])

        # Create Friday evening record
        friday_midnight = self.ISRAEL_TZ.localize(
            datetime.combine(saturday_date, datetime.min.time())
        )

        Holiday.objects.create(
            date=friday_date,
            name="Shabbat",
            is_shabbat=True,
            is_special_shabbat=False,
            is_holiday=False,
            start_time=shabbat_start,
            end_time=friday_midnight
        )

        # Create Saturday record
        Holiday.objects.create(
            date=saturday_date,
            name="Shabbat",
            is_shabbat=True,
            is_special_shabbat=False,
            is_holiday=False,
            start_time=friday_midnight,
            end_time=shabbat_end
        )


# Import for convenience
from datetime import timedelta
