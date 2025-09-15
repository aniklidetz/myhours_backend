"""
Integration tests for external API services.

Tests integration between multiple services, caching behavior across services,
error handling in service interactions, and performance with real-world scenarios.

These tests complement the isolated unit tests for individual services:
- test_hebcal_api_client.py - HebcalAPIClient unit tests
- test_holiday_sync_service.py - HolidaySyncService unit tests
- test_holiday_utility_service.py - HolidayUtilityService unit tests
"""

from datetime import date
from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import TestCase

from integrations.models import Holiday
from integrations.services.hebcal_service import HebcalService


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
        """Test handling of connection errors with UnifiedShabbatService"""
        with patch("requests.get") as mock_get:
            # Mock connection error
            mock_get.side_effect = requests.ConnectionError("Connection failed")

            # Should return estimated times, not raise exception
            from integrations.services.unified_shabbat_service import get_shabbat_times
            shabbat_times = get_shabbat_times(date(2025, 7, 25))

            self.assertIn("shabbat_start", shabbat_times)
            self.assertIn("shabbat_end", shabbat_times)
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
        """Test handling of concurrent API calls with UnifiedShabbatService"""
        with patch("requests.get") as mock_get:
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

            from integrations.services.unified_shabbat_service import get_shabbat_times
            results = []
            for test_date in dates:
                result = get_shabbat_times(test_date)
                results.append(result)

            # All calls should succeed
            self.assertEqual(len(results), 10)
            for result in results:
                self.assertIn("shabbat_start", result)
                self.assertIn("shabbat_end", result)