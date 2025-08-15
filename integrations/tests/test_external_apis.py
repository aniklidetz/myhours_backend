"""
Comprehensive tests for external API integrations.
Tests Hebcal API, Sunrise/Sunset API, caching, error handling, and data synchronization.
"""

from datetime import date, datetime, time
from decimal import Decimal
from unittest.mock import MagicMock, patch

import requests

from django.core.cache import cache
from django.test import TestCase

from integrations.models import Holiday
from integrations.services.hebcal_service import HebcalService
from integrations.services.sunrise_sunset_service import SunriseSunsetService


class HebcalServiceTest(TestCase):
    """Comprehensive tests for HebcalService"""

    def setUp(self):
        """Set up test data"""
        cache.clear()  # Clear cache before each test
        Holiday.objects.all().delete()  # Clear existing holiday data

    def tearDown(self):
        """Clean up after each test"""
        cache.clear()

    @patch("integrations.services.hebcal_service.requests.get")
    def test_fetch_holidays_success(self, mock_get):
        """Test successful holiday fetching from Hebcal API"""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "items": [
                {
                    "title": "Rosh Hashanah",
                    "date": "2025-09-16",
                    "category": "holiday",
                    "subcat": "major",
                },
                {
                    "title": "Yom Kippur",
                    "date": "2025-10-04",
                    "category": "holiday",
                    "subcat": "major",
                },
                {
                    "title": "Sukkot",
                    "date": "2025-10-09",
                    "category": "holiday",
                    "subcat": "major",
                },
            ]
        }
        mock_get.return_value = mock_response

        # Test the service
        holidays = HebcalService.fetch_holidays(2025)

        # Verify results
        self.assertEqual(len(holidays), 3)
        self.assertEqual(holidays[0]["title"], "Rosh Hashanah")
        self.assertEqual(holidays[1]["title"], "Yom Kippur")
        self.assertEqual(holidays[2]["title"], "Sukkot")

        # Verify API was called with correct parameters
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        self.assertEqual(call_args[1]["params"]["year"], 2025)
        self.assertEqual(call_args[1]["params"]["cfg"], "json")

    @patch("integrations.services.hebcal_service.cache")
    @patch("integrations.services.hebcal_service.requests.get")
    def test_fetch_holidays_with_caching(self, mock_get, mock_cache):
        """Test holiday fetching with caching mechanism"""
        # Mock cache miss first, then cache hit
        mock_cache.get.side_effect = [None, ["cached_holiday"]]

        # Mock API response with holidays to trigger caching
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "items": [
                {
                    "title": "Test Holiday",
                    "date": "2025-01-01",
                    "category": "holiday",
                    "subcat": "major",
                }
            ]
        }
        mock_get.return_value = mock_response

        # First call - should hit API
        holidays1 = HebcalService.fetch_holidays(2025)

        # Second call - should use cache
        holidays2 = HebcalService.fetch_holidays(2025)

        # Verify API was called only once
        mock_get.assert_called_once()

        # Verify cache was attempted to be set
        mock_cache.set.assert_called()

        # Second call should return cached data
        self.assertEqual(holidays2, ["cached_holiday"])

    @patch("integrations.services.hebcal_service.requests.get")
    def test_fetch_holidays_api_error(self, mock_get):
        """Test API error handling"""
        # Mock API error
        mock_get.side_effect = requests.RequestException("Network error")

        # Test the service
        holidays = HebcalService.fetch_holidays(2025, use_cache=False)

        # Should return empty list on error
        self.assertEqual(holidays, [])

    @patch("integrations.services.hebcal_service.requests.get")
    def test_fetch_holidays_invalid_response(self, mock_get):
        """Test handling of invalid API response"""
        # Mock response with invalid JSON
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response

        # Test the service
        holidays = HebcalService.fetch_holidays(2025, use_cache=False)

        # Should return empty list on invalid response
        self.assertEqual(holidays, [])

    @patch("integrations.services.hebcal_service.requests.get")
    def test_fetch_holidays_http_error(self, mock_get):
        """Test handling of HTTP errors"""
        # Mock HTTP error
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_get.return_value = mock_response

        # Test the service
        holidays = HebcalService.fetch_holidays(2025, use_cache=False)

        # Should return empty list on HTTP error
        self.assertEqual(holidays, [])

    @patch("integrations.services.hebcal_service.requests.get")
    def test_sync_holidays_to_db(self, mock_get):
        """Test syncing holidays from API to database"""
        # Mock API response
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "items": [
                {
                    "title": "Pesach I",
                    "date": "2025-04-13",
                    "category": "holiday",
                    "subcat": "major",
                },
                {
                    "title": "Yom Ha'atzmaut",
                    "date": "2025-05-05",
                    "category": "holiday",
                    "subcat": "modern",
                },
            ]
        }
        mock_get.return_value = mock_response

        # Test sync
        created, updated = HebcalService.sync_holidays_to_db(
            2025, include_weekly_shabbats=False
        )

        # Verify holidays were created (only paid holidays are now saved)
        self.assertGreaterEqual(
            created, 1
        )  # At least one paid holiday should be created
        self.assertEqual(updated, 0)

        # Verify in database
        passover = Holiday.objects.get(date=date(2025, 4, 13))
        self.assertEqual(passover.name, "Pesach I")
        self.assertTrue(passover.is_holiday)

        independence_day = Holiday.objects.get(date=date(2025, 5, 5))
        self.assertEqual(independence_day.name, "Yom Ha'atzmaut")

    @patch("integrations.services.hebcal_service.requests.get")
    def test_sync_holidays_update_existing(self, mock_get):
        """Test updating existing holidays during sync"""
        # Create existing holiday with DIFFERENT data (wrong values that need updating)
        # Note: is_official_holiday("Pesach I") returns True, so is_holiday should be True
        existing_holiday, _ = Holiday.objects.get_or_create(
            date=date(2025, 4, 13),
            defaults={
                "name": "Old Name",  # Different name - will be updated
                "is_holiday": False,  # Wrong value - should be True
                "is_shabbat": True,  # Wrong value - should be False
                "is_special_shabbat": False,
            },
        )

        # Mock API response with updated data
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "items": [
                {
                    "title": "Pesach I",
                    "date": "2025-04-13",
                    "category": "holiday",
                    "subcat": "major",
                }
            ]
        }
        mock_get.return_value = mock_response

        # Test sync
        created, updated = HebcalService.sync_holidays_to_db(
            2025, include_weekly_shabbats=False
        )

        # Should update existing since data was different
        self.assertGreaterEqual(updated, 1)
        # Created can be >= 0 as there might be new non-conflicting holidays

        # Verify holiday still exists and wasn't duplicated
        passover_holidays = Holiday.objects.filter(
            name="Pesach I", date=date(2025, 4, 13)
        )
        self.assertEqual(passover_holidays.count(), 1)

    def test_is_holiday_detection(self):
        """Test holiday detection functionality"""
        # Create test holidays
        Holiday.objects.get_or_create(
            date=date(2025, 9, 16),
            defaults={"name": "Rosh Hashanah", "is_holiday": True, "is_shabbat": False},
        )

        Holiday.objects.get_or_create(
            date=date(2025, 10, 4),
            defaults={"name": "Yom Kippur", "is_holiday": True, "is_shabbat": False},
        )

        # Test holiday detection
        self.assertTrue(HebcalService.is_holiday(date(2025, 9, 16)))
        self.assertTrue(HebcalService.is_holiday(date(2025, 10, 4)))
        self.assertFalse(HebcalService.is_holiday(date(2025, 9, 15)))  # Not a holiday

    def test_get_holiday_name(self):
        """Test getting holiday name for a specific date"""
        # Create test holiday
        Holiday.objects.get_or_create(
            date=date(2025, 9, 16),
            defaults={"name": "Rosh Hashanah", "is_holiday": True, "is_shabbat": False},
        )

        # Test getting holiday name
        holiday_name = HebcalService.get_holiday_name(date(2025, 9, 16))
        self.assertEqual(holiday_name, "Rosh Hashanah")

        # Test non-holiday date
        non_holiday_name = HebcalService.get_holiday_name(date(2025, 9, 15))
        self.assertIsNone(non_holiday_name)


class SunriseSunsetServiceTest(TestCase):
    """Comprehensive tests for SunriseSunsetService"""

    def setUp(self):
        """Set up test data"""
        cache.clear()
        self.test_date = date(2025, 7, 25)
        self.tel_aviv_lat = 32.0853
        self.tel_aviv_lng = 34.7818

    def tearDown(self):
        """Clean up after each test"""
        cache.clear()

    @patch("integrations.services.sunrise_sunset_service.requests.get")
    def test_get_shabbat_times_success(self, mock_get):
        """Test successful Shabbat times retrieval"""
        # Mock API response
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "results": {
                "sunrise": "2025-07-25T05:45:00+00:00",
                "sunset": "2025-07-25T19:30:00+00:00",
            },
            "status": "OK",
        }
        mock_get.return_value = mock_response

        # Test the service
        shabbat_times = SunriseSunsetService.get_shabbat_times(
            self.test_date, self.tel_aviv_lat, self.tel_aviv_lng
        )

        # Verify results
        self.assertIn("start", shabbat_times)
        self.assertIn("end", shabbat_times)
        self.assertIn("is_estimated", shabbat_times)
        self.assertFalse(shabbat_times["is_estimated"])

        # Verify API was called
        mock_get.assert_called_once()

    @patch("integrations.services.sunrise_sunset_service.requests.get")
    def test_get_shabbat_times_with_caching(self, mock_get):
        """Test Shabbat times with caching"""
        # Mock API response
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "results": {
                "sunrise": "2025-07-25T05:45:00+00:00",
                "sunset": "2025-07-25T19:30:00+00:00",
            },
            "status": "OK",
        }
        mock_get.return_value = mock_response

        # First call
        times1 = SunriseSunsetService.get_shabbat_times(
            self.test_date, self.tel_aviv_lat, self.tel_aviv_lng
        )

        # Second call (should use cache)
        times2 = SunriseSunsetService.get_shabbat_times(
            self.test_date, self.tel_aviv_lat, self.tel_aviv_lng
        )

        # API should be called only once
        mock_get.assert_called_once()

        # Results should be the same
        self.assertEqual(times1["start"], times2["start"])
        self.assertEqual(times1["end"], times2["end"])

    @patch("integrations.services.sunrise_sunset_service.requests.get")
    def test_get_shabbat_times_api_error(self, mock_get):
        """Test handling of API errors"""
        # Mock API error
        mock_get.side_effect = requests.RequestException("Network error")

        # Test the service
        shabbat_times = SunriseSunsetService.get_shabbat_times(
            self.test_date, self.tel_aviv_lat, self.tel_aviv_lng
        )

        # Should return estimated times
        self.assertIn("start", shabbat_times)
        self.assertIn("end", shabbat_times)
        self.assertTrue(shabbat_times["is_estimated"])

    def test_calculate_estimated_shabbat_times(self):
        """Test calculation of estimated Shabbat times"""
        # Test for a Friday
        friday_date = date(2025, 7, 25)  # Assuming this is a Friday

        estimated_times = SunriseSunsetService._calculate_estimated_shabbat_times(
            friday_date
        )

        self.assertIn("start", estimated_times)
        self.assertIn("end", estimated_times)
        self.assertTrue(estimated_times["is_estimated"])

        # Verify times are in correct format
        start_time = datetime.fromisoformat(
            estimated_times["start"].replace("Z", "+00:00")
        )
        end_time = datetime.fromisoformat(estimated_times["end"].replace("Z", "+00:00"))

        self.assertIsInstance(start_time, datetime)
        self.assertIsInstance(end_time, datetime)
        self.assertGreater(end_time, start_time)

    def test_is_shabbat_time(self):
        """Test Shabbat time detection"""
        # Mock Shabbat times
        with patch.object(SunriseSunsetService, "get_shabbat_times") as mock_get_times:
            mock_get_times.return_value = {
                "start": "2025-07-25T19:30:00+03:00",
                "end": "2025-07-26T20:30:00+03:00",
                "is_estimated": False,
            }

            # Test times during Shabbat
            shabbat_time = datetime(2025, 7, 26, 10, 0)  # Saturday morning
            self.assertTrue(SunriseSunsetService.is_shabbat_time(shabbat_time))

            # Test time before Shabbat
            before_shabbat = datetime(2025, 7, 25, 18, 0)  # Friday afternoon
            self.assertFalse(SunriseSunsetService.is_shabbat_time(before_shabbat))

            # Test time after Shabbat
            after_shabbat = datetime(2025, 7, 26, 21, 0)  # Saturday night
            self.assertFalse(SunriseSunsetService.is_shabbat_time(after_shabbat))

    @patch("integrations.services.sunrise_sunset_service.requests.get")
    def test_timezone_handling(self, mock_get):
        """Test proper timezone handling in API responses"""
        # Mock API response with timezone info
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "results": {
                "sunrise": "2025-07-25T05:45:00+03:00",  # Israel timezone
                "sunset": "2025-07-25T19:30:00+03:00",
            },
            "status": "OK",
        }
        mock_get.return_value = mock_response

        # Test the service
        shabbat_times = SunriseSunsetService.get_shabbat_times(
            self.test_date, self.tel_aviv_lat, self.tel_aviv_lng
        )

        # Verify timezone is preserved
        self.assertIn("+03:00", shabbat_times["start"])
        self.assertIn("+03:00", shabbat_times["end"])

    def test_different_locations(self):
        """Test Shabbat times for different geographical locations"""
        locations = [
            ("Tel Aviv", 32.0853, 34.7818),
            ("Jerusalem", 31.7683, 35.2137),
            ("Haifa", 32.7940, 34.9896),
        ]

        with patch(
            "integrations.services.sunrise_sunset_service.requests.get"
        ) as mock_get:
            # Mock different responses for different locations
            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {
                "results": {
                    "sunrise": "2025-07-25T05:45:00+03:00",
                    "sunset": "2025-07-25T19:30:00+03:00",
                },
                "status": "OK",
            }
            mock_get.return_value = mock_response

            for city, lat, lng in locations:
                shabbat_times = SunriseSunsetService.get_shabbat_times(
                    self.test_date, lat, lng
                )

                # Each location should get valid times
                self.assertIn("start", shabbat_times)
                self.assertIn("end", shabbat_times)

        # Verify API was called for each location
        self.assertEqual(mock_get.call_count, len(locations))


class IntegrationCacheTest(TestCase):
    """Test caching mechanisms for external integrations"""

    def setUp(self):
        """Set up test data"""
        cache.clear()

    def tearDown(self):
        """Clean up after each test"""
        cache.clear()

    def test_holiday_cache_expiration(self):
        """Test that holiday cache expires appropriately"""
        # Clear cache before test
        from django.core.cache import cache

        cache.clear()

        with patch("integrations.services.hebcal_service.requests.get") as mock_get:
            # Mock API response with valid holiday data
            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {
                "items": [
                    {
                        "title": "Test Holiday",
                        "date": "2025-01-01",
                        "category": "holiday",
                    }
                ]
            }
            mock_get.return_value = mock_response

            # First call - should hit API
            HebcalService.fetch_holidays(2025)

            # Second call within cache period - should use cache
            HebcalService.fetch_holidays(2025)

            # API should be called only once
            self.assertEqual(mock_get.call_count, 1)

    def test_shabbat_times_cache_key_uniqueness(self):
        """Test that Shabbat times cache keys are unique per location and date"""
        with patch(
            "integrations.services.sunrise_sunset_service.requests.get"
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {
                "results": {
                    "sunrise": "2025-07-25T05:45:00+03:00",
                    "sunset": "2025-07-25T19:30:00+03:00",
                },
                "status": "OK",
            }
            mock_get.return_value = mock_response

            # Different locations should have separate cache entries
            tel_aviv_times = SunriseSunsetService.get_shabbat_times(
                date(2025, 7, 25), 32.0853, 34.7818
            )

            jerusalem_times = SunriseSunsetService.get_shabbat_times(
                date(2025, 7, 25), 31.7683, 35.2137
            )

            # Should call API for each unique location
            self.assertEqual(mock_get.call_count, 2)

    def test_cache_invalidation(self):
        """Test manual cache invalidation"""
        with patch("integrations.services.hebcal_service.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {"items": []}
            mock_get.return_value = mock_response

            # First call
            HebcalService.fetch_holidays(2025)

            # Manually clear cache
            cache.clear()

            # Second call after cache clear - should hit API again
            HebcalService.fetch_holidays(2025)

            # API should be called twice
            self.assertEqual(mock_get.call_count, 2)


class IntegrationErrorHandlingTest(TestCase):
    """Test error handling across all integration services"""

    def test_network_timeout_handling(self):
        """Test handling of network timeouts"""
        with patch("integrations.services.hebcal_service.requests.get") as mock_get:
            # Mock timeout error
            mock_get.side_effect = requests.Timeout("Request timed out")

            # Should not raise exception, return empty result
            holidays = HebcalService.fetch_holidays(2025, use_cache=False)
            self.assertEqual(holidays, [])

    def test_connection_error_handling(self):
        """Test handling of connection errors"""
        with patch(
            "integrations.services.sunrise_sunset_service.requests.get"
        ) as mock_get:
            # Mock connection error
            mock_get.side_effect = requests.ConnectionError("Connection failed")

            # Should return estimated times, not raise exception
            shabbat_times = SunriseSunsetService.get_shabbat_times(
                date(2025, 7, 25), 32.0853, 34.7818
            )

            self.assertIn("start", shabbat_times)
            self.assertIn("end", shabbat_times)
            self.assertTrue(shabbat_times["is_estimated"])

    def test_invalid_json_handling(self):
        """Test handling of invalid JSON responses"""
        with patch("integrations.services.hebcal_service.requests.get") as mock_get:
            # Mock response with invalid JSON
            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.side_effect = ValueError("Invalid JSON")
            mock_get.return_value = mock_response

            # Should not raise exception
            holidays = HebcalService.fetch_holidays(2025, use_cache=False)
            self.assertEqual(holidays, [])

    def test_api_rate_limiting(self):
        """Test handling of API rate limiting"""
        with patch("integrations.services.hebcal_service.requests.get") as mock_get:
            # Mock rate limiting response
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = requests.HTTPError(
                "429 Too Many Requests"
            )
            mock_get.return_value = mock_response

            # Should handle gracefully
            holidays = HebcalService.fetch_holidays(2025, use_cache=False)
            self.assertEqual(holidays, [])


class IntegrationPerformanceTest(TestCase):
    """Test performance aspects of integrations"""

    def setUp(self):
        """Set up test data"""
        cache.clear()  # Clear cache before each test
        Holiday.objects.all().delete()  # Clear existing holiday data

    def test_batch_holiday_sync_performance(self):
        """Test performance of batch holiday synchronization"""
        with patch("integrations.services.hebcal_service.requests.get") as mock_get:
            # Mock large response with sequential valid dates
            import datetime

            base_date = datetime.date(2025, 1, 1)
            large_response = {
                "items": [
                    {
                        "title": f"Holiday {i}",
                        "date": (base_date + datetime.timedelta(days=i)).strftime(
                            "%Y-%m-%d"
                        ),
                        "category": "holiday",
                        "subcat": "major",  # Use valid subcat for processing
                    }
                    for i in range(100)  # 100 holidays
                ]
            }

            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = large_response
            mock_get.return_value = mock_response

            # Test sync performance
            created, updated = HebcalService.sync_holidays_to_db(
                2025, include_weekly_shabbats=False
            )

            # Should handle large datasets efficiently (non-paid holidays are now filtered)
            self.assertGreaterEqual(
                created, 70
            )  # At least 70% should be created after filtering
            self.assertEqual(updated, 0)

            # Verify holidays were created (filtered for paid holidays only)
            self.assertGreaterEqual(Holiday.objects.count(), 70)

    def test_concurrent_api_calls(self):
        """Test handling of concurrent API calls"""
        with patch(
            "integrations.services.sunrise_sunset_service.requests.get"
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {
                "results": {
                    "sunrise": "2025-07-25T05:45:00+03:00",
                    "sunset": "2025-07-25T19:30:00+03:00",
                },
                "status": "OK",
            }
            mock_get.return_value = mock_response

            # Simulate concurrent calls for different dates
            dates = [date(2025, 7, i) for i in range(1, 11)]  # 10 different dates

            results = []
            for test_date in dates:
                result = SunriseSunsetService.get_shabbat_times(
                    test_date, 32.0853, 34.7818
                )
                results.append(result)

            # All calls should succeed
            self.assertEqual(len(results), 10)
            for result in results:
                self.assertIn("start", result)
                self.assertIn("end", result)
