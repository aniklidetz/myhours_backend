import logging
import warnings
from datetime import date, datetime, timedelta

import requests

from django.core.cache import cache

logger = logging.getLogger(__name__)


class SunriseSunsetService:
    """
    Service for interacting with the Sunrise-Sunset API to determine Shabbat start and end times

    .. deprecated:: 2024-09-14
       SunriseSunsetService is deprecated. Use UnifiedShabbatService instead.
       See integrations.services.unified_shabbat_service.get_shabbat_times()
    """

    BASE_URL = "https://api.sunrise-sunset.org/json"
    CACHE_KEY_PREFIX = "sunrise_sunset_"
    SHABBAT_CACHE_PREFIX = "shabbat_"
    CACHE_TIMEOUT = 60 * 60 * 24 * 7  # 7 days

    @classmethod
    def get_times(cls, date_obj=None, lat=31.7683, lng=35.2137, use_cache=True):
        """
        Retrieves sunrise and sunset times for the specified date and coordinates.
        """
        warnings.warn(
            "SunriseSunsetService.get_times() is deprecated. Use integrations.services.unified_shabbat_service.get_shabbat_times() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        if date_obj is None:
            date_obj = date.today()

        # Generate cache key
        cache_key = f"{cls.CACHE_KEY_PREFIX}{date_obj}_{lat}_{lng}"

        # Check cache
        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                return cached_data

        # Prepare request parameters
        params = {
            "lat": lat,
            "lng": lng,
            "date": date_obj.isoformat(),
            "formatted": 0,  # Retrieve time in ISO 8601 format
        }

        try:
            response = requests.get(cls.BASE_URL, params=params)
            response.raise_for_status()

            data = response.json()
            results = data.get("results", {})

            # Cache results
            if use_cache and data.get("status") == "OK":
                cache.set(cache_key, results, cls.CACHE_TIMEOUT)

            return results

        except Exception as e:
            from core.logging_utils import err_tag

            logger.error(
                "Error fetching sunrise-sunset data", extra={"err": err_tag(e)}
            )
            return {}

    @classmethod
    def get_shabbat_times(cls, date_obj, lat=31.7683, lng=35.2137):
        """
        Retrieves Shabbat start and end times for the specified date.
        Optimized to use a single API call for better performance.
        """
        warnings.warn(
            "SunriseSunsetService.get_shabbat_times() is deprecated. Use integrations.services.unified_shabbat_service.get_shabbat_times() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        try:
            # Make sure the date is Friday, or find the next Friday
            if date_obj.weekday() != 4:  # 4 = Friday
                days_until_friday = (4 - date_obj.weekday()) % 7
                date_obj = date_obj + timedelta(days=days_until_friday)

            # Check cache first for complete Shabbat times
            cache_key = f"{cls.SHABBAT_CACHE_PREFIX}{lat}:{lng}:{date_obj.isoformat()}"
            cached_result = cache.get(cache_key)
            if cached_result:
                return cached_result

            saturday = date_obj + timedelta(days=1)

            # Use a single API call and estimate Saturday sunset based on Friday data
            # This is an optimization to reduce API calls from 2 to 1
            friday_times = cls.get_times(date_obj, lat, lng, use_cache=True)

            if not friday_times:
                # API call failed, return fallback times
                fallback_result = {
                    "date": date_obj.isoformat(),
                    "start": (
                        datetime.combine(
                            date_obj, datetime.min.time().replace(hour=18, minute=0)
                        ).isoformat()
                    ),
                    "end": (
                        datetime.combine(
                            saturday, datetime.min.time().replace(hour=19, minute=30)
                        ).isoformat()
                    ),
                    "is_estimated": True,
                }
                cache.set(cache_key, fallback_result, cls.CACHE_TIMEOUT)
                return fallback_result

            # Extract Friday sunset
            friday_sunset_str = friday_times.get("sunset")
            if not friday_sunset_str:
                # No sunset data, return fallback
                fallback_result = {
                    "date": date_obj.isoformat(),
                    "start": (
                        datetime.combine(
                            date_obj, datetime.min.time().replace(hour=18, minute=0)
                        ).isoformat()
                    ),
                    "end": (
                        datetime.combine(
                            saturday, datetime.min.time().replace(hour=19, minute=30)
                        ).isoformat()
                    ),
                    "is_estimated": True,
                }
                cache.set(cache_key, fallback_result, cls.CACHE_TIMEOUT)
                return fallback_result

            # Parse Friday sunset time
            try:
                friday_sunset = datetime.fromisoformat(
                    friday_sunset_str.replace("Z", "+00:00")
                )
            except ValueError as e:
                from core.logging_utils import err_tag

                logger.error(
                    "Error parsing Friday sunset time", extra={"err": err_tag(e)}
                )
                fallback_result = {
                    "date": date_obj.isoformat(),
                    "start": (
                        datetime.combine(
                            date_obj, datetime.min.time().replace(hour=18, minute=0)
                        ).isoformat()
                    ),
                    "end": (
                        datetime.combine(
                            saturday, datetime.min.time().replace(hour=19, minute=30)
                        ).isoformat()
                    ),
                    "is_estimated": True,
                }
                cache.set(cache_key, fallback_result, cls.CACHE_TIMEOUT)
                return fallback_result

            # Estimate Saturday sunset (typically 1-2 minutes later than Friday in summer)
            # This is a reasonable approximation for consecutive days
            saturday_sunset = friday_sunset + timedelta(days=1, minutes=1)

            # Calculate Shabbat start and end times
            shabbat_start = friday_sunset - timedelta(minutes=18)
            shabbat_end = saturday_sunset + timedelta(minutes=42)

            result = {
                "date": date_obj.isoformat(),
                "start": shabbat_start.isoformat(),
                "end": shabbat_end.isoformat(),
                "friday_sunset": friday_sunset.isoformat(),
                "saturday_sunset": saturday_sunset.isoformat(),
                "is_estimated": False,
            }

            # Cache the successful result
            cache.set(cache_key, result, cls.CACHE_TIMEOUT)
            return result
        except Exception as e:
            from core.logging_utils import err_tag

            logger.error(
                "Error calculating Shabbat times for {date_obj}",
                extra={"err": err_tag(e)},
            )
            # Return approximate times in case of any error
            error_result = {
                "date": date_obj.isoformat(),
                "start": (
                    datetime.combine(
                        date_obj, datetime.min.time().replace(hour=18, minute=0)
                    ).isoformat()
                ),
                "end": (
                    datetime.combine(
                        date_obj + timedelta(days=1),
                        datetime.min.time().replace(hour=19, minute=30),
                    ).isoformat()
                ),
                "is_estimated": True,
            }
            # Cache the error result to prevent repeated failures
            cache_key = f"{cls.SHABBAT_CACHE_PREFIX}{lat}:{lng}:{date_obj.isoformat()}"
            cache.set(cache_key, error_result, cls.CACHE_TIMEOUT)
            return error_result

    @classmethod
    def _calculate_estimated_shabbat_times(cls, date_obj):
        """
        Calculate estimated Shabbat times when API is unavailable.
        Uses fixed sunset time approximations.
        """
        # Make sure the date is Friday, or find the next Friday
        if date_obj.weekday() != 4:  # 4 = Friday
            days_until_friday = (4 - date_obj.weekday()) % 7
            date_obj = date_obj + timedelta(days=days_until_friday)

        saturday = date_obj + timedelta(days=1)

        return {
            "date": date_obj.isoformat(),
            "start": (
                datetime.combine(
                    date_obj, datetime.min.time().replace(hour=18, minute=0)
                ).isoformat()
            ),
            "end": (
                datetime.combine(
                    saturday, datetime.min.time().replace(hour=19, minute=30)
                ).isoformat()
            ),
            "is_estimated": True,
        }

    @classmethod
    def is_shabbat_time(cls, check_time, lat=31.7683, lng=35.2137):
        """
        Check if a given datetime falls within Shabbat time.

        Args:
            check_time: datetime object to check
            lat: Latitude for location
            lng: Longitude for location

        Returns:
            bool: True if within Shabbat time
        """
        try:
            # Get the Friday for this week
            days_since_friday = (check_time.weekday() - 4) % 7
            friday_date = check_time.date() - timedelta(days=days_since_friday)

            # Get Shabbat times for this Friday
            shabbat_times = cls.get_shabbat_times(friday_date, lat, lng)

            # Parse Shabbat start and end times
            start_time = datetime.fromisoformat(
                shabbat_times["start"].replace("Z", "+00:00")
            )
            end_time = datetime.fromisoformat(
                shabbat_times["end"].replace("Z", "+00:00")
            )

            # Ensure check_time is timezone-aware
            if check_time.tzinfo is None:
                check_time = check_time.replace(tzinfo=start_time.tzinfo)

            return start_time <= check_time <= end_time

        except Exception as e:
            from core.logging_utils import err_tag

            logger.error("Error checking Shabbat time", extra={"err": err_tag(e)})
            return False
