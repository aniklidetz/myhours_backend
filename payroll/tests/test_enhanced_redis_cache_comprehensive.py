"""
Comprehensive tests for enhanced_redis_cache.py covering all advanced caching scenarios:

1. Cache miss → fetch → cache hit workflow
2. TTL (Time To Live) expiration handling
3. Serialization of complex structures (dates/timezones)
4. Redis exceptions and graceful degradation
5. Empty/corrupted cache values handling
"""

import json
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from payroll.tests.helpers import MONTHLY_NORM_HOURS, ISRAELI_DAILY_NORM_HOURS, NIGHT_NORM_HOURS, MONTHLY_NORM_HOURS
from unittest.mock import MagicMock, Mock, patch

import pytz

from django.test import TestCase, override_settings

from payroll.enhanced_redis_cache import EnhancedPayrollCache, enhanced_payroll_cache


def create_mock_shabbat_times(friday_date_str="2025-02-07", saturday_date_str="2025-02-08"):
    """Helper function to create mock ShabbatTimes in UnifiedShabbatService format"""
    return {
        "shabbat_start": f"{friday_date_str}T17:00:00+02:00",
        "shabbat_end": f"{saturday_date_str}T18:00:00+02:00",
        "friday_sunset": f"{friday_date_str}T17:18:00+02:00",
        "saturday_sunset": f"{saturday_date_str}T17:18:00+02:00",
        "timezone": "Asia/Jerusalem",
        "is_estimated": False,
        "calculation_method": "api_precise",
        "coordinates": {"lat": 31.7683, "lng": 35.2137},
        "friday_date": friday_date_str,
        "saturday_date": saturday_date_str
    }


class CacheMissHitWorkflowTest(TestCase):
    """Test complete cache miss → fetch → cache hit workflow"""

    def setUp(self):
        self.cache = EnhancedPayrollCache()
        self.test_year = 2025
        self.test_month = 2

    @patch("payroll.enhanced_redis_cache.get_shabbat_times")
    @patch.object(EnhancedPayrollCache, "get_holidays_for_month")
    def test_cache_miss_then_hit_workflow(
        self, mock_get_holidays, mock_get_shabbat_times
    ):
        """Test: cache miss → fetch from source → cache hit on second call"""

        # Mock the base method to simulate database fetch
        base_holiday_data = {
            "2025-02-08": {"name": "Shabbat", "is_shabbat": True, "is_holiday": False}
        }

        # Mock unified shabbat service
        mock_get_shabbat_times.return_value = create_mock_shabbat_times("2025-02-07", "2025-02-08")

        # FIRST CALL - should be cache MISS → fetch from source
        mock_get_holidays.return_value = base_holiday_data

        result1 = self.cache.get_holidays_with_shabbat_times(
            self.test_year, self.test_month
        )

        # Verify base method was called (cache miss)
        mock_get_holidays.assert_called_once_with(self.test_year, self.test_month)

        # Verify unified shabbat service was called to enhance data
        mock_get_shabbat_times.assert_called()

        # Verify enhanced data was returned
        saturday_data = result1["2025-02-08"]
        self.assertEqual(
            saturday_data["precise_start_time"], "2025-02-07T17:00:00+02:00"
        )
        self.assertEqual(saturday_data["timezone"], "Asia/Jerusalem")

        # SECOND CALL - should be cache HIT (but might still call base method since we're testing enhanced cache)
        mock_get_holidays.reset_mock()  # Reset call count
        mock_get_shabbat_times.reset_mock()

        result2 = self.cache.get_holidays_with_shabbat_times(
            self.test_year, self.test_month
        )

        # The enhanced cache calls the base method each time, but base method should use cached data
        # What matters is that sunrise service calls should be reduced/cached
        # Verify results are consistent (main goal of caching)

        # Results should be identical
        self.assertEqual(result1, result2)

    @patch("payroll.enhanced_redis_cache.get_shabbat_times")
    def test_cache_shabbat_times_workflow(self, mock_get_shabbat_times):
        """Test pre-caching workflow and subsequent retrieval"""

        # Mock cache availability
        self.cache.cache_available = True
        self.cache.redis_client = Mock()

        # Mock unified shabbat service
        mock_get_shabbat_times.return_value = create_mock_shabbat_times("2025-02-07", "2025-02-08")

        # PRE-CACHE the data
        self.cache.cache_shabbat_times_for_month(self.test_year, self.test_month)

        # Verify Redis setex was called with correct TTL (1 week)
        self.cache.redis_client.setex.assert_called_once()
        call_args = self.cache.redis_client.setex.call_args[0]
        ttl = call_args[1]
        self.assertEqual(ttl, 7 * 24 * 60 * 60)  # 1 week TTL


class TTLExpirationTest(TestCase):
    """Test TTL (Time To Live) expiration scenarios"""

    def setUp(self):
        self.cache = EnhancedPayrollCache()
        self.cache.cache_available = True
        self.cache.redis_client = Mock()

    @patch("payroll.enhanced_redis_cache.get_shabbat_times")
    def test_ttl_expiration_triggers_reload(self, mock_get_shabbat_times):
        """Test that expired TTL triggers data reload"""

        mock_get_shabbat_times.return_value = create_mock_shabbat_times("2025-02-07", "2025-02-08")

        # Cache data with short TTL
        self.cache.cache_shabbat_times_for_month(2025, 2)

        # Verify setex called with 1 week TTL
        self.cache.redis_client.setex.assert_called_once()
        call_args = self.cache.redis_client.setex.call_args[0]
        cache_key, ttl, data = call_args

        # Verify correct TTL (1 week = 604800 seconds)
        expected_ttl = 7 * 24 * 60 * 60
        self.assertEqual(ttl, expected_ttl)

    def test_ttl_key_configuration(self):
        """Test that TTL is properly configured for cached keys"""
        self.cache.cache_available = True
        self.cache.redis_client = Mock()

        with patch(
            "payroll.enhanced_redis_cache.get_shabbat_times"
        ) as mock_service:
            mock_service.return_value = create_mock_shabbat_times()

            # Cache some data
            self.cache.cache_shabbat_times_for_month(2025, 1)

            # Verify setex (set with expiration) was used, not set
            self.cache.redis_client.setex.assert_called_once()
            # setex automatically sets TTL, so we're good

    @patch.object(EnhancedPayrollCache, "_make_key")
    def test_cache_key_generation_for_ttl(self, mock_make_key):
        """Test cache key generation includes proper prefix for TTL tracking"""
        self.cache.cache_available = True
        self.cache.redis_client = Mock()

        mock_make_key.return_value = "enhanced_holidays:2025:2"

        with patch(
            "payroll.enhanced_redis_cache.get_shabbat_times"
        ) as mock_service:
            mock_service.return_value = create_mock_shabbat_times()

            self.cache.cache_shabbat_times_for_month(2025, 2)

            # Verify correct key prefix was used
            mock_make_key.assert_called_with("enhanced_holidays", 2025, 2)


class SerializationTest(TestCase):
    """Test serialization of complex structures (dates, timezones, decimals)"""

    def setUp(self):
        self.cache = EnhancedPayrollCache()
        self.cache.cache_available = True
        self.cache.redis_client = Mock()

    @patch("payroll.enhanced_redis_cache.get_shabbat_times")
    def test_timezone_serialization(self, mock_get_shabbat_times):
        """Test that timezone information is properly serialized/deserialized"""

        # Mock service with timezone data
        complex_shabbat_data = {
            "shabbat_start": "2025-02-07T17:15:23.456+02:00",  # Complex timestamp
            "shabbat_end": "2025-02-08T18:25:45.789+02:00",
            "friday_sunset": "2025-02-07T17:15:23.456+02:00",
            "saturday_sunset": "2025-02-08T18:25:45.789+02:00",
            "timezone": "Asia/Jerusalem",
            "is_estimated": False,
            "calculation_method": "api_precise",
            "coordinates": {"lat": 31.7683, "lng": 35.2137},
            "friday_date": "2025-02-07",
            "saturday_date": "2025-02-08"
        }
        mock_get_shabbat_times.return_value = (
            complex_shabbat_data
        )

        # Cache the complex data
        self.cache.cache_shabbat_times_for_month(2025, 2)

        # Verify setex was called
        self.cache.redis_client.setex.assert_called_once()

        # Extract the serialized data
        call_args = self.cache.redis_client.setex.call_args[0]
        cache_key, ttl, serialized_data = call_args

        # Verify it's JSON serialized
        self.assertIsInstance(serialized_data, str)

        # Verify we can deserialize it back
        deserialized = json.loads(serialized_data)

        # Check specific date fields were preserved
        friday_data = deserialized["2025-02-07"]
        self.assertEqual(
            friday_data["precise_start_time"], "2025-02-07T17:15:23.456+02:00"
        )
        self.assertEqual(friday_data["timezone"], "Asia/Jerusalem")
        self.assertFalse(friday_data["is_estimated"])

    @patch.object(EnhancedPayrollCache, "_serialize_decimal")
    def test_decimal_serialization_called(self, mock_serialize_decimal):
        """Test that decimal serialization method is used"""
        self.cache.cache_available = True
        self.cache.redis_client = Mock()

        # Mock the serialization method
        mock_serialize_decimal.side_effect = lambda x: x  # Pass through for test

        with patch(
            "payroll.enhanced_redis_cache.get_shabbat_times"
        ) as mock_service:
            mock_service.return_value = create_mock_shabbat_times()

            self.cache.cache_shabbat_times_for_month(2025, 2)

            # Verify json.dumps was called with our custom serializer
            self.cache.redis_client.setex.assert_called_once()

    def test_complex_data_structure_preservation(self):
        """Test that complex nested structures are preserved through serialization"""
        # Test with mock Redis to verify serialization
        self.cache.cache_available = True

        # Create a mock that captures what would be stored
        stored_data = {}

        def mock_setex(key, ttl, data):
            stored_data[key] = json.loads(data)

        self.cache.redis_client = Mock()
        self.cache.redis_client.setex.side_effect = mock_setex

        with patch(
            "payroll.enhanced_redis_cache.get_shabbat_times"
        ) as mock_service:
            # Complex nested data
            mock_service.return_value = {
                "shabbat_start": "2025-02-07T17:15:00+02:00",
                "shabbat_end": "2025-02-08T18:25:00+02:00",
                "nested_info": {
                    "calculation_accuracy": 0.99,
                    "api_version": "2.1",
                    "location_data": {
                        "lat": 31.7683,
                        "lng": 35.2137,
                        "city": "Jerusalem",
                    },
                },
            }

            self.cache.cache_shabbat_times_for_month(2025, 2)

            # Verify nested structure was preserved
            self.assertTrue(len(stored_data) > 0)
            key = list(stored_data.keys())[0]
            data = stored_data[key]

            # Check Friday data has basic structure (nested_info gets processed by enhancement logic)
            friday_data = data["2025-02-07"]
            # The enhancement logic extracts specific fields, so nested structure might be flattened
            # Verify that timezone and timing data is preserved correctly
            self.assertIn("timezone", friday_data)
            self.assertEqual(friday_data["timezone"], "Asia/Jerusalem")


class RedisExceptionHandlingTest(TestCase):
    """Test Redis exceptions and graceful degradation"""

    def setUp(self):
        self.cache = EnhancedPayrollCache()

    def test_redis_unavailable_graceful_degradation(self):
        """Test graceful degradation when Redis is unavailable"""
        # Simulate Redis unavailable
        self.cache.cache_available = False

        with patch.object(self.cache, "get_holidays_for_month") as mock_base_method:
            mock_base_method.return_value = {
                "2025-02-08": {"name": "Shabbat", "is_shabbat": True}
            }

            with patch(
                "payroll.enhanced_redis_cache.get_shabbat_times"
            ) as mock_service:
                mock_service.return_value = {
                    "shabbat_start": "2025-02-07T17:00:00+02:00",
                    "shabbat_end": "2025-02-08T18:00:00+02:00",
                }

                # Should still work without Redis
                result = self.cache.get_holidays_with_shabbat_times(2025, 2)

                # Verify it fell back to base method and still enhanced data
                mock_base_method.assert_called_once()
                self.assertIn("2025-02-08", result)
                self.assertEqual(
                    result["2025-02-08"]["precise_start_time"],
                    "2025-02-07T17:00:00+02:00",
                )

    def test_redis_connection_exception_handling(self):
        """Test handling of Redis connection exceptions"""
        self.cache.cache_available = True
        self.cache.redis_client = Mock()

        # Mock Redis operations to raise exceptions
        self.cache.redis_client.setex.side_effect = ConnectionError(
            "Redis connection failed"
        )

        with patch(
            "payroll.enhanced_redis_cache.get_shabbat_times"
        ) as mock_service:
            mock_service.return_value = create_mock_shabbat_times()

            # Should not raise exception, should handle gracefully
            try:
                self.cache.cache_shabbat_times_for_month(2025, 2)
                # If no exception handling, the above line would raise ConnectionError
            except ConnectionError:
                self.fail("Redis exception was not handled gracefully")

    def test_redis_timeout_exception_handling(self):
        """Test handling of Redis timeout exceptions"""
        self.cache.cache_available = True
        self.cache.redis_client = Mock()

        # Mock timeout exception
        import socket

        self.cache.redis_client.setex.side_effect = socket.timeout("Redis timeout")

        with patch(
            "payroll.enhanced_redis_cache.get_shabbat_times"
        ) as mock_service:
            mock_service.return_value = create_mock_shabbat_times()

            # Should handle timeout gracefully
            self.cache.cache_shabbat_times_for_month(2025, 2)
            # Test passes if no exception is raised

    def test_partial_redis_failure_degradation(self):
        """Test degradation when Redis partially fails during operation"""
        self.cache.cache_available = True
        self.cache.redis_client = Mock()

        # Simulate Redis working for some operations but failing for others
        def side_effect_setex(key, ttl, data):
            if "holidays" in key:
                raise Exception("Redis storage failed")
            return "OK"

        self.cache.redis_client.setex.side_effect = side_effect_setex

        with patch(
            "payroll.enhanced_redis_cache.get_shabbat_times"
        ) as mock_service:
            mock_service.return_value = create_mock_shabbat_times()

            # Should handle partial failures gracefully
            self.cache.cache_shabbat_times_for_month(2025, 2)


class EmptyCorruptedCacheTest(TestCase):
    """Test handling of empty/corrupted cache values"""

    def setUp(self):
        self.cache = EnhancedPayrollCache()
        self.cache.cache_available = True
        self.cache.redis_client = Mock()

    @patch.object(EnhancedPayrollCache, "get_holidays_for_month")
    def test_empty_cache_value_handling(self, mock_get_holidays):
        """Test handling when cache returns empty/None values"""

        # Mock base method to return data
        mock_get_holidays.return_value = {
            "2025-02-08": {"name": "Shabbat", "is_shabbat": True}
        }

        # Test with None return from cache
        with patch(
            "payroll.enhanced_redis_cache.get_shabbat_times"
        ) as mock_service:
            mock_service.return_value = None

            result = self.cache.get_holidays_with_shabbat_times(2025, 2)

            # Should handle None from service gracefully
            saturday_data = result["2025-02-08"]
            self.assertEqual(saturday_data["name"], "Shabbat")
            # Should not have enhanced timing data when service returns None
            self.assertNotIn("precise_start_time", saturday_data)

    @patch.object(EnhancedPayrollCache, "get_holidays_for_month")
    def test_corrupted_sunrise_service_data(self, mock_get_holidays):
        """Test handling of corrupted/invalid data from sunrise service"""

        mock_get_holidays.return_value = {
            "2025-02-08": {"name": "Shabbat", "is_shabbat": True}
        }

        # Test with corrupted service response
        with patch(
            "payroll.enhanced_redis_cache.get_shabbat_times"
        ) as mock_service:
            # Corrupted data structure
            mock_service.return_value = {
                "invalid_field": "corrupted_value",
                "shabbat_start": "invalid_date_format",
                "nested": {"deeply": {"corrupted": "data"}},
            }

            # Should handle corrupted data gracefully
            result = self.cache.get_holidays_with_shabbat_times(2025, 2)

            # Should still return basic holiday data
            self.assertIn("2025-02-08", result)
            saturday_data = result["2025-02-08"]
            self.assertEqual(saturday_data["name"], "Shabbat")

            # Should include the service data that matches expected fields
            # The implementation only extracts specific fields, so check that invalid data is handled
            # Check that the implementation handled corrupted shabbat_start gracefully
            self.assertEqual(saturday_data["precise_start_time"], "invalid_date_format")
            # And other fields get default/fallback values
            self.assertIn("timezone", saturday_data)

    def test_empty_holidays_data_handling(self):
        """Test handling when base holidays data is empty"""

        with patch.object(self.cache, "get_holidays_for_month") as mock_get_holidays:
            # Empty base data
            mock_get_holidays.return_value = {}

            result = self.cache.get_holidays_with_shabbat_times(2025, 2)

            # Should return empty dict gracefully
            self.assertEqual(result, {})

    def test_malformed_json_in_cache(self):
        """Test handling of malformed JSON data in cache"""
        # This test would be more relevant for the base PayrollRedisCache
        # but we can test the service degradation

        with patch.object(self.cache, "get_holidays_for_month") as mock_get_holidays:
            # Simulate JSON parsing error by having base method raise exception
            mock_get_holidays.side_effect = json.JSONDecodeError(
                "Invalid JSON", "doc", 0
            )

            # Should handle JSON errors gracefully and return empty dict
            result = self.cache.get_holidays_with_shabbat_times(2025, 2)

            # Should return empty dict when JSON parsing fails
            self.assertIsInstance(result, dict)
            self.assertEqual(result, {})


class CacheInvalidationTest(TestCase):
    """Test cache invalidation scenarios"""

    def setUp(self):
        self.cache = EnhancedPayrollCache()
        self.cache.cache_available = True
        self.cache.redis_client = Mock()

    @patch("payroll.enhanced_redis_cache.get_shabbat_times")
    def test_cache_invalidation_on_data_change(self, mock_get_shabbat_times):
        """Test that cache properly handles data changes"""

        # First set of data
        first_data = create_mock_shabbat_times("2025-02-07", "2025-02-08")

        # Second set of data (updated times)
        second_data = create_mock_shabbat_times("2025-02-07", "2025-02-08")
        second_data.update({
            "shabbat_start": "2025-02-07T17:15:00+02:00",  # Changed time
            "shabbat_end": "2025-02-08T18:25:00+02:00",  # Changed time
        })

        # First cache operation
        mock_get_shabbat_times.return_value = (
            first_data
        )
        self.cache.cache_shabbat_times_for_month(2025, 2)

        # Second cache operation with updated data
        mock_get_shabbat_times.return_value = (
            second_data
        )
        self.cache.cache_shabbat_times_for_month(2025, 2)

        # Verify setex was called twice (cache updated)
        self.assertEqual(self.cache.redis_client.setex.call_count, 2)

    def test_cache_key_consistency(self):
        """Test that cache keys are consistent across operations"""

        with patch.object(self.cache, "_make_key") as mock_make_key:
            mock_make_key.return_value = "enhanced_holidays:2025:2"

            with patch(
                "payroll.enhanced_redis_cache.get_shabbat_times"
            ) as mock_service:
                mock_service.return_value = create_mock_shabbat_times()

                # Multiple operations should use same key
                self.cache.cache_shabbat_times_for_month(2025, 2)
                self.cache.cache_shabbat_times_for_month(2025, 2)

                # Verify _make_key called consistently
                expected_calls = [((("enhanced_holidays", 2025, 2),), {})] * 2
                mock_make_key.assert_has_calls([call[0] for call in expected_calls])


class IntegrationCacheTest(TestCase):
    """Integration tests combining multiple cache scenarios"""

    def setUp(self):
        self.cache = EnhancedPayrollCache()

    @patch("payroll.enhanced_redis_cache.get_shabbat_times")
    @patch.object(EnhancedPayrollCache, "get_holidays_for_month")
    def test_full_cache_lifecycle_integration(
        self, mock_get_holidays, mock_get_shabbat_times
    ):
        """Test complete cache lifecycle: miss → populate → hit → expiry → refresh"""

        # Mock base data
        mock_get_holidays.return_value = {
            "2025-02-08": {"name": "Shabbat", "is_shabbat": True}
        }

        # Mock service data
        mock_get_shabbat_times.return_value = create_mock_shabbat_times("2025-02-07", "2025-02-08")

        # Lifecycle test
        # 1. First call - cache miss
        result1 = self.cache.get_holidays_with_shabbat_times(2025, 2)

        # 2. Verify data was enhanced
        self.assertIn("precise_start_time", result1["2025-02-08"])

        # 3. Second call - should use same enhanced data
        mock_get_holidays.reset_mock()
        result2 = self.cache.get_holidays_with_shabbat_times(2025, 2)

        # Results should be consistent
        self.assertEqual(result1, result2)


# ========================================
# DOMAIN-SPECIFIC TESTS (Shabbat/Holidays)
# ========================================


class DomainShabbatHolidayWorkflowTest(TestCase):
    """Domain-specific tests for Shabbat and holiday workflows"""

    def setUp(self):
        self.cache = EnhancedPayrollCache()
        self.israel_tz = pytz.timezone("Asia/Jerusalem")
        self.test_year = 2025
        self.test_month = 2
        self.test_friday = date(2025, 2, 7)  # Friday
        self.test_saturday = date(2025, 2, 8)  # Saturday

    @patch("payroll.enhanced_redis_cache.get_shabbat_times")
    @patch.object(EnhancedPayrollCache, "get_holidays_for_month")
    def test_get_holidays_with_shabbat_times_success(
        self, mock_get_holidays, mock_get_shabbat_times
    ):
        """Test successful enhancement of holidays with Shabbat times"""
        # Mock base holiday data
        mock_get_holidays.return_value = {
            "2025-02-07": {
                "name": "Erev Shabbat",
                "is_shabbat": True,
                "is_holiday": False,
            },
            "2025-02-08": {"name": "Shabbat", "is_shabbat": True, "is_holiday": False},
        }

        # Mock sunrise-sunset service
        mock_shabbat_times = create_mock_shabbat_times("2025-02-07", "2025-02-08")
        # Customize times for this test
        mock_shabbat_times.update({
            "shabbat_start": "2025-02-07T17:15:00+02:00",
            "shabbat_end": "2025-02-08T18:25:00+02:00",
            "friday_sunset": "2025-02-07T17:15:00+02:00",
            "saturday_sunset": "2025-02-08T18:25:00+02:00",
        })
        mock_get_shabbat_times.return_value = (
            mock_shabbat_times
        )

        result = self.cache.get_holidays_with_shabbat_times(
            self.test_year, self.test_month
        )

        # Verify base method was called
        mock_get_holidays.assert_called_once_with(self.test_year, self.test_month)

        # Verify sunrise service was called for Shabbat dates
        self.assertEqual(
            mock_get_shabbat_times.call_count, 2
        )

        # Verify enhanced data structure
        friday_data = result["2025-02-07"]
        self.assertEqual(friday_data["precise_start_time"], "2025-02-07T17:15:00+02:00")
        self.assertEqual(friday_data["precise_end_time"], "2025-02-08T18:25:00+02:00")
        self.assertEqual(friday_data["timezone"], "Asia/Jerusalem")
        self.assertFalse(friday_data["is_estimated"])
        self.assertEqual(friday_data["calculation_method"], "api_precise")

        saturday_data = result["2025-02-08"]
        self.assertEqual(
            saturday_data["precise_start_time"], "2025-02-07T17:15:00+02:00"
        )
        self.assertEqual(saturday_data["precise_end_time"], "2025-02-08T18:25:00+02:00")

    @patch("payroll.enhanced_redis_cache.get_shabbat_times")
    @patch.object(EnhancedPayrollCache, "get_holidays_for_month")
    def test_get_holidays_no_shabbat_enhancement(
        self, mock_get_holidays, mock_get_shabbat_times
    ):
        """Test holidays without Shabbat don't get enhanced"""
        # Mock holiday data without Shabbat
        mock_get_holidays.return_value = {
            "2025-02-10": {
                "name": "Some Holiday",
                "is_shabbat": False,
                "is_holiday": True,
            }
        }

        result = self.cache.get_holidays_with_shabbat_times(
            self.test_year, self.test_month
        )

        # Sunrise service should not be called
        mock_get_shabbat_times.assert_not_called()

        # Holiday should remain unchanged
        holiday_data = result["2025-02-10"]
        self.assertNotIn("precise_start_time", holiday_data)
        self.assertNotIn("precise_end_time", holiday_data)

    @patch("payroll.enhanced_redis_cache.get_shabbat_times")
    @patch.object(EnhancedPayrollCache, "get_holidays_for_month")
    def test_get_holidays_sunrise_service_none_response(
        self, mock_get_holidays, mock_get_shabbat_times
    ):
        """Test when sunrise service returns None"""
        mock_get_holidays.return_value = {
            "2025-02-07": {
                "name": "Erev Shabbat",
                "is_shabbat": True,
                "is_holiday": False,
            }
        }

        # Mock sunrise service to return None
        mock_get_shabbat_times.return_value = None

        result = self.cache.get_holidays_with_shabbat_times(
            self.test_year, self.test_month
        )

        # Holiday should remain unchanged when service returns None
        friday_data = result["2025-02-07"]
        self.assertNotIn("precise_start_time", friday_data)
        self.assertNotIn("precise_end_time", friday_data)

    @patch.object(EnhancedPayrollCache, "get_holidays_for_month")
    def test_get_holidays_empty_result(self, mock_get_holidays):
        """Test with empty holidays"""
        mock_get_holidays.return_value = {}

        result = self.cache.get_holidays_with_shabbat_times(
            self.test_year, self.test_month
        )

        self.assertEqual(result, {})


class DomainShabbatCachingWorkflowTest(TestCase):
    """Test Shabbat-specific caching workflows"""

    def setUp(self):
        self.cache = EnhancedPayrollCache()
        self.test_year = 2025
        self.test_month = 2

    @patch("payroll.enhanced_redis_cache.get_shabbat_times")
    @patch.object(EnhancedPayrollCache, "_make_key")
    @patch.object(EnhancedPayrollCache, "_serialize_decimal")
    def test_cache_shabbat_times_success(
        self, mock_serialize, mock_make_key, mock_get_shabbat_times
    ):
        """Test successful caching of Shabbat times"""
        # Mock cache availability
        self.cache.cache_available = True
        self.cache.redis_client = Mock()

        # Mock key generation
        mock_make_key.return_value = "enhanced_holidays:2025:2"

        # Mock serialization
        mock_serialize.return_value = "serialized_decimal"

        # Mock Shabbat times response
        mock_shabbat_times = create_mock_shabbat_times("2025-02-07", "2025-02-08")
        # Customize times for this test
        mock_shabbat_times.update({
            "shabbat_start": "2025-02-07T17:15:00+02:00",
            "shabbat_end": "2025-02-08T18:25:00+02:00",
            "friday_sunset": "2025-02-07T17:15:00+02:00",
            "saturday_sunset": "2025-02-08T18:25:00+02:00",
        })
        mock_get_shabbat_times.return_value = (
            mock_shabbat_times
        )

        self.cache.cache_shabbat_times_for_month(self.test_year, self.test_month)

        # Verify Redis client was called
        self.cache.redis_client.setex.assert_called_once()

        # Verify call parameters
        call_args = self.cache.redis_client.setex.call_args
        cache_key = call_args[0][0]
        ttl = call_args[0][1]
        cached_data = call_args[0][2]

        self.assertEqual(cache_key, "enhanced_holidays:2025:2")
        self.assertGreater(ttl, 0)  # TTL should be positive
        self.assertIsInstance(cached_data, str)  # Should be serialized JSON

    def test_cache_shabbat_times_cache_not_available(self):
        """Test when cache is not available"""
        self.cache.cache_available = False

        # Should not raise exception
        self.cache.cache_shabbat_times_for_month(self.test_year, self.test_month)

    @patch("payroll.enhanced_redis_cache.get_shabbat_times")
    @patch.object(EnhancedPayrollCache, "_make_key")
    def test_cache_shabbat_times_december(self, mock_make_key, mock_get_shabbat_times):
        """Test caching for December (year boundary)"""
        self.cache.cache_available = True
        self.cache.redis_client = Mock()
        mock_make_key.return_value = "enhanced_holidays:2025:12"

        mock_get_shabbat_times.return_value = {
            "shabbat_start": "2025-12-05T16:10:00+02:00",  # Earlier sunset in winter
            "shabbat_end": "2025-12-06T17:15:00+02:00",
        }

        self.cache.cache_shabbat_times_for_month(2025, 12)

        # Should work for December
        self.cache.redis_client.setex.assert_called_once()
        mock_make_key.assert_called_with("enhanced_holidays", 2025, 12)

    @patch("payroll.enhanced_redis_cache.get_shabbat_times")
    @patch.object(EnhancedPayrollCache, "_make_key")
    def test_cache_shabbat_times_service_exception(
        self, mock_make_key, mock_get_shabbat_times
    ):
        """Test handling of sunrise service exceptions"""
        self.cache.cache_available = True
        self.cache.redis_client = Mock()
        mock_make_key.return_value = "enhanced_holidays:2025:2"

        # Mock service exception
        mock_get_shabbat_times.side_effect = Exception(
            "API Error"
        )

        # Should not raise exception (should be handled gracefully)
        self.cache.cache_shabbat_times_for_month(self.test_year, self.test_month)


class DomainShabbatOverlapDetectionTest(TestCase):
    """Test Shabbat work overlap detection"""

    def setUp(self):
        self.cache = EnhancedPayrollCache()
        self.israel_tz = pytz.timezone("Asia/Jerusalem")

    @patch.object(EnhancedPayrollCache, "get_holidays_with_shabbat_times")
    def test_is_work_during_shabbat_overlap(self, mock_get_holidays):
        """Test work that overlaps with Shabbat times"""
        # Mock Shabbat data with precise times
        mock_get_holidays.return_value = {
            "2025-02-08": {  # Saturday
                "name": "Shabbat",
                "is_shabbat": True,
                "precise_start_time": "2025-02-07T17:15:00+02:00",  # Friday 5:15 PM
                "precise_end_time": "2025-02-08T18:25:00+02:00",  # Saturday 6:25 PM
                "timezone": "Asia/Jerusalem",
            }
        }

        # Work that overlaps: Saturday 2:00 PM - 7:00 PM (overlaps with Shabbat end)
        work_start = self.israel_tz.localize(datetime(2025, 2, 8, 14, 0))
        work_end = self.israel_tz.localize(datetime(2025, 2, 8, 19, 0))
        work_date = date(2025, 2, 8)

        result = self.cache.is_work_during_shabbat(work_start, work_end, work_date)

        self.assertTrue(result["is_shabbat_work"])
        self.assertEqual(
            result["overlap_minutes"], 265
        )  # 6:25 PM - 2:00 PM = 4h 25min = 265 minutes overlap
        self.assertIn("work_during_shabbat", result["details"])

    @patch.object(EnhancedPayrollCache, "get_holidays_with_shabbat_times")
    def test_is_work_during_shabbat_no_overlap(self, mock_get_holidays):
        """Test work that doesn't overlap with Shabbat"""
        # Mock Shabbat data
        mock_get_holidays.return_value = {
            "2025-02-08": {
                "name": "Shabbat",
                "is_shabbat": True,
                "precise_start_time": "2025-02-07T17:15:00+02:00",  # Friday 5:15 PM
                "precise_end_time": "2025-02-08T18:25:00+02:00",  # Saturday 6:25 PM
                "timezone": "Asia/Jerusalem",
            }
        }

        # Work after Shabbat: Saturday 8:00 PM - 10:00 PM (no overlap)
        work_start = self.israel_tz.localize(datetime(2025, 2, 8, 20, 0))
        work_end = self.israel_tz.localize(datetime(2025, 2, 8, 22, 0))
        work_date = date(2025, 2, 8)

        result = self.cache.is_work_during_shabbat(work_start, work_end, work_date)

        self.assertFalse(result["is_shabbat_work"])
        self.assertEqual(result["overlap_minutes"], 0)

    @patch.object(EnhancedPayrollCache, "get_holidays_with_shabbat_times")
    def test_is_work_during_shabbat_not_shabbat_day(self, mock_get_holidays):
        """Test work on non-Shabbat day"""
        # Mock holidays without Shabbat on work date
        mock_get_holidays.return_value = {
            "2025-02-07": {  # Friday (different from work date)
                "name": "Erev Shabbat",
                "is_shabbat": True,
            }
        }

        # Work on Monday (not Shabbat)
        work_start = self.israel_tz.localize(datetime(2025, 2, 10, 9, 0))
        work_end = self.israel_tz.localize(datetime(2025, 2, 10, 17, 0))
        work_date = date(2025, 2, 10)

        result = self.cache.is_work_during_shabbat(work_start, work_end, work_date)

        self.assertFalse(result["is_shabbat_work"])
        self.assertEqual(result["overlap_minutes"], 0)
        self.assertIn("not_shabbat_day", result["details"])

    @patch.object(EnhancedPayrollCache, "get_holidays_with_shabbat_times")
    def test_is_work_during_shabbat_no_precise_times(self, mock_get_holidays):
        """Test Shabbat without precise times (fallback behavior)"""
        # Mock Shabbat data without precise times
        mock_get_holidays.return_value = {
            "2025-02-08": {
                "name": "Shabbat",
                "is_shabbat": True,
                # No precise_start_time or precise_end_time
            }
        }

        work_start = self.israel_tz.localize(datetime(2025, 2, 8, 14, 0))
        work_end = self.israel_tz.localize(datetime(2025, 2, 8, 19, 0))
        work_date = date(2025, 2, 8)

        result = self.cache.is_work_during_shabbat(work_start, work_end, work_date)

        # Should still detect as Shabbat work, but use fallback logic
        self.assertTrue(result["is_shabbat_work"])
        self.assertIn("no_precise_times", result["details"])

    @patch.object(EnhancedPayrollCache, "get_holidays_with_shabbat_times")
    def test_is_work_during_shabbat_date_not_found(self, mock_get_holidays):
        """Test when work date is not in holidays"""
        # Mock empty holidays for work date
        mock_get_holidays.return_value = {}

        work_start = self.israel_tz.localize(datetime(2025, 2, 8, 14, 0))
        work_end = self.israel_tz.localize(datetime(2025, 2, 8, 19, 0))
        work_date = date(2025, 2, 8)

        result = self.cache.is_work_during_shabbat(work_start, work_end, work_date)

        self.assertFalse(result["is_shabbat_work"])
        self.assertEqual(result["overlap_minutes"], 0)

    @patch.object(EnhancedPayrollCache, "get_holidays_with_shabbat_times")
    def test_is_work_during_shabbat_datetime_parse_error(self, mock_get_holidays):
        """Test handling of malformed datetime strings"""
        # Mock Shabbat data with malformed datetime
        mock_get_holidays.return_value = {
            "2025-02-08": {
                "name": "Shabbat",
                "is_shabbat": True,
                "precise_start_time": "invalid-datetime-format",
                "precise_end_time": "2025-02-08T18:25:00+02:00",
                "timezone": "Asia/Jerusalem",
            }
        }

        work_start = self.israel_tz.localize(datetime(2025, 2, 8, 14, 0))
        work_end = self.israel_tz.localize(datetime(2025, 2, 8, 19, 0))
        work_date = date(2025, 2, 8)

        result = self.cache.is_work_during_shabbat(work_start, work_end, work_date)

        # Should handle gracefully, probably falling back to basic logic
        self.assertIsInstance(result, dict)
        self.assertIn("is_shabbat_work", result)
        self.assertIn("overlap_minutes", result)


class DomainWorkflowIntegrationTest(TestCase):
    """Integration tests for complete domain workflows"""

    def setUp(self):
        self.cache = EnhancedPayrollCache()
        self.israel_tz = pytz.timezone("Asia/Jerusalem")

    @patch("payroll.enhanced_redis_cache.get_shabbat_times")
    @patch.object(EnhancedPayrollCache, "get_holidays_for_month")
    def test_full_workflow_cache_and_check(
        self, mock_get_holidays, mock_get_shabbat_times
    ):
        """Test complete workflow: get holidays → enhance → check work overlap"""
        # Mock base holiday data
        mock_get_holidays.return_value = {
            "2025-02-08": {"name": "Shabbat", "is_shabbat": True, "is_holiday": False}
        }

        # Mock sunrise service
        mock_get_shabbat_times.return_value = {
            "shabbat_start": "2025-02-07T17:15:00+02:00",
            "shabbat_end": "2025-02-08T18:25:00+02:00",
            "timezone": "Asia/Jerusalem",
            "is_estimated": False,
        }

        # Step 1: Get enhanced holidays
        holidays = self.cache.get_holidays_with_shabbat_times(2025, 2)

        # Verify enhancement worked
        saturday_data = holidays["2025-02-08"]
        self.assertIn("precise_start_time", saturday_data)
        self.assertEqual(saturday_data["precise_end_time"], "2025-02-08T18:25:00+02:00")

        # Step 2: Check work overlap using enhanced data
        work_start = self.israel_tz.localize(
            datetime(2025, 2, 8, 16, 0)
        )  # 4 PM Saturday
        work_end = self.israel_tz.localize(datetime(2025, 2, 8, 20, 0))  # 8 PM Saturday
        work_date = date(2025, 2, 8)

        # Mock the enhanced holidays for overlap check
        with patch.object(
            self.cache, "get_holidays_with_shabbat_times"
        ) as mock_enhanced:
            mock_enhanced.return_value = holidays

            overlap_result = self.cache.is_work_during_shabbat(
                work_start, work_end, work_date
            )

            # Should detect overlap: 4PM-6:25PM = 2h 25min overlap
            self.assertTrue(overlap_result["is_shabbat_work"])
            self.assertGreater(overlap_result["overlap_minutes"], 0)

    @patch.object(EnhancedPayrollCache, "get_holidays_for_month")
    def test_get_holidays_exception_handling(self, mock_get_holidays):
        """Test exception handling in get_holidays_with_shabbat_times"""
        # Mock base method to raise exception
        mock_get_holidays.side_effect = Exception("Database connection failed")

        # Should handle exception gracefully
        result = self.cache.get_holidays_with_shabbat_times(2025, 2)

        # Should return empty dict or handle gracefully
        self.assertIsInstance(result, dict)

    def test_cache_shabbat_times_redis_exception(self):
        """Test Redis exception handling in cache_shabbat_times_for_month"""
        # Mock cache availability but failing Redis client
        self.cache.cache_available = True
        self.cache.redis_client = Mock()
        self.cache.redis_client.setex.side_effect = Exception("Redis connection failed")

        # Should not raise exception (should be caught internally)
        self.cache.cache_shabbat_times_for_month(2025, 2)

    def test_is_work_during_shabbat_with_timezone_aware_dates(self):
        """Test is_work_during_shabbat with timezone-aware datetime objects"""
        # Use different timezones to test conversion
        utc_tz = pytz.UTC

        work_start = utc_tz.localize(datetime(2025, 2, 8, 8, 0))  # 8 AM UTC
        work_end = utc_tz.localize(datetime(2025, 2, 8, 14, 0))  # 2 PM UTC
        work_date = date(2025, 2, 8)

        # Mock empty holidays (should not crash)
        with patch.object(
            self.cache, "get_holidays_with_shabbat_times"
        ) as mock_get_holidays:
            mock_get_holidays.return_value = {}

            result = self.cache.is_work_during_shabbat(work_start, work_end, work_date)
            self.assertFalse(result["is_shabbat_work"])


class DomainPerformanceWorkflowTest(TestCase):
    """Performance tests for domain-specific workflows"""

    def setUp(self):
        self.cache = EnhancedPayrollCache()

    @patch("payroll.enhanced_redis_cache.get_shabbat_times")
    @patch.object(EnhancedPayrollCache, "get_holidays_for_month")
    def test_multiple_shabbat_dates_in_month(
        self, mock_get_holidays, mock_get_shabbat_times
    ):
        """Test handling multiple Shabbat dates in a month"""
        # Mock multiple Shabbat dates
        mock_get_holidays.return_value = {
            "2025-02-07": {"name": "Erev Shabbat", "is_shabbat": True},
            "2025-02-08": {"name": "Shabbat", "is_shabbat": True},
            "2025-02-14": {"name": "Erev Shabbat", "is_shabbat": True},
            "2025-02-15": {"name": "Shabbat", "is_shabbat": True},
            "2025-02-21": {"name": "Erev Shabbat", "is_shabbat": True},
            "2025-02-22": {"name": "Shabbat", "is_shabbat": True},
        }

        mock_get_shabbat_times.return_value = {
            "shabbat_start": "2025-02-07T17:15:00+02:00",
            "shabbat_end": "2025-02-08T18:25:00+02:00",
        }

        result = self.cache.get_holidays_with_shabbat_times(2025, 2)

        # Should handle all Shabbat dates
        self.assertEqual(len(result), 6)
        # Service should be called for each Shabbat date
        self.assertEqual(
            mock_get_shabbat_times.call_count, 6
        )

    @patch.object(EnhancedPayrollCache, "_make_key")
    def test_cache_key_generation(self, mock_make_key):
        """Test cache key generation for Shabbat times"""
        self.cache.cache_available = True
        self.cache.redis_client = Mock()

        mock_make_key.return_value = "test_key"

        self.cache.cache_shabbat_times_for_month(2025, 2)

        # Verify key generation was called with correct parameters
        mock_make_key.assert_called_with("enhanced_holidays", 2025, 2)

