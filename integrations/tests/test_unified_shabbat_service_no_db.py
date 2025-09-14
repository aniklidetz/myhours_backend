"""
Database-free tests for UnifiedShabbatService

These tests can run without PostgreSQL/MongoDB and focus on core logic validation.
Use these when database is not available but you need to test the service logic.
"""

import pytest
from datetime import date, datetime, timedelta
from unittest.mock import patch, Mock
import pytz

# Prevent Django database access
pytestmark = pytest.mark.django_db(transaction=False, databases=[])


class TestUnifiedShabbatServiceNoDb:
    """Test UnifiedShabbatService core logic without database requirements"""

    def test_service_imports_successfully(self):
        """Test that service can be imported without database"""
        from integrations.services.unified_shabbat_service import UnifiedShabbatService
        service = UnifiedShabbatService()
        assert service is not None

    def test_contract_imports_successfully(self):
        """Test that contracts can be imported and used"""
        from payroll.services.contracts import ShabbatTimes, validate_shabbat_times

        # Create a valid contract
        valid_contract = {
            "shabbat_start": "2024-06-14T17:12:00+03:00",
            "shabbat_end": "2024-06-15T20:32:00+03:00",
            "friday_sunset": "2024-06-14T17:30:00+03:00",
            "saturday_sunset": "2024-06-15T19:50:00+03:00",
            "timezone": "Asia/Jerusalem",
            "is_estimated": False,
            "calculation_method": "api_precise",
            "coordinates": {"lat": 31.7683, "lng": 35.2137}
        }

        # Should not raise exception
        validate_shabbat_times(valid_contract)

    def test_friday_calculation_logic(self):
        """Test Friday date calculation without API calls"""
        from integrations.services.unified_shabbat_service import UnifiedShabbatService

        service = UnifiedShabbatService()

        # Monday should map to Friday of same week
        monday = date(2024, 6, 10)  # Monday June 10
        friday = service._get_friday_for_date(monday)
        expected_friday = date(2024, 6, 14)  # Friday June 14

        assert friday == expected_friday

        # Friday should return itself
        friday_input = date(2024, 6, 14)  # Friday
        friday_output = service._get_friday_for_date(friday_input)
        assert friday_output == friday_input

    def test_timezone_conversion_logic(self):
        """Test timezone conversion without API calls"""
        from integrations.services.unified_shabbat_service import UnifiedShabbatService

        service = UnifiedShabbatService()

        # Test UTC to Israeli timezone conversion
        utc_time_str = "2024-06-14T16:30:15+00:00"
        israel_time = service._parse_and_convert_to_israel_tz(utc_time_str)

        # Should be timezone-aware and in Israeli timezone
        assert israel_time.tzinfo is not None
        assert israel_time.tzinfo.zone == "Asia/Jerusalem"

    def test_fallback_creation_logic(self):
        """Test fallback time creation for different seasons"""
        from payroll.services.contracts import create_fallback_shabbat_times, validate_shabbat_times

        seasons = [
            ("2024-06-14", "summer"),   # June - summer
            ("2024-12-13", "winter"),   # December - winter
            ("2024-03-15", "spring"),   # March - spring
            ("2024-09-13", "fall")      # September - fall
        ]

        for date_str, season_name in seasons:
            fallback = create_fallback_shabbat_times(date_str)

            # Should pass validation
            validate_shabbat_times(fallback)

            # Should be marked as estimated
            assert fallback["is_estimated"] is True
            assert fallback["calculation_method"] == "fallback"
            assert fallback["timezone"] == "Asia/Jerusalem"

            # Parse times to verify they're reasonable
            friday_sunset = datetime.fromisoformat(fallback["friday_sunset"])
            saturday_sunset = datetime.fromisoformat(fallback["saturday_sunset"])

            # Saturday sunset should be after Friday sunset
            assert saturday_sunset > friday_sunset

    def test_jewish_law_compliance_in_fallback(self):
        """Test that fallback times follow Jewish law (18/42 minute rules)"""
        from payroll.services.contracts import create_fallback_shabbat_times
        from datetime import timedelta

        fallback = create_fallback_shabbat_times("2024-06-14")

        # Parse times
        friday_sunset = datetime.fromisoformat(fallback["friday_sunset"])
        saturday_sunset = datetime.fromisoformat(fallback["saturday_sunset"])
        shabbat_start = datetime.fromisoformat(fallback["shabbat_start"])
        shabbat_end = datetime.fromisoformat(fallback["shabbat_end"])

        # Test 18-minute rule (Shabbat starts 18 min before Friday sunset)
        start_diff = friday_sunset - shabbat_start
        expected_start = timedelta(minutes=18)
        assert abs(start_diff - expected_start) < timedelta(minutes=1)

        # Test 42-minute rule (Shabbat ends 42 min after Saturday sunset)
        end_diff = shabbat_end - saturday_sunset
        expected_end = timedelta(minutes=42)
        assert abs(end_diff - expected_end) < timedelta(minutes=1)

    @patch('requests.get')
    def test_service_handles_api_failure_gracefully(self, mock_get):
        """Test that service handles API failures and returns fallback"""
        from integrations.services.unified_shabbat_service import UnifiedShabbatService
        from payroll.services.contracts import validate_shabbat_times

        # Mock API failure
        mock_get.side_effect = Exception("Network error")

        service = UnifiedShabbatService()
        result = service.get_shabbat_times(date(2024, 6, 15))

        # Should return valid ShabbatTimes even with API failure
        validate_shabbat_times(result)

        # Should be marked as fallback
        assert result["is_estimated"] is True

    @patch('requests.get')
    def test_service_uses_api_when_available(self, mock_get):
        """Test that service tries to use API when available"""
        from integrations.services.unified_shabbat_service import UnifiedShabbatService

        # Mock successful API response
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "OK",
            "results": {"sunset": "2024-06-14T16:30:15+00:00"}
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        service = UnifiedShabbatService()
        result = service.get_shabbat_times(date(2024, 6, 14))

        # Should have made API calls
        assert mock_get.called

        # Should return valid result
        from payroll.services.contracts import validate_shabbat_times
        validate_shabbat_times(result)

    def test_seasonal_fallback_variation(self):
        """Test that fallback times vary appropriately by season"""
        from payroll.services.contracts import create_fallback_shabbat_times

        summer_fallback = create_fallback_shabbat_times("2024-07-15")  # July
        winter_fallback = create_fallback_shabbat_times("2024-01-15")  # January

        summer_sunset = datetime.fromisoformat(summer_fallback["friday_sunset"])
        winter_sunset = datetime.fromisoformat(winter_fallback["friday_sunset"])

        # Summer sunset should be later than winter sunset
        assert summer_sunset.hour > winter_sunset.hour

        # Both should be reasonable times for Israel
        assert 16 <= winter_sunset.hour <= 18  # Winter sunset 4-6 PM
        assert 19 <= summer_sunset.hour <= 20  # Summer sunset 7-8 PM

    def test_contract_validation_rejects_invalid_data(self):
        """Test that contract validation properly rejects invalid data"""
        from payroll.services.contracts import validate_shabbat_times, ValidationError

        invalid_contracts = [
            {},  # Empty
            {"invalid": "data"},  # Wrong fields
            {  # Missing required fields
                "shabbat_start": "2024-06-14T17:12:00+03:00",
                "timezone": "Asia/Jerusalem"
            },
            {  # Wrong timezone
                "shabbat_start": "2024-06-14T17:12:00+03:00",
                "shabbat_end": "2024-06-15T20:32:00+03:00",
                "friday_sunset": "2024-06-14T17:30:00+03:00",
                "saturday_sunset": "2024-06-15T19:50:00+03:00",
                "timezone": "US/Eastern",  # Wrong timezone
                "is_estimated": False,
                "calculation_method": "api_precise",
                "coordinates": {"lat": 31.7683, "lng": 35.2137}
            }
        ]

        for invalid_contract in invalid_contracts:
            with pytest.raises(ValidationError):
                validate_shabbat_times(invalid_contract)

    def test_service_statistics_tracking(self):
        """Test that service tracks usage statistics"""
        from integrations.services.unified_shabbat_service import UnifiedShabbatService

        service = UnifiedShabbatService()
        stats = service.get_service_stats()

        # Should return dict with expected keys
        assert isinstance(stats, dict)
        assert "api_calls_made" in stats
        assert "cache_hits" in stats
        assert "service_version" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])