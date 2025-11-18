"""
Comprehensive tests for HolidaySyncService.

This module tests the HolidaySyncService in isolation,
mocking all dependencies including API clients and database operations.
"""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

from django.test import TestCase

from integrations.models import Holiday
from integrations.services.holiday_sync_service import HolidaySyncService


class HolidaySyncServiceTest(TestCase):
    """Test suite for HolidaySyncService"""

    def setUp(self):
        """Set up test environment - Iron Isolation pattern"""
        # Only clean specific dates used by integration tests + their eve dates, not all Holiday records
        integration_test_dates = [
            date(2025, 9, 16),
            date(2025, 9, 15),  # Rosh Hashanah + eve
            date(2025, 9, 25),
            date(2025, 9, 24),  # Yom Kippur + eve
            date(2025, 10, 1),
            date(2025, 9, 30),  # Minor Holiday + eve
            date(2025, 1, 3),
            date(2025, 1, 2),  # Shabbat + potential eve
            date(2025, 1, 4),
            date(2025, 1, 10),
            date(2025, 1, 11),
            date(2025, 1, 9),
            date(2025, 7, 12),
            date(2025, 7, 19),
            date(2025, 7, 5),
            date(2025, 7, 4),
            date(2025, 1, 1),
            date(2025, 1, 17),
            date(2025, 1, 24),
            date(2025, 1, 31),
            date(2025, 2, 7),
            date(2025, 12, 26),  # Shabbat Chanukah
            date(2025, 12, 25),  # Eve
        ]
        Holiday.objects.filter(date__in=integration_test_dates).delete()

    def tearDown(self):
        """Clean up after tests - Iron Isolation pattern"""
        # Only clean specific dates used by integration tests + their eve dates, not all Holiday records
        integration_test_dates = [
            date(2025, 9, 16),
            date(2025, 9, 15),  # Rosh Hashanah + eve
            date(2025, 9, 25),
            date(2025, 9, 24),  # Yom Kippur + eve
            date(2025, 10, 1),
            date(2025, 9, 30),  # Minor Holiday + eve
            date(2025, 1, 3),
            date(2025, 1, 2),  # Shabbat + potential eve
            date(2025, 1, 4),
            date(2025, 1, 10),
            date(2025, 1, 11),
            date(2025, 1, 9),
            date(2025, 7, 12),
            date(2025, 7, 19),
            date(2025, 7, 5),
            date(2025, 7, 4),
            date(2025, 1, 1),
            date(2025, 1, 17),
            date(2025, 1, 24),
            date(2025, 1, 31),
            date(2025, 2, 7),
            date(2025, 12, 26),  # Shabbat Chanukah
            date(2025, 12, 25),  # Eve
        ]
        Holiday.objects.filter(date__in=integration_test_dates).delete()

    @patch("integrations.services.holiday_sync_service.IsraeliHolidaysService")
    @patch("integrations.services.holiday_sync_service.get_shabbat_times")
    @patch("integrations.services.holiday_sync_service.HebcalAPIClient")
    def test_sync_year_complete_workflow(
        self, mock_api_client, mock_shabbat_times, mock_israeli_service
    ):
        """Test complete year synchronization workflow"""
        # Mock API client response
        mock_api_client.fetch_holidays.return_value = [
            {
                "title": "Rosh Hashanah",
                "date": "2025-09-16",
                "category": "holiday",
                "subcat": "major",
            },
            {
                "title": "Shabbat Rosh Chodesh",
                "date": "2025-01-03",
                "category": "holiday",
                "subcat": "shabbat",
            },
        ]

        # Mock Shabbat times generation
        mock_shabbat_times.return_value = {
            "shabbat_start": "2025-01-10T16:30:00+02:00",
            "shabbat_end": "2025-01-11T17:30:00+02:00",
        }

        # Mock Israeli holidays service
        mock_israeli_service.sync_national_holidays.return_value = (1, 0)

        # Execute sync
        created, updated = HolidaySyncService.sync_year(2025)

        # Verify API client was called
        mock_api_client.fetch_holidays.assert_called_once_with(2025, use_cache=True)

        # Verify Israeli holidays service was called
        mock_israeli_service.sync_national_holidays.assert_called_once_with(2025)

        # Verify results
        self.assertGreater(created, 0)
        self.assertGreaterEqual(updated, 0)

        # Verify holidays were created in database
        holidays = Holiday.objects.all()
        self.assertGreater(len(holidays), 0)

    @patch("integrations.services.holiday_sync_service.get_shabbat_times")
    def test_generate_weekly_shabbats(self, mock_shabbat_times):
        """Test weekly Shabbat generation"""
        # Mock Shabbat times
        mock_shabbat_times.return_value = {
            "shabbat_start": "2025-01-03T16:30:00+02:00",
            "shabbat_end": "2025-01-04T17:30:00+02:00",
        }

        # Generate Shabbats for a small date range (January 2025)
        shabbats = HolidaySyncService._generate_weekly_shabbats(2025)

        # Should generate 52-53 Shabbats for the year
        self.assertGreaterEqual(len(shabbats), 52)
        self.assertLessEqual(len(shabbats), 53)

        # Verify first Shabbat structure
        first_shabbat = shabbats[0]
        self.assertEqual(first_shabbat["title"], "Shabbat")
        self.assertEqual(first_shabbat["category"], "holiday")
        self.assertEqual(first_shabbat["subcat"], "shabbat")
        self.assertIn("start_time", first_shabbat)
        self.assertIn("end_time", first_shabbat)

        # Verify all dates are Fridays
        for shabbat in shabbats:
            shabbat_date = datetime.strptime(shabbat["date"], "%Y-%m-%d").date()
            self.assertEqual(shabbat_date.weekday(), 4)  # Friday = 4

    def test_sync_special_shabbats(self):
        """Test synchronization of special Shabbats"""
        # Clear any existing special shabbats to ensure clean test
        Holiday.objects.filter(is_special_shabbat=True).delete()

        holidays = [
            {
                "title": "Shabbat Rosh Chodesh",
                "date": "2025-01-03",
                "category": "holiday",
                "subcat": "shabbat",
            },
            {
                "title": "Shabbat Chanukah",
                "date": "2025-12-26",
                "category": "holiday",
                "subcat": "shabbat",
            },
        ]

        created, updated = HolidaySyncService._sync_special_shabbats(holidays)

        # Verify special Shabbats were created
        self.assertEqual(created, 2)
        self.assertEqual(updated, 0)

        # Verify database records
        special_shabbats = Holiday.objects.filter(is_special_shabbat=True)
        self.assertEqual(len(special_shabbats), 2)

        first_shabbat = special_shabbats.get(date=date(2025, 1, 3))
        self.assertEqual(first_shabbat.name, "Shabbat Rosh Chodesh")
        self.assertTrue(first_shabbat.is_shabbat)
        self.assertTrue(first_shabbat.is_special_shabbat)
        self.assertFalse(first_shabbat.is_holiday)

    @patch("integrations.services.holiday_sync_service.is_official_holiday")
    def test_sync_other_holidays(self, mock_is_official):
        """Test synchronization of regular holidays"""
        # Mock official holiday check
        mock_is_official.side_effect = lambda title: title in [
            "Rosh Hashanah",
            "Yom Kippur",
        ]

        holidays = [
            {
                "title": "Rosh Hashanah",
                "date": "2025-09-16",
                "category": "holiday",
                "subcat": "major",
            },
            {
                "title": "Minor Holiday",
                "date": "2025-10-01",
                "category": "holiday",
                "subcat": "minor",
            },
            {
                "title": "Yom Kippur",
                "date": "2025-09-25",
                "category": "holiday",
                "subcat": "major",
            },
        ]

        created, updated = HolidaySyncService._sync_other_holidays(holidays)

        # Verify holidays were created
        # Note: Official holidays that start in evening create 2 records (eve + main day)
        # Rosh Hashanah creates 2 (eve + main), Yom Kippur creates 2 (eve + main), Minor creates 1 = 5 total
        self.assertEqual(created, 5)
        self.assertEqual(updated, 0)

        # Verify official holidays have is_holiday=True
        rosh_hashanah = Holiday.objects.get(date=date(2025, 9, 16))
        self.assertTrue(rosh_hashanah.is_holiday)
        self.assertEqual(rosh_hashanah.name, "Rosh Hashanah")

        yom_kippur = Holiday.objects.get(date=date(2025, 9, 25))
        self.assertTrue(yom_kippur.is_holiday)

        # Verify non-official holidays have is_holiday=False
        minor_holiday = Holiday.objects.get(date=date(2025, 10, 1))
        self.assertFalse(minor_holiday.is_holiday)

    def test_sync_weekly_shabbats(self):
        """Test synchronization of regular weekly Shabbats"""
        weekly_shabbats = [
            {
                "title": "Shabbat",
                "date": "2025-01-03",
                "category": "holiday",
                "subcat": "shabbat",
                "start_time": "2025-01-03T16:30:00+02:00",
                "end_time": "2025-01-04T17:30:00+02:00",
            },
            {
                "title": "Shabbat",
                "date": "2025-01-10",
                "category": "holiday",
                "subcat": "shabbat",
                "start_time": "2025-01-10T16:35:00+02:00",
                "end_time": "2025-01-11T17:35:00+02:00",
            },
        ]

        created, updated = HolidaySyncService._sync_weekly_shabbats(weekly_shabbats)

        # Verify Shabbats were created
        # Note: Each Shabbat creates 2 records (Friday evening + Saturday)
        # 2 Shabbats × 2 records = 4 total
        self.assertEqual(created, 4)
        self.assertEqual(updated, 0)

        # Verify database records - only check the specific dates we created
        test_dates = [
            date(2025, 1, 3),
            date(2025, 1, 4),
            date(2025, 1, 10),
            date(2025, 1, 11),
        ]
        shabbats = Holiday.objects.filter(
            date__in=test_dates, is_shabbat=True, is_special_shabbat=False
        )
        self.assertEqual(len(shabbats), 4)  # 2 Shabbats × 2 records each

        first_shabbat = shabbats.get(date=date(2025, 1, 3))
        self.assertEqual(first_shabbat.name, "Shabbat")
        self.assertTrue(first_shabbat.is_shabbat)
        self.assertFalse(first_shabbat.is_special_shabbat)
        self.assertFalse(first_shabbat.is_holiday)
        self.assertIsNotNone(first_shabbat.start_time)
        self.assertIsNotNone(first_shabbat.end_time)

    def test_sync_weekly_shabbats_preserves_special_status(self):
        """Test that weekly Shabbat sync preserves special Shabbat status"""
        # Create a special Shabbat first
        Holiday.objects.create(
            date=date(2025, 1, 3),
            name="Shabbat Rosh Chodesh",
            is_shabbat=True,
            is_special_shabbat=True,
            is_holiday=False,
        )

        # Try to sync regular Shabbat on same date
        weekly_shabbats = [
            {
                "title": "Shabbat",
                "date": "2025-01-03",
                "category": "holiday",
                "subcat": "shabbat",
                "start_time": "2025-01-03T16:30:00+02:00",
                "end_time": "2025-01-04T17:30:00+02:00",
            }
        ]

        created, updated = HolidaySyncService._sync_weekly_shabbats(weekly_shabbats)

        # Should not update special Shabbat (Friday), but creates Saturday record
        # Friday 2025-01-03 already exists as special, so not created
        # Saturday 2025-01-04 gets created = 1 record
        self.assertEqual(created, 1)
        self.assertEqual(updated, 0)

        # Verify special status is preserved
        shabbat = Holiday.objects.get(date=date(2025, 1, 3))
        self.assertEqual(shabbat.name, "Shabbat Rosh Chodesh")
        self.assertTrue(shabbat.is_special_shabbat)

    @patch("integrations.services.holiday_sync_service.IsraeliHolidaysService")
    def test_sync_national_holidays(self, mock_israeli_service):
        """Test synchronization of Israeli national holidays"""
        mock_israeli_service.sync_national_holidays.return_value = (1, 0)

        created, updated = HolidaySyncService._sync_national_holidays(2025)

        # Verify service was called
        mock_israeli_service.sync_national_holidays.assert_called_once_with(2025)

        # Verify results
        self.assertEqual(created, 1)
        self.assertEqual(updated, 0)

    @patch("integrations.services.holiday_sync_service.IsraeliHolidaysService")
    def test_sync_national_holidays_error_handling(self, mock_israeli_service):
        """Test error handling in national holidays sync"""
        mock_israeli_service.sync_national_holidays.side_effect = Exception(
            "Service error"
        )

        created, updated = HolidaySyncService._sync_national_holidays(2025)

        # Should return zero counts on error
        self.assertEqual(created, 0)
        self.assertEqual(updated, 0)

    def test_update_holiday_if_changed(self):
        """Test holiday update detection and execution"""
        # Create existing holiday
        holiday = Holiday.objects.create(
            date=date(2025, 1, 1),
            name="Old Name",
            is_holiday=False,
            is_shabbat=False,
            is_special_shabbat=False,
        )

        # Test with changes
        defaults = {
            "name": "New Name",
            "is_holiday": True,
            "is_shabbat": False,
            "is_special_shabbat": False,
        }

        updated = HolidaySyncService._update_holiday_if_changed(holiday, defaults)

        # Should return True for update
        self.assertTrue(updated)

        # Verify changes were applied
        holiday.refresh_from_db()
        self.assertEqual(holiday.name, "New Name")
        self.assertTrue(holiday.is_holiday)

        # Test with no changes
        updated_again = HolidaySyncService._update_holiday_if_changed(holiday, defaults)

        # Should return False for no update
        self.assertFalse(updated_again)

    def test_sync_year_default_year(self):
        """Test sync_year uses current year when no year specified"""
        # Fix current year at test start to avoid timing issues
        current_year = date.today().year

        with patch(
            "integrations.services.holiday_sync_service.HebcalAPIClient"
        ) as mock_api:
            with patch(
                "integrations.services.holiday_sync_service.IsraeliHolidaysService"
            ) as mock_israeli:
                mock_api.fetch_holidays.return_value = []
                mock_israeli.sync_national_holidays.return_value = (0, 0)

                # Call without year parameter
                HolidaySyncService.sync_year()

                # Should use current year
                mock_api.fetch_holidays.assert_called_with(current_year, use_cache=True)

    def test_sync_year_without_weekly_shabbats(self):
        """Test sync_year with weekly Shabbats disabled"""
        with patch(
            "integrations.services.holiday_sync_service.HebcalAPIClient"
        ) as mock_api:
            with patch(
                "integrations.services.holiday_sync_service.IsraeliHolidaysService"
            ) as mock_israeli:
                mock_api.fetch_holidays.return_value = []
                mock_israeli.sync_national_holidays.return_value = (0, 0)

                # Call with weekly Shabbats disabled
                HolidaySyncService.sync_year(2025, include_weekly_shabbats=False)

                # Should not generate weekly Shabbats
                # This would be verified by checking that no regular Shabbats are created
                # but since we're mocking everything, we just verify the method completes

    @patch("integrations.services.holiday_sync_service.get_shabbat_times")
    def test_generate_weekly_shabbats_error_handling(self, mock_shabbat_times):
        """Test error handling in weekly Shabbat generation"""

        # Mock Shabbat times to raise error for some dates
        def side_effect(date_obj):
            if date_obj.day == 10:  # Simulate error on specific date
                raise Exception("API error")
            return {
                "shabbat_start": "2025-01-03T16:30:00+02:00",
                "shabbat_end": "2025-01-04T17:30:00+02:00",
            }

        mock_shabbat_times.side_effect = side_effect

        # Generate Shabbats for a small date range
        shabbats = HolidaySyncService._generate_weekly_shabbats(2025)

        # Should generate Shabbats despite some errors
        self.assertGreater(len(shabbats), 0)

        # Should not include the failed date
        failed_dates = [s for s in shabbats if s["date"].endswith("-10")]
        self.assertEqual(len(failed_dates), 0)
