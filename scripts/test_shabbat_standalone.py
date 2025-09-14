#!/usr/bin/env python
"""
Standalone test for Shabbat service - no Django required

This script tests UnifiedShabbatService logic without requiring Django setup.
Useful for quick validation when database is not available.
"""

import sys
import os
from pathlib import Path
from datetime import date, datetime

# Add project root to Python path
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))


def test_basic_imports():
    """Test that we can import the service without Django"""
    print(" TESTING BASIC IMPORTS")
    print("=" * 40)

    try:
        # Mock Django settings to avoid import errors
        import sys
        from unittest.mock import MagicMock

        # Mock Django modules
        django_mock = MagicMock()
        sys.modules['django'] = django_mock
        sys.modules['django.core'] = django_mock
        sys.modules['django.core.cache'] = django_mock
        sys.modules['django.core.cache.cache'] = django_mock
        sys.modules['django.conf'] = django_mock
        sys.modules['django.conf.settings'] = django_mock

        # Mock cache
        cache_mock = MagicMock()
        cache_mock.get.return_value = None
        django_mock.core.cache.cache = cache_mock

        from integrations.services.unified_shabbat_service import UnifiedShabbatService
        from payroll.services.contracts import ShabbatTimes, validate_shabbat_times

        print(" Successfully imported UnifiedShabbatService")
        print(" Successfully imported ShabbatTimes contract")

        return True

    except ImportError as e:
        print(f" Import failed: {e}")
        return False
    except Exception as e:
        print(f" Unexpected error: {e}")
        return False


def test_service_logic():
    """Test service logic without external dependencies"""
    print("\n TESTING SERVICE LOGIC")
    print("=" * 40)

    try:
        from integrations.services.unified_shabbat_service import UnifiedShabbatService
        from payroll.services.contracts import validate_shabbat_times

        service = UnifiedShabbatService()

        # Test Friday calculation
        monday = date(2024, 6, 10)  # Monday
        friday_for_monday = service._get_friday_for_date(monday)
        expected_friday = date(2024, 6, 14)  # Friday of that week

        if friday_for_monday == expected_friday:
            print(" Correctly finds Friday for any date")
        else:
            print(f" Friday calculation wrong: got {friday_for_monday}, expected {expected_friday}")
            return False

        # Test timezone conversion logic
        test_utc_string = "2024-06-14T16:30:15+00:00"
        try:
            converted = service._parse_and_convert_to_israel_tz(test_utc_string)
            print(" Timezone conversion works")
        except Exception as e:
            print(f" Timezone conversion failed: {e}")
            return False

        return True

    except Exception as e:
        print(f" Service logic test failed: {e}")
        return False


def test_fallback_creation():
    """Test fallback time creation"""
    print("\n  TESTING FALLBACK CREATION")
    print("=" * 40)

    try:
        from payroll.services.contracts import create_fallback_shabbat_times, validate_shabbat_times

        # Test fallback creation for different seasons
        seasons = [
            ("2024-06-14", "summer"),
            ("2024-12-13", "winter"),
            ("2024-03-15", "spring"),
            ("2024-09-13", "fall")
        ]

        for date_str, season in seasons:
            fallback = create_fallback_shabbat_times(date_str)

            # Should pass validation
            validate_shabbat_times(fallback)

            # Should be marked as estimated
            if not fallback["is_estimated"]:
                print(f" Fallback for {season} not marked as estimated")
                return False

            # Should have correct timezone
            if fallback["timezone"] != "Asia/Jerusalem":
                print(f" Wrong timezone in {season} fallback")
                return False

        print(" Fallback creation works for all seasons")
        return True

    except Exception as e:
        print(f" Fallback test failed: {e}")
        return False


def test_contract_validation():
    """Test contract validation logic"""
    print("\n TESTING CONTRACT VALIDATION")
    print("=" * 40)

    try:
        from payroll.services.contracts import validate_shabbat_times, ValidationError

        # Test valid contract
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

        validate_shabbat_times(valid_contract)
        print(" Valid contract passes validation")

        # Test invalid contract
        invalid_contract = {"invalid": "data"}

        try:
            validate_shabbat_times(invalid_contract)
            print(" Should have rejected invalid contract")
            return False
        except ValidationError:
            print(" Correctly rejects invalid contracts")

        return True

    except Exception as e:
        print(f" Contract validation test failed: {e}")
        return False


def test_time_calculations():
    """Test time calculation logic"""
    print("\n TESTING TIME CALCULATIONS")
    print("=" * 40)

    try:
        from payroll.services.contracts import create_fallback_shabbat_times
        from datetime import datetime, timedelta

        # Test that Shabbat start is 18 minutes before sunset
        fallback = create_fallback_shabbat_times("2024-06-14")

        friday_sunset = datetime.fromisoformat(fallback["friday_sunset"])
        shabbat_start = datetime.fromisoformat(fallback["shabbat_start"])

        start_diff = friday_sunset - shabbat_start
        expected_start_diff = timedelta(minutes=18)

        if abs(start_diff - expected_start_diff) < timedelta(minutes=1):
            print(" Shabbat starts 18 minutes before Friday sunset")
        else:
            print(f" Wrong Shabbat start timing: {start_diff}")
            return False

        # Test that Shabbat end is 42 minutes after sunset
        saturday_sunset = datetime.fromisoformat(fallback["saturday_sunset"])
        shabbat_end = datetime.fromisoformat(fallback["shabbat_end"])

        end_diff = shabbat_end - saturday_sunset
        expected_end_diff = timedelta(minutes=42)

        if abs(end_diff - expected_end_diff) < timedelta(minutes=1):
            print(" Shabbat ends 42 minutes after Saturday sunset")
        else:
            print(f" Wrong Shabbat end timing: {end_diff}")
            return False

        print(" All time calculations are correct")
        return True

    except Exception as e:
        print(f" Time calculation test failed: {e}")
        return False


def main():
    """Run all standalone tests"""
    print(" UNIFIED SHABBAT SERVICE - STANDALONE TESTS")
    print("=" * 55)
    print("(These tests don't require Django or database)")
    print()

    tests = [
        ("Import Test", test_basic_imports),
        ("Service Logic", test_service_logic),
        ("Fallback Creation", test_fallback_creation),
        ("Contract Validation", test_contract_validation),
        ("Time Calculations", test_time_calculations),
    ]

    results = {}
    for test_name, test_func in tests:
        results[test_name] = test_func()

    # Summary
    print("\n SUMMARY")
    print("=" * 30)

    passed = sum(results.values())
    total = len(results)

    for test_name, result in results.items():
        status = " PASS" if result else " FAIL"
        print(f"{test_name}: {status}")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("\n STANDALONE TESTS PASSED!")
        print("Service logic is working correctly.")
        if total < 5:
            print("Note: Full testing requires Django environment.")
        return 0
    else:
        print("\n  SOME TESTS FAILED")
        print("Please fix the failing tests.")
        return 1


if __name__ == "__main__":
    sys.exit(main())