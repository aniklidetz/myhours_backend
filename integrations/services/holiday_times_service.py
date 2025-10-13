"""
Service for calculating holiday start and end times based on Jewish calendar rules.

Jewish holidays begin at sunset on the evening before the holiday date
and end at nightfall on the holiday date (or the day after for 2-day holidays).
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

from django.utils import timezone

from integrations.services.unified_shabbat_service import (
    get_nightfall_time,
    get_sunset_time,
)

logger = logging.getLogger(__name__)


class HolidayTimesService:
    """
    Calculate start and end times for Jewish holidays.

    Jewish holidays follow these rules:
    - Start at sunset on the evening before
    - End at nightfall on the holiday date
    - Two-day holidays end at nightfall on the second day
    """

    # Two-day holidays (in Israel)
    TWO_DAY_HOLIDAYS = [
        "Rosh Hashana",  # Always 2 days even in Israel
    ]

    # Standard buffer times (same as Shabbat)
    STANDARD_START_BUFFER = 18  # Minutes before sunset (candle lighting)
    STANDARD_END_BUFFER = (
        0  # Already included in nightfall calculation (42 min after sunset)
    )

    # Holidays that have special timing rules
    SPECIAL_TIMING_HOLIDAYS = {
        "Yom Kippur": {
            "start_offset": 40,  # Starts 40 minutes before sunset
            "end_offset": 10,  # Ends 10 minutes after normal nightfall
        },
        "Tish'a B'Av": {
            "start_offset": 18,  # Normal candle lighting time
            "end_offset": 0,  # Normal nightfall
        },
    }

    @classmethod
    def calculate_holiday_times(
        cls,
        holiday_date: datetime.date,
        holiday_name: str,
        lat: float = 31.7683,  # Jerusalem
        lng: float = 35.2137,  # Jerusalem
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        Calculate start and end times for a Jewish holiday.

        Args:
            holiday_date: The date of the holiday
            holiday_name: Name of the holiday
            lat: Latitude for sunset/nightfall calculation
            lng: Longitude for sunset/nightfall calculation

        Returns:
            Tuple of (start_time, end_time) as timezone-aware datetimes
        """
        try:
            # Get sunset on the evening before (holiday starts)
            day_before = holiday_date - timedelta(days=1)
            sunset = get_sunset_time(day_before, lat, lng)

            # Determine end date (same day or next day for 2-day holidays)
            is_two_day = any(
                two_day in holiday_name for two_day in cls.TWO_DAY_HOLIDAYS
            )

            if is_two_day or "II" in holiday_name:
                # For second day or explicitly 2-day holidays
                end_date = holiday_date + timedelta(days=1)
            else:
                end_date = holiday_date

            # Get nightfall on the end date (holiday ends)
            nightfall = get_nightfall_time(end_date, lat, lng)

            # Apply timing buffers
            if sunset:
                # Default: add standard buffer before sunset (candle lighting)
                sunset = sunset - timedelta(minutes=cls.STANDARD_START_BUFFER)

            # Check for special timing rules
            for special_holiday, offsets in cls.SPECIAL_TIMING_HOLIDAYS.items():
                if special_holiday in holiday_name:
                    if sunset:
                        # Override with special offset (already subtracted standard, so adjust)
                        sunset = sunset + timedelta(
                            minutes=cls.STANDARD_START_BUFFER
                        )  # Undo standard
                        sunset = sunset - timedelta(
                            minutes=offsets["start_offset"]
                        )  # Apply special
                    if nightfall:
                        nightfall = nightfall + timedelta(minutes=offsets["end_offset"])
                    break

            # Sunset and nightfall should already be in Israeli timezone from get_sunset_time/get_nightfall_time
            # Just ensure they're timezone aware
            if sunset and sunset.tzinfo is None:
                # This shouldn't happen with current implementation, but safety check
                import pytz

                israel_tz = pytz.timezone("Asia/Jerusalem")
                sunset = israel_tz.localize(sunset)
            if nightfall and nightfall.tzinfo is None:
                import pytz

                israel_tz = pytz.timezone("Asia/Jerusalem")
                nightfall = israel_tz.localize(nightfall)

            return sunset, nightfall

        except Exception as e:
            logger.error(
                f"Error calculating times for {holiday_name} on {holiday_date}: {e}"
            )
            return None, None

    @classmethod
    def should_have_times(cls, holiday_name: str) -> bool:
        """
        Determine if a holiday should have start/end times.

        Only official holidays and special observances should have times.
        Minor holidays and CH''M days typically don't need precise times.

        Args:
            holiday_name: Name of the holiday

        Returns:
            bool: True if holiday should have times
        """
        # Import here to avoid circular dependency
        from integrations.config.israeli_holidays import is_official_holiday

        # Official holidays should have times
        if is_official_holiday(holiday_name):
            return True

        # Special fasts and observances
        special_observances = [
            "Tish'a B'Av",
            "Tzom Gedaliah",
            "Asara B'Tevet",
            "Ta'anit Esther",
            "Ta'anit Bekhorot",
        ]

        for observance in special_observances:
            if observance in holiday_name:
                return True

        return False
