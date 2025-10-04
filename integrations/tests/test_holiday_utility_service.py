"""
Comprehensive tests for HolidayUtilityService.

This module tests the HolidayUtilityService with both unit tests
and integration tests with the database, focusing on utility functions
for holiday queries and checks.
"""

from datetime import date, datetime
from unittest.mock import patch

from django.test import TestCase

from integrations.models import Holiday
from integrations.services.holiday_utility_service import HolidayUtilityService


class HolidayUtilityServiceTest(TestCase):
    """Test suite for HolidayUtilityService"""

    def setUp(self):
        """Set up test environment with sample holiday data"""
        Holiday.objects.all().delete()

        # Create test holidays using get_or_create to avoid conflicts
        self.new_year, _ = Holiday.objects.get_or_create(
            date=date(2025, 1, 1),
            defaults={
                "name": "New Year",
                "is_holiday": True,
                "is_shabbat": False,
                "is_special_shabbat": False
            }
        )

        self.regular_shabbat, _ = Holiday.objects.get_or_create(
            date=date(2025, 1, 3),
            defaults={
                "name": "Shabbat",
                "is_holiday": False,
                "is_shabbat": True,
                "is_special_shabbat": False,
                "start_time": datetime(2025, 1, 3, 16, 30, tzinfo=datetime.now().astimezone().tzinfo),
                "end_time": datetime(2025, 1, 4, 17, 30, tzinfo=datetime.now().astimezone().tzinfo)
            }
        )

        self.special_shabbat, _ = Holiday.objects.get_or_create(
            date=date(2025, 1, 10),
            defaults={
                "name": "Shabbat Rosh Chodesh",
                "is_holiday": False,
                "is_shabbat": True,
                "is_special_shabbat": True
            }
        )

        self.non_holiday, _ = Holiday.objects.get_or_create(
            date=date(2025, 1, 15),
            defaults={
                "name": "Minor Event",
                "is_holiday": False,
                "is_shabbat": False,
                "is_special_shabbat": False
            }
        )

    def tearDown(self):
        """Clean up after tests"""
        Holiday.objects.all().delete()

    def test_get_holiday_name_existing_holiday(self):
        """Test getting holiday name for existing holiday in database"""
        name = HolidayUtilityService.get_holiday_name(date(2025, 1, 1))
        self.assertEqual(name, "New Year")

    def test_get_holiday_name_non_holiday(self):
        """Test getting holiday name for non-holiday date"""
        name = HolidayUtilityService.get_holiday_name(date(2025, 1, 15))
        self.assertIsNone(name)

    def test_get_holiday_name_shabbat(self):
        """Test getting holiday name for Shabbat (should return None since is_holiday=False)"""
        name = HolidayUtilityService.get_holiday_name(date(2025, 1, 3))
        self.assertIsNone(name)

    def test_get_holiday_name_nonexistent_date(self):
        """Test getting holiday name for date not in database"""
        name = HolidayUtilityService.get_holiday_name(date(2025, 12, 25))
        self.assertIsNone(name)

    @patch("integrations.services.holiday_utility_service.HebcalAPIClient")
    def test_get_holiday_name_api_fallback(self, mock_api_client):
        """Test API fallback when holiday not found in database"""
        # Mock API response
        mock_api_client.fetch_holidays.return_value = [
            {
                "title": "API Holiday",
                "date": "2025-12-25",
                "category": "holiday",
                "subcat": "major"
            }
        ]

        # Mock is_official_holiday to return True
        with patch("integrations.services.holiday_utility_service.is_official_holiday") as mock_official:
            mock_official.return_value = True

            name = HolidayUtilityService.get_holiday_name(date(2025, 12, 25))

            # Should use API fallback
            mock_api_client.fetch_holidays.assert_called_once_with(2025, use_cache=True)
            self.assertEqual(name, "API Holiday")

    @patch("integrations.services.holiday_utility_service.HebcalAPIClient")
    def test_get_holiday_name_api_fallback_non_official(self, mock_api_client):
        """Test API fallback returns None for non-official holidays"""
        # Mock API response
        mock_api_client.fetch_holidays.return_value = [
            {
                "title": "Non-Official Holiday",
                "date": "2025-12-25",
                "category": "holiday",
                "subcat": "minor"
            }
        ]

        # Mock is_official_holiday to return False
        with patch("integrations.services.holiday_utility_service.is_official_holiday") as mock_official:
            mock_official.return_value = False

            name = HolidayUtilityService.get_holiday_name(date(2025, 12, 25))

            # Should return None for non-official holiday
            self.assertIsNone(name)

    def test_is_holiday_existing_holiday(self):
        """Test is_holiday for existing holiday in database"""
        is_holiday = HolidayUtilityService.is_holiday(date(2025, 1, 1))
        self.assertTrue(is_holiday)

    def test_is_holiday_non_holiday(self):
        """Test is_holiday for non-holiday date"""
        is_holiday = HolidayUtilityService.is_holiday(date(2025, 1, 15))
        self.assertFalse(is_holiday)

    def test_is_holiday_shabbat(self):
        """Test is_holiday for Shabbat (should return False since is_holiday=False)"""
        is_holiday = HolidayUtilityService.is_holiday(date(2025, 1, 3))
        self.assertFalse(is_holiday)

    def test_is_holiday_nonexistent_date(self):
        """Test is_holiday for date not in database"""
        is_holiday = HolidayUtilityService.is_holiday(date(2025, 12, 25))
        self.assertFalse(is_holiday)

    @patch("integrations.services.holiday_utility_service.HebcalAPIClient")
    def test_is_holiday_api_fallback(self, mock_api_client):
        """Test API fallback for is_holiday check"""
        # Mock API response
        mock_api_client.fetch_holidays.return_value = [
            {
                "title": "API Holiday",
                "date": "2025-12-25",
                "category": "holiday",
                "subcat": "major"
            }
        ]

        # Mock is_official_holiday to return True
        with patch("integrations.services.holiday_utility_service.is_official_holiday") as mock_official:
            mock_official.return_value = True

            is_holiday = HolidayUtilityService.is_holiday(date(2025, 12, 25))

            # Should use API fallback
            mock_api_client.fetch_holidays.assert_called_once_with(2025, use_cache=True)
            self.assertTrue(is_holiday)

    def test_is_shabbat_regular_shabbat(self):
        """Test is_shabbat for regular Shabbat"""
        is_shabbat = HolidayUtilityService.is_shabbat(date(2025, 1, 3))
        self.assertTrue(is_shabbat)

    def test_is_shabbat_special_shabbat(self):
        """Test is_shabbat for special Shabbat"""
        is_shabbat = HolidayUtilityService.is_shabbat(date(2025, 1, 10))
        self.assertTrue(is_shabbat)

    def test_is_shabbat_non_shabbat(self):
        """Test is_shabbat for non-Shabbat date"""
        is_shabbat = HolidayUtilityService.is_shabbat(date(2025, 1, 1))
        self.assertFalse(is_shabbat)

    def test_is_shabbat_nonexistent_date(self):
        """Test is_shabbat for date not in database"""
        is_shabbat = HolidayUtilityService.is_shabbat(date(2025, 12, 25))
        self.assertFalse(is_shabbat)

    def test_is_special_shabbat_special_shabbat(self):
        """Test is_special_shabbat for special Shabbat"""
        is_special = HolidayUtilityService.is_special_shabbat(date(2025, 1, 10))
        self.assertTrue(is_special)

    def test_is_special_shabbat_regular_shabbat(self):
        """Test is_special_shabbat for regular Shabbat"""
        is_special = HolidayUtilityService.is_special_shabbat(date(2025, 1, 3))
        self.assertFalse(is_special)

    def test_is_special_shabbat_non_shabbat(self):
        """Test is_special_shabbat for non-Shabbat date"""
        is_special = HolidayUtilityService.is_special_shabbat(date(2025, 1, 1))
        self.assertFalse(is_special)

    def test_get_holiday_info_holiday(self):
        """Test get_holiday_info for holiday"""
        info = HolidayUtilityService.get_holiday_info(date(2025, 1, 1))

        expected_info = {
            "exists": True,
            "name": "New Year",
            "is_holiday": True,
            "is_shabbat": False,
            "is_special_shabbat": False,
            "start_time": None,
            "end_time": None,
        }

        self.assertEqual(info, expected_info)

    def test_get_holiday_info_regular_shabbat(self):
        """Test get_holiday_info for regular Shabbat"""
        info = HolidayUtilityService.get_holiday_info(date(2025, 1, 3))

        expected_info = {
            "exists": True,
            "name": "Shabbat",
            "is_holiday": False,
            "is_shabbat": True,
            "is_special_shabbat": False,
            "start_time": self.regular_shabbat.start_time,
            "end_time": self.regular_shabbat.end_time,
        }

        self.assertEqual(info, expected_info)

    def test_get_holiday_info_special_shabbat(self):
        """Test get_holiday_info for special Shabbat"""
        info = HolidayUtilityService.get_holiday_info(date(2025, 1, 10))

        expected_info = {
            "exists": True,
            "name": "Shabbat Rosh Chodesh",
            "is_holiday": False,
            "is_shabbat": True,
            "is_special_shabbat": True,
            "start_time": None,
            "end_time": None,
        }

        self.assertEqual(info, expected_info)

    def test_get_holiday_info_nonexistent(self):
        """Test get_holiday_info for nonexistent date"""
        info = HolidayUtilityService.get_holiday_info(date(2025, 12, 25))

        expected_info = {
            "exists": False,
            "name": None,
            "is_holiday": False,
            "is_shabbat": False,
            "is_special_shabbat": False,
            "start_time": None,
            "end_time": None,
        }

        self.assertEqual(info, expected_info)

    def test_error_handling_get_holiday_name(self):
        """Test error handling in get_holiday_name"""
        # Mock database error
        with patch("integrations.services.holiday_utility_service.Holiday.objects.filter") as mock_filter:
            mock_filter.side_effect = Exception("Database error")

            name = HolidayUtilityService.get_holiday_name(date(2025, 1, 1))
            self.assertIsNone(name)

    def test_error_handling_is_holiday(self):
        """Test error handling in is_holiday"""
        # Mock database error
        with patch("integrations.services.holiday_utility_service.Holiday.objects.filter") as mock_filter:
            mock_filter.side_effect = Exception("Database error")

            is_holiday = HolidayUtilityService.is_holiday(date(2025, 1, 1))
            self.assertFalse(is_holiday)

    def test_error_handling_is_shabbat(self):
        """Test error handling in is_shabbat"""
        # Mock database error
        with patch("integrations.services.holiday_utility_service.Holiday.objects.filter") as mock_filter:
            mock_filter.side_effect = Exception("Database error")

            is_shabbat = HolidayUtilityService.is_shabbat(date(2025, 1, 3))
            self.assertFalse(is_shabbat)

    def test_error_handling_is_special_shabbat(self):
        """Test error handling in is_special_shabbat"""
        # Mock database error
        with patch("integrations.services.holiday_utility_service.Holiday.objects.filter") as mock_filter:
            mock_filter.side_effect = Exception("Database error")

            is_special = HolidayUtilityService.is_special_shabbat(date(2025, 1, 10))
            self.assertFalse(is_special)

    def test_error_handling_get_holiday_info(self):
        """Test error handling in get_holiday_info"""
        # Mock database error
        with patch("integrations.services.holiday_utility_service.Holiday.objects.filter") as mock_filter:
            mock_filter.side_effect = Exception("Database error")

            info = HolidayUtilityService.get_holiday_info(date(2025, 1, 1))
            expected_info = {"exists": False, "name": None}
            self.assertEqual(info, expected_info)

    @patch("integrations.services.holiday_utility_service.HebcalAPIClient")
    def test_api_fallback_error_handling(self, mock_api_client):
        """Test error handling in API fallback methods"""
        # Mock API error
        mock_api_client.fetch_holidays.side_effect = Exception("API error")

        # Should return None/False on API error
        name = HolidayUtilityService.get_holiday_name(date(2025, 12, 25))
        self.assertIsNone(name)

        is_holiday = HolidayUtilityService.is_holiday(date(2025, 12, 25))
        self.assertFalse(is_holiday)

    @patch("integrations.services.holiday_utility_service.HebcalAPIClient")
    def test_api_fallback_invalid_date_format(self, mock_api_client):
        """Test API fallback with invalid date format in response"""
        # Mock API response with invalid date
        mock_api_client.fetch_holidays.return_value = [
            {
                "title": "Invalid Date Holiday",
                "date": "invalid-date",
                "category": "holiday",
                "subcat": "major"
            }
        ]

        # Should handle invalid date gracefully
        name = HolidayUtilityService.get_holiday_name(date(2025, 12, 25))
        self.assertIsNone(name)

        is_holiday = HolidayUtilityService.is_holiday(date(2025, 12, 25))
        self.assertFalse(is_holiday)

    def test_multiple_holidays_same_date(self):
        """Test behavior when multiple holidays exist for same date"""
        # This test is conceptual since the Holiday model has a unique constraint on date
        # In practice, this scenario shouldn't occur, but we test the query behavior

        # Should return the existing holiday
        name = HolidayUtilityService.get_holiday_name(date(2025, 1, 1))
        self.assertEqual(name, "New Year")

        is_holiday = HolidayUtilityService.is_holiday(date(2025, 1, 1))
        self.assertTrue(is_holiday)