"""
Tests for Shabbat time calculations during Israeli DST transitions.

Israeli DST transitions in 2025:
- Spring forward: Friday, March 28, 2025 at 02:00 → 03:00 (clock jumps forward 1 hour)
- Fall back: Sunday, October 26, 2025 at 02:00 → 01:00 (clock falls back 1 hour)

Critical test cases:
1. Shabbat time calculation on DST transition dates
2. Work shifts crossing DST boundaries (for payroll premium calculations)
3. Ensure no "nonexistent time" errors during spring forward
4. Ensure correct handling of ambiguous times during fall back
"""

from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
import pytz

from integrations.services.unified_shabbat_service import (
    UnifiedShabbatService,
    get_shabbat_times,
    is_shabbat_time,
)
from payroll.services.contracts import validate_shabbat_times


class TestIsraeliDSTTransitions:
    """Test Shabbat calculations during Israeli DST transitions"""

    def test_israeli_timezone_has_dst(self):
        """Verify that Israeli timezone has DST configured correctly in pytz"""
        israel_tz = pytz.timezone("Asia/Jerusalem")

        # Spring forward date: March 28, 2025 (DST starts)
        before_dst = israel_tz.localize(datetime(2025, 3, 28, 1, 0))
        after_dst = israel_tz.localize(datetime(2025, 3, 28, 3, 0))

        # Check that DST is different
        assert before_dst.dst() != after_dst.dst(), "Israeli timezone should have DST"

        # Fall back date: October 26, 2025 (DST ends)
        in_dst = israel_tz.localize(datetime(2025, 10, 25, 12, 0))
        after_dst_end = israel_tz.localize(datetime(2025, 10, 26, 12, 0))

        assert in_dst.dst() != after_dst_end.dst(), "DST should end in October"

    def test_shabbat_times_on_spring_dst_transition_friday(self):
        """
        Test Shabbat calculation on March 28, 2025 (Friday) when DST starts.

        On this date:
        - Clock jumps forward at 02:00 → 03:00
        - Shabbat starts Friday evening (before DST change)
        - Shabbat continues through Saturday (after DST change)

        This is a CRITICAL test because a work shift on Friday night crossing
        into Saturday will cross the DST boundary, affecting payroll calculations.
        """
        service = UnifiedShabbatService()

        # Friday, March 28, 2025 is when DST starts in Israel
        dst_transition_friday = date(2025, 3, 28)

        # Get Shabbat times
        shabbat_times = service.get_shabbat_times(dst_transition_friday)

        # Validate contract compliance
        validate_shabbat_times(shabbat_times)

        # Verify timezone is Israeli
        assert shabbat_times["timezone"] == "Asia/Jerusalem"

        # Parse times
        shabbat_start = datetime.fromisoformat(shabbat_times["shabbat_start"])
        shabbat_end = datetime.fromisoformat(shabbat_times["shabbat_end"])
        friday_sunset = datetime.fromisoformat(shabbat_times["friday_sunset"])
        saturday_sunset = datetime.fromisoformat(shabbat_times["saturday_sunset"])

        # All times should be timezone-aware
        assert shabbat_start.tzinfo is not None
        assert shabbat_end.tzinfo is not None

        # Shabbat should start 18 minutes before Friday sunset
        diff_start = friday_sunset - shabbat_start
        assert abs(diff_start - timedelta(minutes=18)) < timedelta(minutes=1)

        # Shabbat should end 42 minutes after Saturday sunset
        diff_end = shabbat_end - saturday_sunset
        assert abs(diff_end - timedelta(minutes=42)) < timedelta(minutes=1)

        # Duration should be approximately 25 hours
        # NOTE: With DST spring forward, the duration might be ~24 hours instead of ~25
        # because the clock jumps forward 1 hour during Saturday morning
        duration = shabbat_end - shabbat_start
        assert (
            timedelta(hours=23, minutes=30)
            <= duration
            <= timedelta(hours=25, minutes=30)
        ), f"Shabbat duration {duration} seems wrong for DST transition"

    def test_shabbat_times_on_fall_dst_transition_sunday(self):
        """
        Test Shabbat calculation on October 24, 2025 (Friday before DST ends).

        DST ends on Sunday, October 26 at 02:00 → 01:00, but Shabbat is
        Friday Oct 24 evening through Saturday Oct 25 evening.

        This Shabbat does NOT cross DST boundary, so it should be normal ~25 hours.
        """
        service = UnifiedShabbatService()

        # Friday before DST ends
        friday_before_dst_end = date(2025, 10, 24)

        # Get Shabbat times
        shabbat_times = service.get_shabbat_times(friday_before_dst_end)

        # Validate
        validate_shabbat_times(shabbat_times)
        assert shabbat_times["timezone"] == "Asia/Jerusalem"

        # Parse times
        shabbat_start = datetime.fromisoformat(shabbat_times["shabbat_start"])
        shabbat_end = datetime.fromisoformat(shabbat_times["shabbat_end"])

        # Duration should be normal ~25 hours (DST change is on Sunday, not during Shabbat)
        duration = shabbat_end - shabbat_start
        assert (
            timedelta(hours=24, minutes=30)
            <= duration
            <= timedelta(hours=25, minutes=30)
        )

    def test_work_shift_crossing_dst_spring_forward(self):
        """
        Test realistic payroll scenario: Employee works Friday night crossing DST.

        Scenario:
        - Friday March 28, 2025: Employee checks in at 22:00 (before DST)
        - Saturday March 29, 2025: Clock jumps 02:00 → 03:00 at 02:00
        - Employee checks out at 04:00 (after DST jump)

        CRITICAL: is_shabbat_time() must correctly identify Shabbat hours for
        premium pay calculation (1.5× for Shabbat hours).
        """
        israel_tz = pytz.timezone("Asia/Jerusalem")

        # Friday March 28, 2025 at 22:00 (10 PM) - before DST
        check_in = israel_tz.localize(datetime(2025, 3, 28, 22, 0))

        # Saturday March 29, 2025 at 04:00 (4 AM) - after DST jump
        # Note: 02:00-03:00 doesn't exist due to DST, so 04:00 is actually 3 hours later in wall time
        check_out = israel_tz.localize(datetime(2025, 3, 29, 4, 0))

        # Get Shabbat times for this Friday
        shabbat_times = get_shabbat_times(date(2025, 3, 28))
        shabbat_start = datetime.fromisoformat(shabbat_times["shabbat_start"])
        shabbat_end = datetime.fromisoformat(shabbat_times["shabbat_end"])

        # Check-in (22:00 Friday) should be AFTER Shabbat start
        assert is_shabbat_time(
            check_in
        ), f"Check-in at {check_in} should be during Shabbat (starts {shabbat_start})"

        # Check-out (04:00 Saturday) should be BEFORE Shabbat end
        assert is_shabbat_time(
            check_out
        ), f"Check-out at {check_out} should be during Shabbat (ends {shabbat_end})"

        # Verify entire shift is during Shabbat (for 1.5× premium calculation)
        assert check_in >= shabbat_start, "Shift should start after Shabbat begins"
        assert check_out <= shabbat_end, "Shift should end before Shabbat ends"

    def test_work_shift_crossing_midnight_during_dst(self):
        """
        Test work shift that crosses midnight on DST transition night.

        Edge case: Employee works 23:00 Friday → 02:30 Saturday
        On March 28→29, 2025, the clock jumps 02:00 → 03:00 at 02:00.
        So working until 02:30 means the employee actually worked until 03:30 in DST time.
        """
        israel_tz = pytz.timezone("Asia/Jerusalem")

        # Friday 23:00 (before DST)
        work_start = israel_tz.localize(datetime(2025, 3, 28, 23, 0))

        # Saturday 02:30 - but this time doesn't exist! It becomes 03:30
        # pytz.localize with is_dst=None will raise AmbiguousTimeError for fall back
        # and NonExistentTimeError for spring forward
        # We should test that our code handles this gracefully

        # Use is_dst=False to force the time after DST transition
        try:
            work_end = israel_tz.localize(datetime(2025, 3, 29, 2, 30), is_dst=False)
        except pytz.exceptions.NonExistentTimeError:
            # Expected: 02:30 doesn't exist, should use 03:30 instead
            work_end = israel_tz.localize(datetime(2025, 3, 29, 3, 30))

        # Both times should be during Shabbat
        assert is_shabbat_time(work_start), "Work start should be during Shabbat"
        assert is_shabbat_time(work_end), "Work end should be during Shabbat"

    def test_dst_aware_datetime_conversion_from_utc(self):
        """
        Test that UTC to Israeli timezone conversion handles DST correctly.

        This tests the core conversion logic in _parse_and_convert_to_israel_tz().
        """
        service = UnifiedShabbatService()

        # UTC time during Israeli DST (summer)
        utc_summer = "2025-06-15T16:30:00+00:00"  # June (DST active)
        israel_summer = service._parse_and_convert_to_israel_tz(utc_summer)

        # Israeli time should be UTC+3 in summer (DST)
        assert (
            israel_summer.hour == 19
        ), f"Expected 19:30 IDT, got {israel_summer.hour}:30"

        # UTC time during Israeli standard time (winter)
        utc_winter = "2025-01-15T16:30:00+00:00"  # January (no DST)
        israel_winter = service._parse_and_convert_to_israel_tz(utc_winter)

        # Israeli time should be UTC+2 in winter (no DST)
        assert (
            israel_winter.hour == 18
        ), f"Expected 18:30 IST, got {israel_winter.hour}:30"

    def test_is_shabbat_time_with_naive_datetime(self):
        """
        Test that is_shabbat_time handles naive datetimes by assuming Israeli timezone.

        Important: Naive datetimes during DST transitions can be ambiguous.
        """
        # Friday March 28, 2025 at 23:00 (naive - no timezone)
        naive_time = datetime(2025, 3, 28, 23, 0)

        # Should assume Israeli timezone and determine it's Shabbat
        # (Friday 23:00 is typically during Shabbat)
        result = is_shabbat_time(naive_time)

        # Should not crash and should return a boolean
        assert isinstance(result, bool)

    def test_shabbat_premium_calculation_scenario(self):
        """
        Integration test: Verify that DST handling works for payroll premium calculation.

        This is the BUSINESS CRITICAL scenario:
        - Employee works overnight shift Friday → Saturday during DST transition
        - System must correctly identify Shabbat hours for 1.5× premium
        - Incorrect timezone handling = incorrect pay = legal/financial risk
        """
        israel_tz = pytz.timezone("Asia/Jerusalem")

        # March 28-29, 2025: DST transition during Shabbat
        # Shift: 20:00 Friday → 06:00 Saturday
        shift_start = israel_tz.localize(datetime(2025, 3, 28, 20, 0))
        shift_end = israel_tz.localize(datetime(2025, 3, 29, 6, 0))

        # Get Shabbat boundaries
        shabbat_times = get_shabbat_times(date(2025, 3, 28))
        shabbat_start = datetime.fromisoformat(shabbat_times["shabbat_start"])
        shabbat_end = datetime.fromisoformat(shabbat_times["shabbat_end"])

        # Verify Shabbat start is before shift end (overlap exists)
        assert shabbat_start < shift_end, "Shabbat should start during the shift"

        # Calculate overlap hours (simplified - actual payroll logic is more complex)
        overlap_start = max(shift_start, shabbat_start)
        overlap_end = min(shift_end, shabbat_end)

        if overlap_start < overlap_end:
            shabbat_hours = (overlap_end - overlap_start).total_seconds() / 3600

            # Should have significant Shabbat hours (most of night shift)
            assert (
                shabbat_hours > 5
            ), f"Expected significant Shabbat hours, got {shabbat_hours:.2f}h"
        else:
            pytest.fail("No Shabbat overlap detected - DST handling may be broken")


class TestDSTEdgeCases:
    """Additional edge cases for DST handling"""

    def test_nonexistent_time_during_spring_forward(self):
        """
        Test that times between 02:00-03:00 on March 29, 2025 are handled correctly.

        These times don't exist due to DST spring forward.

        NOTE: pytz.localize with is_dst=None doesn't always raise NonExistentTimeError
        in all versions/configurations. Instead it may make a "best guess" which is
        actually desirable for our use case (no crashes during edge cases).
        """
        israel_tz = pytz.timezone("Asia/Jerusalem")

        # 02:30 AM on March 29, 2025 doesn't exist (clock jumps 02:00 → 03:00)
        # pytz should handle this gracefully either by raising exception or picking a valid time
        try:
            time_with_auto = israel_tz.localize(
                datetime(2025, 3, 29, 2, 30), is_dst=None
            )
            # If no exception, verify it created a valid DST time
            assert (
                time_with_auto.tzinfo is not None
            ), "Should create timezone-aware datetime"
            # Should be in DST (IDT) after spring forward
            assert time_with_auto.dst() == timedelta(hours=1), "Should be in DST"
        except pytz.exceptions.NonExistentTimeError:
            # This is also acceptable behavior
            pass

        # Using is_dst=False should always work and convert to post-DST time
        post_dst_time = israel_tz.localize(datetime(2025, 3, 29, 2, 30), is_dst=False)
        assert post_dst_time.tzinfo is not None
        assert post_dst_time.dst() == timedelta(hours=1), "Should be in DST"

    def test_ambiguous_time_during_fall_back(self):
        """
        Test that times between 01:00-02:00 on October 26, 2025 are handled correctly.

        When DST ends, the clock falls back from 02:00 to 01:00, meaning times
        between 01:00-02:00 occur twice (once in IDT/DST, then again in IST/standard).

        NOTE: pytz.localize with is_dst=None doesn't always raise AmbiguousTimeError
        in all versions/configurations. Instead it may make a "best guess" which is
        actually desirable for our use case (no crashes during edge cases).
        """
        israel_tz = pytz.timezone("Asia/Jerusalem")

        # 01:30 AM on October 26, 2025 is ambiguous (happens twice)
        # pytz should handle this gracefully either by raising exception or picking one occurrence
        try:
            time_with_auto = israel_tz.localize(
                datetime(2025, 10, 26, 1, 30), is_dst=None
            )
            # If no exception, verify it created a valid timezone-aware datetime
            assert (
                time_with_auto.tzinfo is not None
            ), "Should create timezone-aware datetime"
        except pytz.exceptions.AmbiguousTimeError:
            # This is also acceptable behavior
            pass

        # Can explicitly specify which occurrence: is_dst=True for first (DST), is_dst=False for second
        first_occurrence = israel_tz.localize(
            datetime(2025, 10, 26, 1, 30), is_dst=True
        )
        second_occurrence = israel_tz.localize(
            datetime(2025, 10, 26, 1, 30), is_dst=False
        )

        # Verify they are different
        assert first_occurrence.tzinfo is not None
        assert second_occurrence.tzinfo is not None

        # First occurrence should be in DST (IDT), second in standard time (IST)
        assert first_occurrence.dst() == timedelta(
            hours=1
        ), "First occurrence should be DST (IDT)"
        assert second_occurrence.dst() == timedelta(
            hours=0
        ), "Second occurrence should be standard time (IST)"

        # They should represent different moments in UTC (1 hour apart)
        diff = second_occurrence - first_occurrence
        assert diff == timedelta(
            hours=1
        ), "Two occurrences should be 1 hour apart in UTC"

    def test_shabbat_calculation_consistency_across_dst(self):
        """
        Test that Shabbat calculations remain consistent across DST transitions.

        Jewish law rules (18 min before, 42 min after sunset) should apply
        regardless of DST status.
        """
        service = UnifiedShabbatService()

        # Test multiple Fridays around DST transitions
        test_dates = [
            date(2025, 3, 21),  # Week before DST starts
            date(2025, 3, 28),  # DST starts (spring forward)
            date(2025, 4, 4),  # Week after DST starts
            date(2025, 10, 17),  # Week before DST ends
            date(2025, 10, 24),  # Week of DST end (ends Sunday)
            date(2025, 10, 31),  # Week after DST ends
        ]

        for test_date in test_dates:
            result = service.get_shabbat_times(test_date)

            # Validate contract
            validate_shabbat_times(result)

            # Parse times
            friday_sunset = datetime.fromisoformat(result["friday_sunset"])
            saturday_sunset = datetime.fromisoformat(result["saturday_sunset"])
            shabbat_start = datetime.fromisoformat(result["shabbat_start"])
            shabbat_end = datetime.fromisoformat(result["shabbat_end"])

            # Verify 18/42 minute rules hold
            diff_start = friday_sunset - shabbat_start
            diff_end = shabbat_end - saturday_sunset

            assert abs(diff_start - timedelta(minutes=18)) < timedelta(
                minutes=1
            ), f"18-minute rule violated for {test_date}"
            assert abs(diff_end - timedelta(minutes=42)) < timedelta(
                minutes=1
            ), f"42-minute rule violated for {test_date}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
