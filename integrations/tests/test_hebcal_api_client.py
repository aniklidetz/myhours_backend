"""
Comprehensive tests for HebcalAPIClient.

This module tests the HebcalAPIClient service in isolation,
focusing on API communication, response parsing, and caching behavior.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import requests

from django.core.cache import cache
from django.test import TestCase

from integrations.services.hebcal_api_client import HebcalAPIClient


class HebcalAPIClientTest(TestCase):
    """Test suite for HebcalAPIClient"""

    def setUp(self):
        """Set up test environment"""
        cache.clear()
        # Reset rate limiting state to avoid test interference
        HebcalAPIClient._last_request_time = None

    def tearDown(self):
        """Clean up after tests"""
        cache.clear()
        # Reset rate limiting state
        HebcalAPIClient._last_request_time = None

    @patch("integrations.services.hebcal_api_client.requests.get")
    def test_fetch_holidays_success(self, mock_get):
        """Test successful API call with proper response parsing"""
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
                    "title": "Some non-holiday",
                    "date": "2025-10-05",
                    "category": "other",
                    "subcat": "minor",
                },
            ]
        }
        mock_get.return_value = mock_response

        # Test the API call
        holidays = HebcalAPIClient.fetch_holidays(2025)

        # Verify correct number of holidays (should filter out non-holiday items)
        self.assertEqual(len(holidays), 2)

        # Verify correct API call parameters
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        params = call_args[1]["params"]

        self.assertEqual(params["year"], 2025)
        self.assertEqual(params["cfg"], "json")
        self.assertEqual(params["v"], 1)
        self.assertEqual(params["ss"], "on")
        self.assertEqual(params["c"], "on")
        self.assertEqual(params["maj"], "on")
        self.assertEqual(params["min"], "on")
        self.assertEqual(params["nx"], "on")
        self.assertEqual(params["i"], "on")

        # Verify holiday data structure
        self.assertEqual(holidays[0]["title"], "Rosh Hashanah")
        self.assertEqual(holidays[0]["date"], "2025-09-16")
        self.assertEqual(holidays[1]["title"], "Yom Kippur")
        self.assertEqual(holidays[1]["date"], "2025-10-04")

    @patch("integrations.services.hebcal_api_client.requests.get")
    def test_fetch_holidays_with_month_filter(self, mock_get):
        """Test API call with month parameter"""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"items": []}
        mock_get.return_value = mock_response

        HebcalAPIClient.fetch_holidays(2025, month=9)

        # Verify month parameter is included
        call_args = mock_get.call_args
        params = call_args[1]["params"]
        self.assertEqual(params["month"], 9)

    @patch("integrations.services.hebcal_api_client.cache")
    @patch("integrations.services.hebcal_api_client.requests.get")
    def test_caching_behavior(self, mock_get, mock_cache):
        """Test caching mechanism works correctly"""
        # Mock cache miss first, then cache hit
        mock_cache.get.side_effect = [None, ["cached_holiday"]]

        # Mock API response
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

        # First call - should hit API and cache result
        holidays1 = HebcalAPIClient.fetch_holidays(2025)

        # Second call - should use cache
        holidays2 = HebcalAPIClient.fetch_holidays(2025)

        # Verify API was called only once
        mock_get.assert_called_once()

        # Verify cache was set with correct key and timeout
        mock_cache.set.assert_called()
        cache_call = mock_cache.set.call_args
        cache_key, cached_data, timeout = cache_call[0]

        self.assertTrue(cache_key.startswith("hebcal_holidays_"))
        self.assertEqual(timeout, HebcalAPIClient.CACHE_TIMEOUT)

        # Second call should return cached data
        self.assertEqual(holidays2, ["cached_holiday"])

    @patch("integrations.services.hebcal_api_client.time.sleep")
    @patch("integrations.services.hebcal_api_client.requests.get")
    def test_cache_disabled(self, mock_get, mock_sleep):
        """Test behavior when caching is disabled"""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"items": []}
        mock_get.return_value = mock_response

        # Call with cache disabled
        HebcalAPIClient.fetch_holidays(2025, use_cache=False)
        HebcalAPIClient.fetch_holidays(2025, use_cache=False)

        # Should call API twice when cache is disabled (1 attempt per call, no retries on success)
        self.assertEqual(mock_get.call_count, 2)

    @patch("integrations.services.hebcal_api_client.time.sleep")
    @patch("integrations.services.hebcal_api_client.requests.get")
    def test_http_error_handling(self, mock_get, mock_sleep):
        """Test handling of HTTP errors"""
        # Mock HTTP error with response object (4xx client error, should not retry)
        mock_response = MagicMock()
        mock_response.status_code = 404
        error = requests.HTTPError("404 Not Found")
        error.response = mock_response
        mock_get.side_effect = error

        # Should return empty list on client error (4xx) without retrying
        holidays = HebcalAPIClient.fetch_holidays(2025)
        self.assertEqual(holidays, [])
        # Should only try once for 4xx errors (no retries)
        self.assertEqual(mock_get.call_count, 1)

    @patch("integrations.services.hebcal_api_client.time.sleep")
    @patch("integrations.services.hebcal_api_client.requests.get")
    def test_network_error_handling(self, mock_get, mock_sleep):
        """Test handling of network errors with retry logic"""
        # Mock network error
        mock_get.side_effect = requests.RequestException("Network error")

        # Should return empty list after all retries exhausted
        holidays = HebcalAPIClient.fetch_holidays(2025)
        self.assertEqual(holidays, [])
        # Should retry MAX_RETRIES times
        self.assertEqual(mock_get.call_count, HebcalAPIClient.MAX_RETRIES)

    @patch("integrations.services.hebcal_api_client.time.sleep")
    @patch("integrations.services.hebcal_api_client.requests.get")
    def test_invalid_json_handling(self, mock_get, mock_sleep):
        """Test handling of invalid JSON response with retry logic"""
        # Mock response with invalid JSON
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response

        # Should return empty list after retries
        holidays = HebcalAPIClient.fetch_holidays(2025)
        self.assertEqual(holidays, [])
        # Should retry MAX_RETRIES times for JSON parsing errors
        self.assertEqual(mock_get.call_count, HebcalAPIClient.MAX_RETRIES)

    def test_default_year_parameter(self):
        """Test that current year is used when no year specified"""
        with patch("integrations.services.hebcal_api_client.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {"items": []}
            mock_get.return_value = mock_response

            # Call without year parameter
            HebcalAPIClient.fetch_holidays()

            # Should use current year
            call_args = mock_get.call_args
            params = call_args[1]["params"]
            current_year = date.today().year
            self.assertEqual(params["year"], current_year)

    def test_parse_holiday_items_filtering(self):
        """Test _parse_holiday_items method filters correctly"""
        raw_data = {
            "items": [
                {
                    "title": "Valid Holiday",
                    "date": "2025-01-01",
                    "category": "holiday",
                    "subcat": "major",
                },
                {
                    "title": "Wrong Category",
                    "date": "2025-01-02",
                    "category": "other",
                    "subcat": "major",
                },
                {
                    "title": "Wrong Year",
                    "date": "2024-01-03",
                    "category": "holiday",
                    "subcat": "major",
                },
                {
                    "title": "Valid Holiday 2",
                    "date": "2025-01-04",
                    "category": "holiday",
                    "subcat": "minor",
                },
            ]
        }

        filtered_items = HebcalAPIClient._parse_holiday_items(raw_data, 2025)

        # Should only include holiday category items from 2025
        self.assertEqual(len(filtered_items), 2)
        self.assertEqual(filtered_items[0]["title"], "Valid Holiday")
        self.assertEqual(filtered_items[1]["title"], "Valid Holiday 2")

    def test_build_request_params(self):
        """Test _build_request_params method"""
        # Test without month
        params = HebcalAPIClient._build_request_params(2025)
        expected_params = {
            "v": 1,
            "cfg": "json",
            "year": 2025,
            "ss": "on",
            "c": "on",
            "maj": "on",
            "min": "on",
            "nx": "on",
            "i": "on",
        }
        self.assertEqual(params, expected_params)

        # Test with month
        params_with_month = HebcalAPIClient._build_request_params(2025, 9)
        expected_params["month"] = 9
        self.assertEqual(params_with_month, expected_params)

    def test_cache_key_generation(self):
        """Test cache key generation for different parameters"""
        with patch("integrations.services.hebcal_api_client.cache") as mock_cache:
            with patch(
                "integrations.services.hebcal_api_client.requests.get"
            ) as mock_get:
                mock_cache.get.return_value = None
                mock_response = MagicMock()
                mock_response.raise_for_status.return_value = None
                mock_response.json.return_value = {"items": []}
                mock_get.return_value = mock_response

                # Test year-only cache key
                HebcalAPIClient.fetch_holidays(2025)
                cache_key = mock_cache.set.call_args[0][0]
                self.assertEqual(cache_key, "hebcal_holidays_2025")

                # Reset mock
                mock_cache.reset_mock()

                # Test year + month cache key
                HebcalAPIClient.fetch_holidays(2025, month=9)
                cache_key = mock_cache.set.call_args[0][0]
                self.assertEqual(cache_key, "hebcal_holidays_2025_9")

    @patch("integrations.services.hebcal_api_client.time.sleep")
    @patch("integrations.services.hebcal_api_client.time.time")
    @patch("integrations.services.hebcal_api_client.requests.get")
    def test_rate_limiting_enforced(self, mock_get, mock_time, mock_sleep):
        """Test that rate limiting is enforced between requests"""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"items": []}
        mock_get.return_value = mock_response

        # Simulate time passing
        mock_time.side_effect = [
            0,
            0.5,
            0.5,
            2.0,
        ]  # Second request too soon, should trigger sleep

        # Make two requests
        HebcalAPIClient.fetch_holidays(2025, use_cache=False)
        HebcalAPIClient.fetch_holidays(2026, use_cache=False)

        # Verify sleep was called to enforce rate limiting
        # Should sleep for MIN_REQUEST_INTERVAL - 0.5 = 0.5 seconds
        self.assertTrue(mock_sleep.called)
        sleep_call = mock_sleep.call_args[0][0]
        self.assertAlmostEqual(sleep_call, 0.5, places=1)

    @patch("integrations.services.hebcal_api_client.time.sleep")
    @patch("integrations.services.hebcal_api_client.requests.get")
    def test_retry_with_429_rate_limit_error(self, mock_get, mock_sleep):
        """Test retry behavior when API returns 429 Too Many Requests"""
        # Mock 429 error with response object
        mock_response = MagicMock()
        mock_response.status_code = 429
        error = requests.HTTPError("429 Too Many Requests")
        error.response = mock_response
        mock_get.side_effect = error

        # Should retry on 429 errors
        holidays = HebcalAPIClient.fetch_holidays(2025)
        self.assertEqual(holidays, [])
        # Should retry MAX_RETRIES times for 429 errors
        self.assertEqual(mock_get.call_count, HebcalAPIClient.MAX_RETRIES)

    @patch("integrations.services.hebcal_api_client.time.sleep")
    @patch("integrations.services.hebcal_api_client.requests.get")
    def test_retry_with_timeout_error(self, mock_get, mock_sleep):
        """Test retry behavior on timeout errors"""
        # Mock timeout error
        mock_get.side_effect = requests.exceptions.Timeout("Request timeout")

        # Should retry on timeout
        holidays = HebcalAPIClient.fetch_holidays(2025)
        self.assertEqual(holidays, [])
        # Should retry MAX_RETRIES times
        self.assertEqual(mock_get.call_count, HebcalAPIClient.MAX_RETRIES)
        # Sleep is called for:
        # - Rate limiting: (MAX_RETRIES - 1) times (not called on first attempt, _last_request_time is None)
        # - Exponential backoff: (MAX_RETRIES - 1) times (not called after last attempt)
        # Total: (MAX_RETRIES - 1) + (MAX_RETRIES - 1) = 2 * (MAX_RETRIES - 1)
        expected_sleep_calls = 2 * (HebcalAPIClient.MAX_RETRIES - 1)
        self.assertEqual(mock_sleep.call_count, expected_sleep_calls)

    @patch("integrations.services.hebcal_api_client.time.sleep")
    @patch("integrations.services.hebcal_api_client.requests.get")
    def test_exponential_backoff_timing(self, mock_get, mock_sleep):
        """Test that exponential backoff timing is correct"""
        # Mock network error to trigger retries
        mock_get.side_effect = requests.RequestException("Network error")

        HebcalAPIClient.fetch_holidays(2025)

        # Verify exponential backoff: 2^0=1s, 2^1=2s (no sleep after last attempt)
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        # Filter out rate limiting sleeps (look for backoff sleeps which are powers of 2)
        backoff_sleeps = [s for s in sleep_calls if s in [1, 2, 4]]
        self.assertEqual(len(backoff_sleeps), HebcalAPIClient.MAX_RETRIES - 1)
        self.assertEqual(backoff_sleeps[0], 1)  # 2^0 = 1
        self.assertEqual(backoff_sleeps[1], 2)  # 2^1 = 2
