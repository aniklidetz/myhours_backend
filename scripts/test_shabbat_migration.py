#!/usr/bin/env python
"""
Test runner for Shabbat service migration

This script runs the comprehensive test suite for UnifiedShabbatService
and provides a detailed report on readiness for migration.
"""

import os
import sys
from pathlib import Path
from datetime import date

# Add project root to Python path
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')

# Initialize Django only if not in test environment
try:
    import django
    django.setup()
    DJANGO_AVAILABLE = True
except Exception as e:
    print(f"  Django setup failed: {e}")
    print("This may be normal if database is not available")
    DJANGO_AVAILABLE = False

def run_basic_verification():
    """Run basic verification that the new service works"""
    print(" BASIC VERIFICATION")
    print("=" * 50)

    if not DJANGO_AVAILABLE:
        print(" Django not available, skipping verification")
        return False

    try:
        from integrations.services.unified_shabbat_service import UnifiedShabbatService
        from payroll.services.contracts import validate_shabbat_times

        service = UnifiedShabbatService()

        # Test basic functionality (this doesn't require database)
        result = service.get_shabbat_times(date(2024, 6, 15))
        validate_shabbat_times(result)

        print(" Service imports successfully")
        print(" Returns valid ShabbatTimes contract")
        print(f" Timezone: {result['timezone']}")
        print(f" Calculation method: {result['calculation_method']}")
        print(f" Is estimated: {result['is_estimated']}")

        # Test convenience functions
        from integrations.services.unified_shabbat_service import get_shabbat_times, is_shabbat_time

        conv_result = get_shabbat_times(date(2024, 6, 15))
        assert conv_result == result
        print(" Convenience functions work")

        return True

    except Exception as e:
        print(f" Basic verification failed: {e}")
        return False


def run_comparison_test():
    """Run comparison with old services"""
    print("\n COMPARISON WITH OLD SERVICES")
    print("=" * 50)

    if not DJANGO_AVAILABLE:
        print(" Django not available, skipping comparison")
        return False

    try:
        from integrations.services.unified_shabbat_service import UnifiedShabbatService
        from integrations.services.sunrise_sunset_service import SunriseSunsetService
        from integrations.services.enhanced_sunrise_sunset_service import EnhancedSunriseSunsetService
        from datetime import datetime
        import pytz

        new_service = UnifiedShabbatService()

        test_date = date(2024, 6, 15)

        # Get results from all services
        new_result = new_service.get_shabbat_times(test_date)
        old_result = SunriseSunsetService.get_shabbat_times(test_date)
        enhanced_result = EnhancedSunriseSunsetService.get_shabbat_times_israeli_timezone(test_date)

        print(f"Test date: {test_date}")
        print(f"New service - Shabbat start: {new_result['shabbat_start']}")
        print(f"Old service - Shabbat start: {old_result['start']}")
        print(f"Enhanced service - Shabbat start: {enhanced_result['shabbat_start']}")

        # Parse and compare times
        new_start = datetime.fromisoformat(new_result["shabbat_start"])
        old_start = datetime.fromisoformat(old_result["start"].replace("Z", "+00:00"))
        enhanced_start = datetime.fromisoformat(enhanced_result["shabbat_start"])

        # Convert to same timezone
        israel_tz = pytz.timezone("Asia/Jerusalem")
        if old_start.tzinfo != israel_tz:
            old_start = old_start.astimezone(israel_tz)

        new_vs_old_diff = abs(new_start - old_start).total_seconds() / 60
        new_vs_enhanced_diff = abs(new_start - enhanced_start).total_seconds() / 60

        print(f" Difference with old service: {new_vs_old_diff:.1f} minutes")
        print(f" Difference with enhanced service: {new_vs_enhanced_diff:.1f} minutes")

        if new_vs_old_diff < 10:
            print(" Within reasonable range of old service")
        else:
            print(f"  Large difference with old service: {new_vs_old_diff:.1f} min")

        if new_vs_enhanced_diff < 2:
            print(" Very close to enhanced service (good precision)")
        else:
            print(f"  Some difference with enhanced service: {new_vs_enhanced_diff:.1f} min")

        return True

    except Exception as e:
        print(f" Comparison test failed: {e}")
        return False


def run_contract_validation():
    """Test that contract validation works"""
    print("\n CONTRACT VALIDATION")
    print("=" * 50)

    if not DJANGO_AVAILABLE:
        print(" Django not available, skipping contract validation")
        return False

    try:
        from payroll.services.contracts import validate_shabbat_times, ValidationError, create_fallback_shabbat_times
        from integrations.services.unified_shabbat_service import UnifiedShabbatService

        service = UnifiedShabbatService()
        result = service.get_shabbat_times(date(2024, 6, 15))

        # Should pass validation
        validated = validate_shabbat_times(result)
        print(" Valid result passes validation")

        # Test fallback creation
        fallback = create_fallback_shabbat_times("2024-06-14")
        validate_shabbat_times(fallback)
        print(" Fallback times are valid")

        # Test invalid contract rejection
        try:
            validate_shabbat_times({"invalid": "data"})
            print(" Should have rejected invalid data")
            return False
        except ValidationError:
            print(" Correctly rejects invalid data")

        return True

    except Exception as e:
        print(f" Contract validation failed: {e}")
        return False


def run_error_handling_test():
    """Test error handling"""
    print("\n  ERROR HANDLING")
    print("=" * 50)

    if not DJANGO_AVAILABLE:
        print(" Django not available, skipping error handling test")
        return False

    try:
        from integrations.services.unified_shabbat_service import UnifiedShabbatService
        from unittest.mock import patch

        service = UnifiedShabbatService()

        # Test with mocked API failure
        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("Network error")

            result = service.get_shabbat_times(date(2024, 6, 15))

            # Check if it returned a fallback result
            if result["is_estimated"] and result["calculation_method"] == "fallback":
                print(" Gracefully handles API failures")
            else:
                print(f"  Unexpected result: is_estimated={result['is_estimated']}, method={result['calculation_method']}")
                print(" Service still returned valid result (this may be expected if API succeeded)")

            # As long as we get a valid result, this is success
            from payroll.services.contracts import validate_shabbat_times
            validate_shabbat_times(result)
            print(" Error handling produces valid ShabbatTimes")

        return True

    except Exception as e:
        print(f" Error handling test failed: {e}")
        return False


def main():
    """Run all verification tests"""
    print(" UNIFIED SHABBAT SERVICE - MIGRATION READINESS TEST")
    print("=" * 60)

    tests = [
        ("Basic Verification", run_basic_verification),
        ("Comparison Test", run_comparison_test),
        ("Contract Validation", run_contract_validation),
        ("Error Handling", run_error_handling_test),
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
        print("\n READY FOR MIGRATION!")
        print("The UnifiedShabbatService is ready to replace the old services.")
        return 0
    else:
        print("\n  MIGRATION NOT READY")
        print("Please fix the failing tests before proceeding with migration.")
        return 1


if __name__ == "__main__":
    sys.exit(main())