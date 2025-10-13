"""
Comprehensive tests for UnifiedShabbatService

Tests focus on:
1. Contract compliance - new service always returns valid ShabbatTimes
2. Correctness - results follow Jewish law (18min before/42min after sunset)
3. Reasonableness - times are within expected ranges for Israel
4. Comparison with old services - not for exact match but for reasonableness
5. Edge cases - API failures, invalid dates, etc.
"""

from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
import pytz

from integrations.services.unified_shabbat_service import (
    UnifiedShabbatService,
    get_shabbat_times,
    is_shabbat_time,
    unified_shabbat_service,
)

# Removed imports of old deprecated services - now using UnifiedShabbatService only
from payroll.services.contracts import (
    ShabbatTimes,
    ValidationError,
    validate_shabbat_times,
)


class TestUnifiedShabbatServiceContract:
    """Test that UnifiedShabbatService always returns valid ShabbatTimes contracts"""

    def test_return_type_is_shabbat_times(self):
        """Test that service always returns ShabbatTimes typed dict"""
        service = UnifiedShabbatService()
        result = service.get_shabbat_times(date(2024, 6, 15))  # Summer Friday

        # Should pass validation without errors
        validated = validate_shabbat_times(result)
        assert validated is not None

        # Check all required fields are present
        assert "shabbat_start" in result
        assert "shabbat_end" in result
        assert "friday_sunset" in result
        assert "saturday_sunset" in result
        assert "timezone" in result
        assert "is_estimated" in result
        assert "calculation_method" in result
        assert "coordinates" in result

    def test_timezone_always_israeli(self):
        """Test that timezone is always set to Asia/Jerusalem"""
        service = UnifiedShabbatService()

        # Test different seasons
        test_dates = [
            date(2024, 6, 15),  # Summer
            date(2024, 12, 15),  # Winter
            date(2024, 3, 15),  # Spring
            date(2024, 9, 15),  # Fall
        ]

        for test_date in test_dates:
            result = service.get_shabbat_times(test_date)
            assert (
                result["timezone"] == "Asia/Jerusalem"
            ), f"Wrong timezone for {test_date}"

    def test_times_are_iso_format(self):
        """Test that all datetime fields are in valid ISO format"""
        service = UnifiedShabbatService()
        result = service.get_shabbat_times(date(2024, 6, 15))

        # Test that times can be parsed as ISO datetimes
        time_fields = [
            "shabbat_start",
            "shabbat_end",
            "friday_sunset",
            "saturday_sunset",
        ]
        for field in time_fields:
            time_str = result[field]
            try:
                parsed_time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                assert (
                    parsed_time.tzinfo is not None
                ), f"{field} should be timezone-aware"
            except ValueError:
                pytest.fail(f"{field} '{time_str}' is not valid ISO format")


class TestShabbatCalculationCorrectness:
    """Test that Shabbat times follow Jewish law correctly"""

    def test_shabbat_start_is_18_minutes_before_sunset(self):
        """Test that Shabbat starts exactly 18 minutes before Friday sunset"""
        service = UnifiedShabbatService()
        result = service.get_shabbat_times(date(2024, 6, 15))

        friday_sunset = datetime.fromisoformat(result["friday_sunset"])
        shabbat_start = datetime.fromisoformat(result["shabbat_start"])

        # Calculate difference
        diff = friday_sunset - shabbat_start
        expected_diff = timedelta(minutes=18)

        # Allow 1 minute tolerance for rounding
        assert abs(diff - expected_diff) < timedelta(
            minutes=1
        ), f"Shabbat should start 18min before sunset, got {diff}"

    def test_shabbat_end_is_42_minutes_after_sunset(self):
        """Test that Shabbat ends exactly 42 minutes after Saturday sunset"""
        service = UnifiedShabbatService()
        result = service.get_shabbat_times(date(2024, 6, 15))

        saturday_sunset = datetime.fromisoformat(result["saturday_sunset"])
        shabbat_end = datetime.fromisoformat(result["shabbat_end"])

        # Calculate difference
        diff = shabbat_end - saturday_sunset
        expected_diff = timedelta(minutes=42)

        # Allow 1 minute tolerance for rounding
        assert abs(diff - expected_diff) < timedelta(
            minutes=1
        ), f"Shabbat should end 42min after sunset, got {diff}"

    def test_shabbat_duration_is_approximately_25_hours(self):
        """Test that Shabbat duration is approximately 25 hours (24h + buffers)"""
        service = UnifiedShabbatService()
        result = service.get_shabbat_times(date(2024, 6, 15))

        shabbat_start = datetime.fromisoformat(result["shabbat_start"])
        shabbat_end = datetime.fromisoformat(result["shabbat_end"])

        duration = shabbat_end - shabbat_start

        # Should be around 25 hours (24h + 18min + 42min = 25h exactly)
        # Allow some tolerance for sunset time variations
        assert (
            timedelta(hours=24, minutes=30)
            <= duration
            <= timedelta(hours=25, minutes=30)
        ), f"Shabbat duration should be ~25 hours, got {duration}"

    def test_times_are_reasonable_for_israel(self):
        """Test that sunset times are reasonable for Israeli geography"""
        service = UnifiedShabbatService()

        # Test summer (long days)
        summer_result = service.get_shabbat_times(date(2024, 6, 21))  # Summer solstice
        summer_sunset = datetime.fromisoformat(summer_result["friday_sunset"])

        # Summer sunset in Israel should be between 7:00-8:00 PM
        assert (
            19 <= summer_sunset.hour <= 20
        ), f"Summer sunset hour {summer_sunset.hour} seems unreasonable for Israel"

        # Test winter (short days)
        winter_result = service.get_shabbat_times(date(2024, 12, 21))  # Winter solstice
        winter_sunset = datetime.fromisoformat(winter_result["friday_sunset"])

        # Winter sunset in Israel should be between 4:30-5:30 PM
        assert (
            16 <= winter_sunset.hour <= 17
        ), f"Winter sunset hour {winter_sunset.hour} seems unreasonable for Israel"


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_non_friday_dates_converted_to_friday(self):
        """Test that any input date gets converted to appropriate Friday"""
        service = UnifiedShabbatService()

        # Test specific date conversions
        test_cases = [
            (date(2024, 6, 10), "2024-06-14"),  # Monday -> Friday same week
            (date(2024, 6, 11), "2024-06-14"),  # Tuesday -> Friday same week
            (date(2024, 6, 12), "2024-06-14"),  # Wednesday -> Friday same week
            (date(2024, 6, 13), "2024-06-14"),  # Thursday -> Friday same week
            (date(2024, 6, 14), "2024-06-14"),  # Friday -> same Friday
            (date(2024, 6, 15), "2024-06-14"),  # Saturday -> Friday same week
            (date(2024, 6, 16), "2024-06-14"),  # Sunday -> Friday same week
        ]

        for test_date, expected_friday in test_cases:
            result = service.get_shabbat_times(test_date)
            friday_date = result["friday_date"]

            assert (
                friday_date == expected_friday
            ), f"Date {test_date} ({test_date.strftime('%A')}) should map to Friday {expected_friday}, got {friday_date}"

    def test_fallback_when_api_fails(self):
        """Test that service returns fallback times when API fails"""
        service = UnifiedShabbatService()

        with patch("requests.get") as mock_get:
            # Simulate API failure
            mock_get.side_effect = Exception("Network error")

            result = service.get_shabbat_times(date(2024, 6, 15))

            # Should still return valid ShabbatTimes
            validate_shabbat_times(result)

            # Should be marked as estimated/fallback
            assert result["is_estimated"] is True
            assert "fallback" in result["calculation_method"]

    def test_fallback_times_are_seasonal(self):
        """Test that fallback times vary by season appropriately"""
        service = UnifiedShabbatService()

        with patch("requests.get") as mock_get:
            mock_get.side_effect = Exception("API unavailable")

            summer_result = service.get_shabbat_times(date(2024, 7, 5))  # July
            winter_result = service.get_shabbat_times(date(2024, 1, 5))  # January

            summer_sunset = datetime.fromisoformat(summer_result["friday_sunset"])
            winter_sunset = datetime.fromisoformat(winter_result["friday_sunset"])

            # Summer sunset should be later than winter
            assert (
                summer_sunset.hour > winter_sunset.hour
            ), "Summer fallback sunset should be later than winter"


class TestConvenienceFunctions:
    """Test convenience functions and helper methods"""

    def test_global_function_get_shabbat_times(self):
        """Test that global convenience function works"""
        result = get_shabbat_times(date(2024, 6, 15))

        # Should return valid ShabbatTimes
        validate_shabbat_times(result)
        assert result["timezone"] == "Asia/Jerusalem"

    def test_is_shabbat_time_function(self):
        """Test is_shabbat_time convenience function"""
        # Get Shabbat times for a known Friday
        shabbat_times = get_shabbat_times(date(2024, 6, 14))  # Friday

        # Parse times
        shabbat_start = datetime.fromisoformat(shabbat_times["shabbat_start"])
        shabbat_end = datetime.fromisoformat(shabbat_times["shabbat_end"])

        # Test time during Shabbat
        during_shabbat = shabbat_start + timedelta(hours=12)
        assert is_shabbat_time(during_shabbat) is True

        # Test time before Shabbat
        before_shabbat = shabbat_start - timedelta(hours=1)
        assert is_shabbat_time(before_shabbat) is False

        # Test time after Shabbat
        after_shabbat = shabbat_end + timedelta(hours=1)
        assert is_shabbat_time(after_shabbat) is False

    def test_service_stats_tracking(self):
        """Test that service tracks usage statistics"""
        service = UnifiedShabbatService()

        # Get initial stats
        initial_stats = service.get_service_stats()
        initial_api_calls = initial_stats["api_calls_made"]

        # Make a service call
        service.get_shabbat_times(date(2024, 6, 15))

        # Check stats updated
        final_stats = service.get_service_stats()
        assert final_stats["api_calls_made"] >= initial_api_calls
        assert "service_version" in final_stats


class TestCaching:
    """Test caching behavior"""

    def test_caching_reduces_api_calls(self):
        """Test that caching reduces API calls for same request"""
        service = UnifiedShabbatService()
        test_date = date(2024, 6, 15)

        # Clear any existing cache
        from django.core.cache import cache

        cache.clear()

        # Get initial API call count
        initial_stats = service.get_service_stats()
        initial_api_calls = initial_stats["api_calls_made"]

        # Make first call (should hit API)
        result1 = service.get_shabbat_times(test_date, use_cache=True)

        # Make second call (should use cache)
        result2 = service.get_shabbat_times(test_date, use_cache=True)

        # Results should be identical
        assert result1 == result2

        # Second call should use cache (check cache hit counter increased)
        final_stats = service.get_service_stats()
        assert final_stats["cache_hits"] > initial_stats.get("cache_hits", 0)

    def test_cache_disabled_option(self):
        """Test that caching can be disabled"""
        service = UnifiedShabbatService()

        # This should work even with cache disabled
        result = service.get_shabbat_times(date(2024, 6, 15), use_cache=False)
        validate_shabbat_times(result)


# Integration test
class TestIntegrationScenarios:
    """Test realistic integration scenarios"""

    def test_payroll_calculation_scenario(self):
        """Test realistic scenario from payroll calculation perspective"""
        service = UnifiedShabbatService()

        # Scenario: Employee worked Friday 8am to Saturday 2am (crosses Shabbat)
        friday_date = date(2024, 6, 14)
        shabbat_times = service.get_shabbat_times(friday_date)

        # Create work times
        israel_tz = pytz.timezone("Asia/Jerusalem")
        work_start = israel_tz.localize(datetime(2024, 6, 14, 8, 0))  # Friday 8am
        work_end = israel_tz.localize(datetime(2024, 6, 15, 2, 0))  # Saturday 2am

        shabbat_start = datetime.fromisoformat(shabbat_times["shabbat_start"])
        shabbat_end = datetime.fromisoformat(shabbat_times["shabbat_end"])

        # Verify times make sense for payroll logic
        assert work_start < shabbat_start, "Work should start before Shabbat"
        assert work_end < shabbat_end, "Work should end before Shabbat ends"
        assert shabbat_start < work_end, "Work should overlap with Shabbat start"

        # This gives payroll system clear, consistent data to work with
        assert shabbat_times["timezone"] == "Asia/Jerusalem"
        assert isinstance(shabbat_times["is_estimated"], bool)


if __name__ == "__main__":
    # Run specific test groups
    pytest.main([__file__ + "::TestUnifiedShabbatServiceContract", "-v"])
