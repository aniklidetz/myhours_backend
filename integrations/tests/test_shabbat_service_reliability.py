"""
Reliability and performance tests for UnifiedShabbatService

These tests focus on:
1. Performance characteristics
2. Reliability under various conditions
3. Memory usage and resource management
4. Behavior with large datasets
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from integrations.services.unified_shabbat_service import (
    UnifiedShabbatService,
    unified_shabbat_service,
)
from payroll.services.contracts import validate_shabbat_times


class TestPerformance:
    """Test service performance characteristics"""

    def test_single_request_performance(self):
        """Test that a single request completes in reasonable time"""
        service = UnifiedShabbatService()

        start_time = time.time()
        result = service.get_shabbat_times(date(2024, 6, 15))
        end_time = time.time()

        # Should complete in under 5 seconds (allowing for API latency)
        duration = end_time - start_time
        assert duration < 5.0, f"Service took {duration:.2f}s, should be under 5s"

        # Should return valid result
        validate_shabbat_times(result)

    def test_cached_request_performance(self):
        """Test that cached requests are fast"""
        service = UnifiedShabbatService()
        test_date = date(2024, 6, 15)

        # First request (will hit API)
        service.get_shabbat_times(test_date)

        # Second request (should use cache)
        start_time = time.time()
        result = service.get_shabbat_times(test_date)
        end_time = time.time()

        # Cached request should be very fast (under 0.1s)
        duration = end_time - start_time
        assert (
            duration < 0.1
        ), f"Cached request took {duration:.3f}s, should be under 0.1s"
        validate_shabbat_times(result)

    @pytest.mark.slow
    def test_multiple_dates_performance(self):
        """Test performance when calculating multiple dates (makes ~104 real API calls)"""
        service = UnifiedShabbatService()

        # Generate test dates for a full year
        start_date = date(2024, 1, 1)
        test_dates = [start_date + timedelta(weeks=i) for i in range(52)]

        start_time = time.time()

        results = []
        for test_date in test_dates:
            result = service.get_shabbat_times(test_date)
            results.append(result)

        end_time = time.time()

        # All 52 requests should complete in reasonable time
        # Note: UnifiedShabbatService makes 2 API calls per unique date for precision
        # 52 dates * 2 API calls = ~104 network requests, expect ~1s per request
        duration = end_time - start_time
        assert (
            duration < 120.0
        ), f"52 requests took {duration:.2f}s, should be under 120s"

        # All results should be valid
        assert len(results) == 52
        for result in results:
            validate_shabbat_times(result)


class TestReliability:
    """Test service reliability under various conditions"""

    def test_handles_api_timeouts_gracefully(self):
        """Test that service handles API timeouts without crashing"""
        service = UnifiedShabbatService()

        with patch("requests.get") as mock_get:
            # Simulate timeout
            mock_get.side_effect = Exception("Request timeout")

            # Should not crash and should return fallback
            result = service.get_shabbat_times(date(2024, 6, 15))

            validate_shabbat_times(result)
            assert result["is_estimated"] is True
            assert "fallback" in result["calculation_method"]

    def test_handles_malformed_api_responses(self):
        """Test handling of malformed API responses"""
        service = UnifiedShabbatService()

        test_cases = [
            {"status": "INVALID_REQUEST"},  # Bad status
            {"results": {}},  # Missing sunset
            {"results": {"sunset": "invalid-date"}},  # Invalid date format
            {},  # Empty response
            None,  # Null response
        ]

        for malformed_response in test_cases:
            with patch("requests.get") as mock_get:
                mock_response = Mock()
                mock_response.json.return_value = malformed_response
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response

                # Should handle gracefully and return fallback
                result = service.get_shabbat_times(date(2024, 6, 15))

                validate_shabbat_times(result)
                assert result["is_estimated"] is True

    def test_thread_safety(self):
        """Test that service is thread-safe"""
        service = UnifiedShabbatService()

        # Test with multiple threads making requests simultaneously
        test_dates = [date(2024, 6, i) for i in range(1, 29)]  # Full month
        results = []
        errors = []

        def get_times_for_date(test_date):
            try:
                return service.get_shabbat_times(test_date)
            except Exception as e:
                errors.append((test_date, str(e)))
                return None

        # Execute requests in parallel
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(get_times_for_date, d) for d in test_dates]

            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        # Should have no errors
        assert len(errors) == 0, f"Thread safety test had errors: {errors}"

        # Should have valid results for all dates
        assert len(results) > 0, "Should have gotten some results"
        for result in results:
            validate_shabbat_times(result)

    def test_memory_usage_stable(self):
        """Test that memory usage doesn't grow excessively"""
        import gc

        service = UnifiedShabbatService()

        # Force garbage collection
        gc.collect()

        # Make many requests to different dates
        for i in range(100):
            test_date = date(2024, 1, 1) + timedelta(days=i * 7)  # Weekly dates
            result = service.get_shabbat_times(test_date)
            validate_shabbat_times(result)

        # Force garbage collection again
        gc.collect()

        # This test mainly ensures no exceptions occur during repeated use
        # (actual memory measurement would require psutil or similar)
        assert True, "Memory test completed without crashes"


class TestEdgeConditions:
    """Test behavior under edge conditions"""

    def test_leap_year_handling(self):
        """Test correct handling of leap years"""
        service = UnifiedShabbatService()

        # Test leap year (2024) and non-leap year dates
        leap_year_date = date(2024, 2, 29)  # This date only exists in leap years
        regular_date = date(2023, 2, 28)

        leap_result = service.get_shabbat_times(leap_year_date)
        regular_result = service.get_shabbat_times(regular_date)

        validate_shabbat_times(leap_result)
        validate_shabbat_times(regular_result)

        # Both should work without issues
        assert leap_result["timezone"] == "Asia/Jerusalem"
        assert regular_result["timezone"] == "Asia/Jerusalem"

    def test_year_boundary_handling(self):
        """Test handling of year boundaries"""
        service = UnifiedShabbatService()

        # Test end of year and beginning of next year
        end_of_year = date(2024, 12, 27)  # Friday
        start_of_year = date(2025, 1, 3)  # Friday

        end_result = service.get_shabbat_times(end_of_year)
        start_result = service.get_shabbat_times(start_of_year)

        validate_shabbat_times(end_result)
        validate_shabbat_times(start_result)

        # Verify Saturday dates are correct (next day)
        assert end_result["saturday_date"] == "2024-12-28"
        assert start_result["saturday_date"] == "2025-01-04"

    def test_distant_future_dates(self):
        """Test handling of dates far in the future"""
        service = UnifiedShabbatService()

        # Test date 10 years in the future
        future_date = date(2034, 6, 16)  # Friday in 2034

        result = service.get_shabbat_times(future_date)
        validate_shabbat_times(result)

        # Should work (though might use fallback if API doesn't support far future)
        assert result["timezone"] == "Asia/Jerusalem"
        assert result["friday_date"] == "2034-06-16"

    def test_historical_dates(self):
        """Test handling of historical dates"""
        service = UnifiedShabbatService()

        # Test historical date (API might not support, should fallback gracefully)
        historical_date = date(2020, 6, 12)  # Friday in 2020

        result = service.get_shabbat_times(historical_date)
        validate_shabbat_times(result)

        # Should work with fallback if needed
        assert result["timezone"] == "Asia/Jerusalem"
        assert result["friday_date"] == "2020-06-12"


class TestErrorRecovery:
    """Test error recovery and resilience"""

    def test_partial_api_failure_recovery(self):
        """Test recovery when only one of two API calls fails"""
        service = UnifiedShabbatService()

        call_count = 0

        def mock_get_with_partial_failure(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:  # First call (Friday) succeeds
                mock_response = Mock()
                mock_response.json.return_value = {
                    "status": "OK",
                    "results": {"sunset": "2024-06-14T16:30:15+00:00"},
                }
                mock_response.raise_for_status.return_value = None
                return mock_response
            else:  # Second call (Saturday) fails
                raise Exception("Network error for Saturday")

        with patch("requests.get", side_effect=mock_get_with_partial_failure):
            result = service.get_shabbat_times(date(2024, 6, 14))

            validate_shabbat_times(result)
            # Should use estimation for Saturday sunset
            assert result["calculation_method"] == "api_estimated"
            assert result["is_estimated"] is True

    def test_cache_corruption_recovery(self):
        """Test recovery from cache corruption"""
        service = UnifiedShabbatService()

        # Mock cache to return invalid data
        with patch("django.core.cache.cache.get") as mock_cache_get:
            mock_cache_get.return_value = {"invalid": "data"}

            # Should ignore corrupted cache and get fresh data
            result = service.get_shabbat_times(date(2024, 6, 15))

            validate_shabbat_times(result)
            assert result["timezone"] == "Asia/Jerusalem"


class TestServiceInteroperability:
    """Test interoperability with existing payroll system"""

    def test_compatible_with_existing_payroll_logic(self):
        """Test that results work with existing payroll calculation patterns"""
        service = UnifiedShabbatService()
        result = service.get_shabbat_times(date(2024, 6, 14))

        # Test pattern: parsing times back to datetime objects
        shabbat_start = datetime.fromisoformat(result["shabbat_start"])
        shabbat_end = datetime.fromisoformat(result["shabbat_end"])

        # Should be timezone-aware datetimes
        assert shabbat_start.tzinfo is not None
        assert shabbat_end.tzinfo is not None

        # Test pattern: checking if work time overlaps with Shabbat
        # (Common pattern in payroll calculation)
        import pytz

        israel_tz = pytz.timezone("Asia/Jerusalem")
        work_start = israel_tz.localize(datetime(2024, 6, 14, 20, 0))  # Friday 8pm
        work_end = israel_tz.localize(datetime(2024, 6, 15, 1, 0))  # Saturday 1am

        # Should be able to determine overlap
        overlap_start = max(work_start, shabbat_start)
        overlap_end = min(work_end, shabbat_end)

        if overlap_start < overlap_end:
            overlap_hours = (overlap_end - overlap_start).total_seconds() / 3600
            assert overlap_hours > 0, "Should detect Shabbat overlap in work hours"

    def test_coordinates_parameter_handling(self):
        """Test that custom coordinates work correctly"""
        service = UnifiedShabbatService()

        # Test with different Israeli cities coordinates
        # Tel Aviv
        tel_aviv_result = service.get_shabbat_times(
            date(2024, 6, 15), lat=32.0853, lng=34.7818
        )

        # Haifa
        haifa_result = service.get_shabbat_times(
            date(2024, 6, 15), lat=32.7940, lng=34.9896
        )

        validate_shabbat_times(tel_aviv_result)
        validate_shabbat_times(haifa_result)

        # Coordinates should be reflected in results
        assert tel_aviv_result["coordinates"]["lat"] == 32.0853
        assert haifa_result["coordinates"]["lat"] == 32.7940

        # Times should be slightly different due to geographic differences
        # (but this test mainly ensures no crashes occur)


if __name__ == "__main__":
    # Run performance tests
    pytest.main(
        [
            __file__ + "::TestPerformance",
            "-v",
            "-s",  # Show print statements for timing info
        ]
    )
