"""
Enhanced Sunrise-Sunset Service with proper timezone handling for Israel

Fixes timezone issues and integrates with Redis cache for better performance
"""

import logging
import warnings
from datetime import date, datetime, timedelta

import pytz
import requests

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class EnhancedSunriseSunsetService:
    """
    Enhanced service with proper Israeli timezone handling and Redis integration

    .. deprecated:: 2024-09-14
       EnhancedSunriseSunsetService is deprecated. Use UnifiedShabbatService instead.
       See integrations.services.unified_shabbat_service.get_shabbat_times()
    """

    BASE_URL = "https://api.sunrise-sunset.org/json"
    CACHE_KEY_PREFIX = "enhanced_sunrise_sunset_"
    SHABBAT_CACHE_PREFIX = "enhanced_shabbat_"
    CACHE_TIMEOUT = 60 * 60 * 24 * 7  # 7 days

    # Israeli coordinates (Jerusalem)
    DEFAULT_LAT = 31.7683
    DEFAULT_LNG = 35.2137

    # Israeli timezone
    ISRAEL_TZ = pytz.timezone("Asia/Jerusalem")
    UTC_TZ = pytz.UTC

    @classmethod
    def get_times_with_israeli_timezone(
        cls, date_obj=None, lat=None, lng=None, use_cache=True
    ):
        """
        Get sunrise/sunset times converted to Israeli timezone

        Returns times in Israel timezone instead of UTC
        """
        if date_obj is None:
            date_obj = date.today()

        if lat is None:
            lat = cls.DEFAULT_LAT
        if lng is None:
            lng = cls.DEFAULT_LNG

        # Generate cache key
        cache_key = f"{cls.CACHE_KEY_PREFIX}il_{date_obj}_{lat}_{lng}"

        # Check cache
        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.debug(f"📋 Cache HIT for sunrise-sunset times {date_obj}")
                return cached_data

        # Prepare request parameters
        params = {
            "lat": lat,
            "lng": lng,
            "date": date_obj.isoformat(),
            "formatted": 0,  # Get UTC time in ISO format
        }

        try:
            logger.debug(f"🌐 API call to sunrise-sunset.org for {date_obj}")
            response = requests.get(cls.BASE_URL, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if data.get("status") != "OK":
                logger.error(f"Sunrise-sunset API error: {data}")
                return None

            results = data.get("results", {})

            # Convert UTC times to Israeli timezone
            israeli_results = {}
            for key, utc_time_str in results.items():
                try:
                    if utc_time_str and isinstance(utc_time_str, str):
                        # Parse UTC time
                        utc_dt = datetime.fromisoformat(
                            utc_time_str.replace("Z", "+00:00")
                        )

                        # Convert to Israeli timezone
                        israeli_dt = utc_dt.astimezone(cls.ISRAEL_TZ)

                        # Store both formats
                        israeli_results[key] = israeli_dt.isoformat()
                        israeli_results[f"{key}_utc"] = utc_time_str

                except ValueError as e:
                    logger.error(
                        f"Error parsing time {key}: {utc_time_str}, error: {e}"
                    )
                    israeli_results[key] = utc_time_str  # Fallback to original

            # Add metadata
            israeli_results["timezone"] = "Asia/Jerusalem"
            israeli_results["api_date"] = date_obj.isoformat()
            israeli_results["coordinates"] = {"lat": lat, "lng": lng}

            # Cache results
            if use_cache:
                cache.set(cache_key, israeli_results, cls.CACHE_TIMEOUT)
                logger.debug(f"📋 Cached sunrise-sunset times for {date_obj}")

            return israeli_results

        except requests.RequestException as e:
            from core.logging_utils import err_tag

            logger.error(
                "Network error fetching sunrise-sunset data", extra={"err": err_tag(e)}
            )
            return None
        except Exception as e:
            from core.logging_utils import err_tag

            logger.error(
                "Unexpected error in sunrise-sunset service", extra={"err": err_tag(e)}
            )
            return None

    @classmethod
    def get_shabbat_times_israeli_timezone(
        cls, date_obj, lat=None, lng=None, use_cache=True
    ):
        """
        Get precise Shabbat start and end times in Israeli timezone

        Returns:
            Dict with Shabbat times in Israeli timezone
        """
        warnings.warn(
            "EnhancedSunriseSunsetService.get_shabbat_times_israeli_timezone() is deprecated. Use integrations.services.unified_shabbat_service.get_shabbat_times() instead.",
            DeprecationWarning,
            stacklevel=2
        )

        if lat is None:
            lat = cls.DEFAULT_LAT
        if lng is None:
            lng = cls.DEFAULT_LNG

        try:
            # Ensure we have Friday
            if date_obj.weekday() != 4:  # 4 = Friday
                days_until_friday = (4 - date_obj.weekday()) % 7
                if days_until_friday == 0:
                    days_until_friday = 7  # Next Friday
                date_obj = date_obj + timedelta(days=days_until_friday)

            # Check cache first
            cache_key = f"{cls.SHABBAT_CACHE_PREFIX}il_{date_obj}_{lat}_{lng}"
            if use_cache:
                cached_result = cache.get(cache_key)
                if cached_result:
                    logger.debug(f"📋 Cache HIT for Shabbat times {date_obj}")
                    return cached_result

            saturday = date_obj + timedelta(days=1)

            # Get Friday sunset times in Israeli timezone
            friday_times = cls.get_times_with_israeli_timezone(
                date_obj, lat, lng, use_cache
            )

            if not friday_times or "sunset" not in friday_times:
                # Fallback to approximate times in Israeli timezone
                logger.warning(f"Using fallback Shabbat times for {date_obj}")
                fallback_result = cls._get_fallback_shabbat_times(date_obj, saturday)
                if use_cache:
                    cache.set(cache_key, fallback_result, cls.CACHE_TIMEOUT)
                return fallback_result

            # Parse Friday sunset (already in Israeli timezone)
            try:
                friday_sunset_str = friday_times["sunset"]
                friday_sunset = datetime.fromisoformat(friday_sunset_str)

                # Ensure it's timezone-aware
                if friday_sunset.tzinfo is None:
                    friday_sunset = cls.ISRAEL_TZ.localize(friday_sunset)

            except ValueError as e:
                from core.logging_utils import err_tag

                logger.error("Error parsing Friday sunset", extra={"err": err_tag(e)})
                fallback_result = cls._get_fallback_shabbat_times(date_obj, saturday)
                if use_cache:
                    cache.set(cache_key, fallback_result, cls.CACHE_TIMEOUT)
                return fallback_result

            # Get Saturday sunset (more accurate than estimation)
            saturday_times = cls.get_times_with_israeli_timezone(
                saturday, lat, lng, use_cache
            )

            if saturday_times and "sunset" in saturday_times:
                try:
                    saturday_sunset_str = saturday_times["sunset"]
                    saturday_sunset = datetime.fromisoformat(saturday_sunset_str)

                    if saturday_sunset.tzinfo is None:
                        saturday_sunset = cls.ISRAEL_TZ.localize(saturday_sunset)

                except ValueError:
                    # Fallback to estimation
                    saturday_sunset = friday_sunset + timedelta(days=1, minutes=1)
            else:
                # Estimation fallback
                saturday_sunset = friday_sunset + timedelta(days=1, minutes=1)

            # Calculate Shabbat times according to Jewish law
            # Shabbat starts 18 minutes before sunset on Friday
            shabbat_start = friday_sunset - timedelta(minutes=18)

            # Shabbat ends when three stars appear (approximately 42 minutes after Saturday sunset)
            shabbat_end = saturday_sunset + timedelta(minutes=42)

            result = {
                "date": date_obj.isoformat(),
                "friday_date": date_obj.isoformat(),
                "saturday_date": saturday.isoformat(),
                "shabbat_start": shabbat_start.isoformat(),
                "shabbat_end": shabbat_end.isoformat(),
                "friday_sunset": friday_sunset.isoformat(),
                "saturday_sunset": saturday_sunset.isoformat(),
                "timezone": "Asia/Jerusalem",
                "coordinates": {"lat": lat, "lng": lng},
                "is_estimated": False,
                "calculation_method": "api_precise",
            }

            # Cache the result
            if use_cache:
                cache.set(cache_key, result, cls.CACHE_TIMEOUT)
                logger.info(
                    f"📅 Cached precise Shabbat times for {date_obj} in Israeli timezone"
                )

            return result

        except Exception as e:
            from core.logging_utils import err_tag

            logger.error(
                "Error calculating Israeli Shabbat times",
                extra={"err": err_tag(e), "date": str(date_obj)},
            )
            # Return fallback times
            fallback_result = cls._get_fallback_shabbat_times(date_obj, saturday)
            if use_cache:
                cache.set(cache_key, fallback_result, cls.CACHE_TIMEOUT)
            return fallback_result

    @classmethod
    def _get_fallback_shabbat_times(cls, friday, saturday):
        """
        Get fallback Shabbat times when API is unavailable

        Uses approximate Israeli sunset times based on season
        """
        # Approximate Israeli sunset times by season
        month = friday.month

        if month in [6, 7, 8]:  # Summer
            sunset_hour, sunset_minute = 19, 30
        elif month in [12, 1, 2]:  # Winter
            sunset_hour, sunset_minute = 16, 45
        elif month in [3, 4, 5]:  # Spring
            sunset_hour, sunset_minute = 18, 15
        else:  # Fall (9, 10, 11)
            sunset_hour, sunset_minute = 17, 30

        # Create timezone-aware datetime objects
        friday_sunset = cls.ISRAEL_TZ.localize(
            datetime.combine(
                friday,
                datetime.min.time().replace(hour=sunset_hour, minute=sunset_minute),
            )
        )

        saturday_sunset = cls.ISRAEL_TZ.localize(
            datetime.combine(
                saturday,
                datetime.min.time().replace(hour=sunset_hour, minute=sunset_minute + 1),
            )
        )

        shabbat_start = friday_sunset - timedelta(minutes=18)
        shabbat_end = saturday_sunset + timedelta(minutes=42)

        return {
            "date": friday.isoformat(),
            "friday_date": friday.isoformat(),
            "saturday_date": saturday.isoformat(),
            "shabbat_start": shabbat_start.isoformat(),
            "shabbat_end": shabbat_end.isoformat(),
            "friday_sunset": friday_sunset.isoformat(),
            "saturday_sunset": saturday_sunset.isoformat(),
            "timezone": "Asia/Jerusalem",
            "coordinates": {"lat": cls.DEFAULT_LAT, "lng": cls.DEFAULT_LNG},
            "is_estimated": True,
            "calculation_method": "seasonal_fallback",
        }

    @classmethod
    def validate_timezone_consistency(cls):
        """
        Validate that Django timezone matches our Israeli timezone
        """
        django_tz = getattr(settings, "TIME_ZONE", None)

        if django_tz != "Asia/Jerusalem":
            logger.warning(
                f"Django TIME_ZONE is {django_tz}, but service uses Asia/Jerusalem"
            )
            return False

        logger.info(
            "✅ Timezone consistency validated: Django and service both use Asia/Jerusalem"
        )
        return True


# Create service instance
enhanced_sunrise_sunset_service = EnhancedSunriseSunsetService()


# Wrapper function for backward compatibility with tests
def get_shabbat_times_israeli_timezone(date_obj, lat=31.7683, lon=35.2137):
    """
    Wrapper function for test compatibility
    Maps old function signature to the class method
    """
    warnings.warn(
        "get_shabbat_times_israeli_timezone() is deprecated. Use integrations.services.unified_shabbat_service.get_shabbat_times() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return enhanced_sunrise_sunset_service.get_shabbat_times_israeli_timezone(
        date_obj=date_obj,
        lat=lat,
        lng=lon,  # Note: parameter name change from 'lon' to 'lng'
    )
