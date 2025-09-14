"""
Unified Shabbat Service - Single source of truth for Shabbat times

This service replaces both SunriseSunsetService and EnhancedSunriseSunsetService
with a single, precise, and consistent implementation that always returns
the standardized ShabbatTimes contract.

Key improvements:
- Always uses precise calculations (2 API calls when possible)
- Consistent ShabbatTimes contract return type
- Proper Israeli timezone handling
- Comprehensive error handling with fallbacks
- Built-in caching for performance
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

import pytz
import requests
from django.core.cache import cache

from payroll.services.contracts import ShabbatTimes, validate_shabbat_times, create_fallback_shabbat_times

logger = logging.getLogger(__name__)


class UnifiedShabbatService:
    """
    Single source of truth for Shabbat times with precise Israeli labor law compliance.

    This service always aims for maximum precision using two API calls (Friday + Saturday)
    with intelligent fallback to seasonal approximations when API is unavailable.

    All returned times are in Israeli timezone (Asia/Jerusalem) and conform to
    the ShabbatTimes contract for type safety and consistency.
    """

    # API Configuration
    BASE_URL = "https://api.sunrise-sunset.org/json"
    CACHE_KEY_PREFIX = "unified_shabbat_"
    CACHE_TIMEOUT = 60 * 60 * 24 * 7  # 7 days

    # Israeli coordinates (Jerusalem default)
    DEFAULT_LAT = 31.7683
    DEFAULT_LNG = 35.2137

    # Israeli timezone
    ISRAEL_TZ = pytz.timezone("Asia/Jerusalem")
    UTC_TZ = pytz.UTC

    # Jewish law constants
    SHABBAT_START_BUFFER_MINUTES = 18  # Candle lighting time (18 min before sunset)
    SHABBAT_END_BUFFER_MINUTES = 42    # Havdalah time (42 min after sunset, 3 stars appear)

    def __init__(self):
        """Initialize service with logging setup"""
        self._api_calls_made = 0
        self._cache_hits = 0

    def get_shabbat_times(
        self,
        date_obj: date,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        use_cache: bool = True
    ) -> ShabbatTimes:
        """
        Get precise Shabbat start and end times in Israeli timezone.

        Always attempts maximum precision with two API calls (Friday + Saturday).
        Falls back to seasonal approximations if API is unavailable.

        Args:
            date_obj: Any date (will find the appropriate Friday)
            lat: Latitude (defaults to Jerusalem)
            lng: Longitude (defaults to Jerusalem)
            use_cache: Whether to use caching (recommended: True)

        Returns:
            ShabbatTimes: Validated Shabbat times in standardized format

        Raises:
            ValidationError: If result doesn't conform to ShabbatTimes contract
        """
        # Use defaults if coordinates not provided
        if lat is None:
            lat = self.DEFAULT_LAT
        if lng is None:
            lng = self.DEFAULT_LNG

        try:
            # Ensure we have Friday for the week
            friday_date = self._get_friday_for_date(date_obj)
            saturday_date = friday_date + timedelta(days=1)

            # Check cache first
            cache_key = f"{self.CACHE_KEY_PREFIX}{friday_date}_{lat}_{lng}"
            if use_cache:
                cached_result = cache.get(cache_key)
                if cached_result:
                    logger.debug(f"📋 Cache HIT for Shabbat times {friday_date}")
                    self._cache_hits += 1
                    return validate_shabbat_times(cached_result)

            # Try precise calculation with API
            result = self._calculate_precise_times(friday_date, saturday_date, lat, lng)

            # Cache successful result
            if use_cache and result:
                cache.set(cache_key, result, self.CACHE_TIMEOUT)
                logger.debug(f"📋 Cached precise Shabbat times for {friday_date}")

            return validate_shabbat_times(result)

        except Exception as e:
            logger.error(
                f"Error in UnifiedShabbatService for {date_obj}",
                extra={"error": str(e), "lat": lat, "lng": lng},
                exc_info=True
            )

            # Return fallback times - always works
            friday_date = self._get_friday_for_date(date_obj)
            fallback_result = create_fallback_shabbat_times(
                friday_date=friday_date.isoformat(),
                calculation_method="api_failed",
                coordinates={"lat": lat, "lng": lng}
            )

            # Cache fallback to prevent repeated API failures
            if use_cache:
                cache_key = f"{self.CACHE_KEY_PREFIX}{friday_date}_{lat}_{lng}"
                cache.set(cache_key, fallback_result, self.CACHE_TIMEOUT // 4)  # Shorter cache for fallbacks

            return fallback_result

    def _get_friday_for_date(self, date_obj: date) -> date:
        """Get the Friday for the week containing the given date"""
        if date_obj.weekday() == 4:  # Already Friday
            return date_obj
        elif date_obj.weekday() < 4:  # Monday-Thursday: go forward to Friday this week
            days_to_friday = 4 - date_obj.weekday()
            return date_obj + timedelta(days=days_to_friday)
        else:  # Saturday-Sunday: go back to Friday of this week
            days_back_to_friday = date_obj.weekday() - 4
            return date_obj - timedelta(days=days_back_to_friday)

    def _calculate_precise_times(
        self,
        friday_date: date,
        saturday_date: date,
        lat: float,
        lng: float
    ) -> ShabbatTimes:
        """
        Calculate precise Shabbat times using two API calls.

        This is the core precision method that makes separate calls for
        Friday and Saturday sunset times for maximum accuracy.
        """
        try:
            # Get Friday sunset time
            friday_times = self._get_api_times(friday_date, lat, lng)
            if not friday_times or "sunset" not in friday_times:
                raise RuntimeError("Failed to get Friday sunset from API")

            # Get Saturday sunset time for precision
            saturday_times = self._get_api_times(saturday_date, lat, lng)
            saturday_sunset_str = None
            if saturday_times and "sunset" in saturday_times:
                saturday_sunset_str = saturday_times["sunset"]

            # Parse Friday sunset (convert from UTC to Israeli time)
            friday_sunset_utc_str = friday_times["sunset"]
            friday_sunset = self._parse_and_convert_to_israel_tz(friday_sunset_utc_str)

            # Parse Saturday sunset or estimate
            if saturday_sunset_str:
                saturday_sunset = self._parse_and_convert_to_israel_tz(saturday_sunset_str)
                calculation_method = "api_precise"
            else:
                # Fallback: estimate Saturday sunset (typically 1-2 minutes later)
                saturday_sunset = friday_sunset + timedelta(days=1, minutes=1)
                calculation_method = "api_estimated"
                logger.info(f"Using estimated Saturday sunset for {saturday_date}")

            # Calculate Shabbat times according to Jewish law
            shabbat_start = friday_sunset - timedelta(minutes=self.SHABBAT_START_BUFFER_MINUTES)
            shabbat_end = saturday_sunset + timedelta(minutes=self.SHABBAT_END_BUFFER_MINUTES)

            # Build result conforming to ShabbatTimes contract
            result = ShabbatTimes(
                shabbat_start=shabbat_start.isoformat(),
                shabbat_end=shabbat_end.isoformat(),
                friday_sunset=friday_sunset.isoformat(),
                saturday_sunset=saturday_sunset.isoformat(),
                timezone="Asia/Jerusalem",
                is_estimated=(calculation_method == "api_estimated"),
                calculation_method=calculation_method,
                coordinates={"lat": lat, "lng": lng},
                friday_date=friday_date.isoformat(),
                saturday_date=saturday_date.isoformat()
            )

            logger.info(
                f"✅ Calculated precise Shabbat times for {friday_date} "
                f"(method: {calculation_method}, API calls: {self._api_calls_made})"
            )

            return result

        except Exception as e:
            logger.error(f"Precise calculation failed: {e}")
            raise  # Re-raise to trigger fallback in parent method

    def _get_api_times(self, date_obj: date, lat: float, lng: float) -> Optional[dict]:
        """
        Make API call to sunrise-sunset.org for a specific date.

        Returns raw API response with UTC times.
        """
        params = {
            "lat": lat,
            "lng": lng,
            "date": date_obj.isoformat(),
            "formatted": 0  # Get UTC time in ISO format
        }

        try:
            logger.debug(f"🌐 API call to sunrise-sunset.org for {date_obj}")
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            response.raise_for_status()

            self._api_calls_made += 1

            data = response.json()
            if data.get("status") != "OK":
                logger.error(f"Sunrise-sunset API error for {date_obj}: {data}")
                return None

            return data.get("results", {})

        except requests.RequestException as e:
            logger.error(f"Network error calling sunrise-sunset API for {date_obj}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected API error for {date_obj}: {e}")
            return None

    def _parse_and_convert_to_israel_tz(self, utc_time_str: str) -> datetime:
        """
        Parse UTC time string from API and convert to Israeli timezone.

        Args:
            utc_time_str: UTC time string like "2024-01-05T16:30:15+00:00"

        Returns:
            datetime: Timezone-aware datetime in Israeli timezone
        """
        try:
            # Parse UTC time
            utc_dt = datetime.fromisoformat(utc_time_str.replace("Z", "+00:00"))

            # Ensure UTC timezone
            if utc_dt.tzinfo is None:
                utc_dt = self.UTC_TZ.localize(utc_dt)

            # Convert to Israeli timezone
            israel_dt = utc_dt.astimezone(self.ISRAEL_TZ)

            return israel_dt

        except ValueError as e:
            logger.error(f"Failed to parse time string '{utc_time_str}': {e}")
            raise ValueError(f"Invalid time format: {utc_time_str}") from e

    def is_shabbat_time(
        self,
        check_time: datetime,
        lat: Optional[float] = None,
        lng: Optional[float] = None
    ) -> bool:
        """
        Check if a given datetime falls within Shabbat time.

        Args:
            check_time: Datetime to check (should be timezone-aware)
            lat: Latitude (defaults to Jerusalem)
            lng: Longitude (defaults to Jerusalem)

        Returns:
            bool: True if within Shabbat time
        """
        try:
            # Ensure timezone-aware
            if check_time.tzinfo is None:
                logger.warning("check_time should be timezone-aware, assuming Israeli time")
                check_time = self.ISRAEL_TZ.localize(check_time)

            # Convert to Israeli timezone for consistency
            check_time_israel = check_time.astimezone(self.ISRAEL_TZ)

            # Get Shabbat times for this week
            shabbat_times = self.get_shabbat_times(
                date_obj=check_time.date(),
                lat=lat,
                lng=lng
            )

            # Parse Shabbat start/end times
            shabbat_start = datetime.fromisoformat(shabbat_times["shabbat_start"])
            shabbat_end = datetime.fromisoformat(shabbat_times["shabbat_end"])

            # Check if time falls within Shabbat
            return shabbat_start <= check_time_israel <= shabbat_end

        except Exception as e:
            logger.error(f"Error checking Shabbat time for {check_time}: {e}")
            return False

    def get_service_stats(self) -> dict:
        """Get service usage statistics for monitoring"""
        return {
            "api_calls_made": self._api_calls_made,
            "cache_hits": self._cache_hits,
            "service_version": "unified_v1.0"
        }


# Global service instance
unified_shabbat_service = UnifiedShabbatService()


# Convenience functions for backward compatibility during migration
def get_shabbat_times(
    date_obj: date,
    lat: float = 31.7683,
    lng: float = 35.2137,
    use_cache: bool = True
) -> ShabbatTimes:
    """
    Convenience function that uses the global unified service instance.

    This provides a simple import path during migration from old services.
    """
    return unified_shabbat_service.get_shabbat_times(
        date_obj=date_obj,
        lat=lat,
        lng=lng,
        use_cache=use_cache
    )


def is_shabbat_time(
    check_time: datetime,
    lat: float = 31.7683,
    lng: float = 35.2137
) -> bool:
    """Convenience function for Shabbat time checking"""
    return unified_shabbat_service.is_shabbat_time(
        check_time=check_time,
        lat=lat,
        lng=lng
    )