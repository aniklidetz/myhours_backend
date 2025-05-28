import requests
import logging
from datetime import date, datetime, timedelta
from django.core.cache import cache

logger = logging.getLogger(__name__)

class SunriseSunsetService:
    """Service for interacting with the Sunrise-Sunset API to determine Shabbat start and end times"""
    
    BASE_URL = "https://api.sunrise-sunset.org/json"
    CACHE_KEY_PREFIX = "sunrise_sunset_"
    CACHE_TIMEOUT = 60 * 60 * 24 * 7  # 7 days
    
    @classmethod
    def get_times(cls, date_obj=None, lat=31.7683, lng=35.2137, use_cache=True):
        """
        Retrieves sunrise and sunset times for the specified date and coordinates.
        """
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
            "formatted": 0  # Retrieve time in ISO 8601 format
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
            logger.error(f"Error fetching sunrise-sunset data: {e}")
            return {}
            
    @classmethod
    def get_shabbat_times(cls, date_obj, lat=31.7683, lng=35.2137):
        """
        Retrieves Shabbat start and end times for the specified date.
        """
        try:
            # Make sure the date is Friday, or find the next Friday
            if date_obj.weekday() != 4:  # 4 = Friday
                days_until_friday = (4 - date_obj.weekday()) % 7
                date_obj = date_obj + timedelta(days=days_until_friday)
            
            # Get sunset time for Friday (Shabbat start)
            friday_times = cls.get_times(date_obj, lat, lng)
            
            # Get sunset time for Saturday (Shabbat end)
            saturday = date_obj + timedelta(days=1)
            saturday_times = cls.get_times(saturday, lat, lng)
            
            # Check if required data is available
            if not friday_times or not saturday_times:
                logger.warning(f"Missing sunrise-sunset data for {date_obj} or {saturday}")
                # Use fixed fallback times as a backup
                return {
                    "date": date_obj.isoformat(),
                    "start": (datetime.combine(date_obj, datetime.min.time().replace(hour=18, minute=0))
                            .isoformat()),
                    "end": (datetime.combine(saturday, datetime.min.time().replace(hour=19, minute=30))
                            .isoformat()),
                    "is_estimated": True
                }
            
            # Extract sunset times from API response
            friday_sunset_str = friday_times.get("sunset")
            saturday_sunset_str = saturday_times.get("sunset")
            
            if not friday_sunset_str or not saturday_sunset_str:
                logger.warning(f"Missing sunset times for {date_obj} or {saturday}")
                # Use fixed fallback times as a backup
                return {
                    "date": date_obj.isoformat(),
                    "start": (datetime.combine(date_obj, datetime.min.time().replace(hour=18, minute=0))
                            .isoformat()),
                    "end": (datetime.combine(saturday, datetime.min.time().replace(hour=19, minute=30))
                            .isoformat()),
                    "is_estimated": True
                }
            
            # Convert string timestamps to datetime objects
            try:
                friday_sunset = datetime.fromisoformat(friday_sunset_str.replace('Z', '+00:00'))
                saturday_sunset = datetime.fromisoformat(saturday_sunset_str.replace('Z', '+00:00'))
            except ValueError as e:
                logger.error(f"Error parsing sunset times: {e}")
                # Use fixed fallback times as a backup
                return {
                    "date": date_obj.isoformat(),
                    "start": (datetime.combine(date_obj, datetime.min.time().replace(hour=18, minute=0))
                            .isoformat()),
                    "end": (datetime.combine(saturday, datetime.min.time().replace(hour=19, minute=30))
                            .isoformat()),
                    "is_estimated": True
                }
            
            # Calculate Shabbat start and end times
            shabbat_start = friday_sunset - timedelta(minutes=18)
            shabbat_end = saturday_sunset + timedelta(minutes=42)
            
            return {
                "date": date_obj.isoformat(),
                "start": shabbat_start.isoformat(),
                "end": shabbat_end.isoformat(),
                "friday_sunset": friday_sunset.isoformat(),
                "saturday_sunset": saturday_sunset.isoformat(),
                "is_estimated": False
            }
        except Exception as e:
            logger.error(f"Error calculating Shabbat times for {date_obj}: {e}")
            # Return approximate times in case of any error
            return {
                "date": date_obj.isoformat(),
                "start": (datetime.combine(date_obj, datetime.min.time().replace(hour=18, minute=0))
                        .isoformat()),
                "end": (datetime.combine(date_obj + timedelta(days=1), datetime.min.time().replace(hour=19, minute=30))
                        .isoformat()),
                "is_estimated": True
            }