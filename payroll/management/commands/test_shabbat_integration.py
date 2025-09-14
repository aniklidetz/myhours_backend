"""
Django management command to test Shabbat time integration with Redis

Usage:
    python manage.py test_shabbat_integration
    python manage.py test_shabbat_integration --date 2025-07-04
    python manage.py test_shabbat_integration --validate-timezone
"""

from datetime import date, datetime, timedelta

import pytz

from django.core.management.base import BaseCommand
from django.utils import timezone

from integrations.services.enhanced_sunrise_sunset_service import (
    enhanced_sunrise_sunset_service,
)
from payroll.enhanced_redis_cache import enhanced_payroll_cache
from payroll.redis_cache_service import payroll_cache


class Command(BaseCommand):
    help = "Test Shabbat time integration and timezone consistency"

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            help="Test date in YYYY-MM-DD format (default: next Friday)",
        )
        parser.add_argument(
            "--validate-timezone",
            action="store_true",
            help="Validate timezone consistency between Django and services",
        )
        parser.add_argument(
            "--test-api",
            action="store_true",
            help="Test direct API calls to sunrise-sunset.org",
        )
        parser.add_argument(
            "--test-redis",
            action="store_true",
            help="Test Redis caching of Shabbat times",
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS("🕐 Testing Shabbat Time Integration with Redis")
        )

        if options["validate_timezone"]:
            self._validate_timezones()

        # Determine test date
        if options["date"]:
            try:
                test_date = datetime.strptime(options["date"], "%Y-%m-%d").date()
            except ValueError:
                self.stdout.write(
                    self.style.ERROR("❌ Invalid date format. Use YYYY-MM-DD")
                )
                return
        else:
            # Find next Friday
            today = date.today()
            days_until_friday = (4 - today.weekday()) % 7
            if days_until_friday == 0:
                days_until_friday = 7  # Next Friday if today is Friday
            test_date = today + timedelta(days=days_until_friday)

        self.stdout.write(f"📅 Testing with date: {test_date} (should be Friday)")

        if options["test_api"]:
            self._test_api_calls(test_date)

        if options["test_redis"]:
            self._test_redis_integration(test_date)

        # Run comprehensive test
        self._run_comprehensive_test(test_date)

    def _validate_timezones(self):
        """Validate timezone consistency"""
        self.stdout.write(self.style.HTTP_INFO("🕐 Validating Timezone Consistency..."))

        # Check Django timezone
        from django.conf import settings

        django_tz = getattr(settings, "TIME_ZONE", None)
        self.stdout.write(f"   Django TIME_ZONE: {django_tz}")

        # Check service timezone
        israel_tz = enhanced_sunrise_sunset_service.ISRAEL_TZ
        self.stdout.write(f"   Service timezone: {israel_tz}")

        # Validate consistency
        is_consistent = enhanced_sunrise_sunset_service.validate_timezone_consistency()

        if is_consistent:
            self.stdout.write(self.style.SUCCESS("✅ Timezone consistency: PASSED"))
        else:
            self.stdout.write(self.style.WARNING("⚠️ Timezone mismatch detected"))

        # Show current time in both timezones
        utc_now = datetime.now(pytz.UTC)
        israel_now = utc_now.astimezone(israel_tz)
        django_now = timezone.now()

        self.stdout.write(f'   UTC time: {utc_now.strftime("%Y-%m-%d %H:%M:%S %Z")}')
        self.stdout.write(
            f'   Israel time: {israel_now.strftime("%Y-%m-%d %H:%M:%S %Z")}'
        )
        self.stdout.write(
            f'   Django time: {django_now.strftime("%Y-%m-%d %H:%M:%S %Z")}'
        )

    def _test_api_calls(self, test_date):
        """Test direct API calls"""
        self.stdout.write(self.style.HTTP_INFO("🌐 Testing Direct API Calls..."))

        # Test sunrise-sunset times
        try:
            times = enhanced_sunrise_sunset_service.get_times_with_israeli_timezone(
                test_date, use_cache=False
            )

            if times:
                self.stdout.write("✅ Sunrise-sunset API: SUCCESS")
                self.stdout.write(f'   Sunrise: {times.get("sunrise", "N/A")}')
                self.stdout.write(f'   Sunset: {times.get("sunset", "N/A")}')
                self.stdout.write(f'   Timezone: {times.get("timezone", "N/A")}')
            else:
                self.stdout.write(self.style.ERROR("❌ Sunrise-sunset API: FAILED"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ API call error: {e}"))

        # Test Shabbat calculation
        try:
            shabbat_times = (
                enhanced_sunrise_sunset_service.get_shabbat_times_israeli_timezone(
                    test_date, use_cache=False
                )
            )

            if shabbat_times:
                self.stdout.write("✅ Shabbat calculation: SUCCESS")
                self.stdout.write(
                    f'   Shabbat start: {shabbat_times.get("shabbat_start", "N/A")}'
                )
                self.stdout.write(
                    f'   Shabbat end: {shabbat_times.get("shabbat_end", "N/A")}'
                )
                self.stdout.write(
                    f'   Method: {shabbat_times.get("calculation_method", "N/A")}'
                )
                self.stdout.write(
                    f'   Estimated: {shabbat_times.get("is_estimated", "N/A")}'
                )
            else:
                self.stdout.write(self.style.ERROR("❌ Shabbat calculation: FAILED"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Shabbat calculation error: {e}"))

    def _test_redis_integration(self, test_date):
        """Test Redis integration"""
        self.stdout.write(self.style.HTTP_INFO("📋 Testing Redis Integration..."))

        # Test Redis connectivity
        cache_stats = payroll_cache.get_cache_stats()
        if cache_stats["status"] == "available":
            self.stdout.write("✅ Redis connectivity: SUCCESS")
            self.stdout.write(
                f'   Connected clients: {cache_stats.get("connected_clients", "unknown")}'
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    f'❌ Redis connectivity: {cache_stats.get("error", "FAILED")}'
                )
            )
            return

        # Test enhanced cache
        try:
            # Clear cache first
            payroll_cache.invalidate_holidays_cache(test_date.year, test_date.month)

            # Test enhanced holiday loading
            enhanced_holidays = enhanced_payroll_cache.get_holidays_with_shabbat_times(
                test_date.year, test_date.month
            )

            date_str = test_date.isoformat()
            if date_str in enhanced_holidays:
                holiday_data = enhanced_holidays[date_str]
                self.stdout.write("✅ Enhanced Redis cache: SUCCESS")
                self.stdout.write(
                    f'   Precise start: {holiday_data.get("precise_start_time", "N/A")}'
                )
                self.stdout.write(
                    f'   Precise end: {holiday_data.get("precise_end_time", "N/A")}'
                )
                self.stdout.write(
                    f'   API enhanced: {holiday_data.get("api_enhanced", "N/A")}'
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"⚠️ No Shabbat data found for {test_date}")
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Redis integration error: {e}"))

    def _run_comprehensive_test(self, test_date):
        """Run comprehensive integration test"""
        self.stdout.write(self.style.HTTP_INFO("🧪 Running Comprehensive Test..."))

        try:
            # Test the complete flow
            saturday = test_date + timedelta(days=1)

            # 1. Get enhanced holidays (should trigger API calls and Redis caching)
            self.stdout.write("1️⃣ Testing enhanced holiday loading...")
            enhanced_holidays = enhanced_payroll_cache.get_holidays_with_shabbat_times(
                test_date.year, test_date.month
            )

            # 2. Check Friday data
            friday_str = test_date.isoformat()
            if friday_str in enhanced_holidays:
                friday_data = enhanced_holidays[friday_str]
                self.stdout.write(f"✅ Friday ({friday_str}):")
                self.stdout.write(f'   Name: {friday_data.get("name", "N/A")}')
                self.stdout.write(
                    f'   Is Shabbat: {friday_data.get("is_shabbat", "N/A")}'
                )
                self.stdout.write(
                    f'   Start: {friday_data.get("precise_start_time", "N/A")}'
                )

            # 3. Check Saturday data
            saturday_str = saturday.isoformat()
            if saturday_str in enhanced_holidays:
                saturday_data = enhanced_holidays[saturday_str]
                self.stdout.write(f"✅ Saturday ({saturday_str}):")
                self.stdout.write(f'   Name: {saturday_data.get("name", "N/A")}')
                self.stdout.write(
                    f'   End: {saturday_data.get("precise_end_time", "N/A")}'
                )

            # 4. Test work overlap calculation
            self.stdout.write("2️⃣ Testing work overlap calculation...")

            # Simulate work session during Shabbat
            israel_tz = pytz.timezone("Asia/Jerusalem")
            work_start = israel_tz.localize(
                datetime.combine(
                    test_date, datetime.min.time().replace(hour=16, minute=0)
                )
            )
            work_end = israel_tz.localize(
                datetime.combine(
                    saturday, datetime.min.time().replace(hour=10, minute=0)
                )
            )

            overlap_result = enhanced_payroll_cache.is_work_during_shabbat(
                work_start, work_end, test_date
            )

            if overlap_result["is_shabbat_work"]:
                self.stdout.write("✅ Shabbat work overlap detected:")
                self.stdout.write(
                    f'   Overlap hours: {overlap_result.get("overlap_hours", "N/A")}'
                )
                self.stdout.write(
                    f'   Shabbat rate: {overlap_result.get("shabbat_rate", "N/A")}x'
                )
                self.stdout.write(
                    f'   Precise timing: {overlap_result.get("precise_timing", "N/A")}'
                )
            else:
                self.stdout.write("ℹ️ No Shabbat work overlap detected")

            # 5. Performance summary
            self.stdout.write("3️⃣ Performance Summary:")
            self.stdout.write(f"   Total dates processed: {len(enhanced_holidays)}")
            self.stdout.write(
                f'   API-enhanced entries: {sum(1 for h in enhanced_holidays.values() if h.get("api_enhanced"))}'
            )

            self.stdout.write(
                self.style.SUCCESS("🎉 Comprehensive test completed successfully!")
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Comprehensive test failed: {e}"))
            import traceback

            self.stdout.write(str(traceback.format_exc()))

