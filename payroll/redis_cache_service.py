"""
Redis Cache Service for Payroll Optimization

Provides caching for:
1. Holidays and Sabbaths by date ranges
2. Daily payroll calculations
3. Monthly payroll summaries
4. Bulk holiday lookups to eliminate N+1 queries
"""

import json
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

try:
    import redis

    from django.conf import settings

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from integrations.models import Holiday
from integrations.services.enhanced_sunrise_sunset_service import (
    enhanced_sunrise_sunset_service,
)

logger = logging.getLogger(__name__)


class PayrollRedisCache:
    """
    Redis cache service specifically for payroll calculations
    """

    def __init__(self):
        self.redis_client = None
        self.cache_available = False

        if REDIS_AVAILABLE:
            try:
                # Try to get Redis configuration from Django settings
                redis_config = getattr(
                    settings,
                    "REDIS_CONFIG",
                    {
                        "host": "localhost",
                        "port": 6379,
                        "db": 0,
                        "decode_responses": True,
                    },
                )

                self.redis_client = redis.Redis(**redis_config)
                # Test connection
                self.redis_client.ping()
                self.cache_available = True
                logger.info("✅ Redis cache initialized successfully")

            except Exception as e:
                logger.warning(f"⚠️ Redis not available: {e}. Using database fallback.")
                self.cache_available = False
        else:
            logger.warning("⚠️ Redis package not installed. Using database fallback.")

    def _make_key(self, prefix: str, *args) -> str:
        """Generate cache key"""
        key_parts = [prefix] + [str(arg) for arg in args]
        return ":".join(key_parts)

    def _serialize_decimal(self, obj):
        """Custom JSON serializer for Decimal objects"""
        if isinstance(obj, Decimal):
            return float(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    # HOLIDAY CACHING METHODS

    def get_holidays_for_month(self, year: int, month: int) -> Dict[str, Dict]:
        """
        Get all holidays for a specific month from cache

        Returns:
            Dict[date_string, holiday_data]
        """
        if not self.cache_available:
            return self._get_holidays_from_db(year, month)

        cache_key = self._make_key("holidays", year, month)

        try:
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                holidays_dict = json.loads(cached_data)
                logger.debug(
                    f"📋 Cache HIT: holidays for {year}-{month:02d} ({len(holidays_dict)} holidays)"
                )
                return holidays_dict
        except Exception as e:
            logger.warning(f"Redis get error for holidays: {e}")

        # Cache miss - get from database and cache
        holidays_dict = self._get_holidays_from_db(year, month)
        self.cache_holidays_for_month(year, month, holidays_dict)

        logger.debug(f"📋 Cache MISS: holidays for {year}-{month:02d} loaded from DB")
        return holidays_dict

    def _get_holidays_from_db(self, year: int, month: int) -> Dict[str, Dict]:
        """Get holidays from database with enhanced Shabbat times"""
        holidays = Holiday.objects.filter(date__year=year, date__month=month)

        holidays_dict = {}
        for holiday in holidays:
            date_str = holiday.date.isoformat()
            holiday_data = {
                "name": holiday.name,
                "is_holiday": holiday.is_holiday,
                "is_shabbat": holiday.is_shabbat,
                "is_special_shabbat": holiday.is_special_shabbat,
                "start_time": (
                    holiday.start_time.isoformat() if holiday.start_time else None
                ),
                "end_time": holiday.end_time.isoformat() if holiday.end_time else None,
            }

            # ✅ NEW: Enhance Shabbat entries with precise API times
            if holiday.is_shabbat:
                try:
                    shabbat_times = enhanced_sunrise_sunset_service.get_shabbat_times_israeli_timezone(
                        holiday.date, use_cache=True
                    )

                    if shabbat_times:
                        holiday_data.update(
                            {
                                "precise_start_time": shabbat_times.get(
                                    "shabbat_start"
                                ),
                                "precise_end_time": shabbat_times.get("shabbat_end"),
                                "friday_sunset": shabbat_times.get("friday_sunset"),
                                "saturday_sunset": shabbat_times.get("saturday_sunset"),
                                "timezone": "Asia/Jerusalem",
                                "is_estimated": shabbat_times.get(
                                    "is_estimated", False
                                ),
                                "api_enhanced": True,
                            }
                        )
                        logger.debug(
                            f"Enhanced Shabbat {date_str} with precise API times"
                        )
                    else:
                        holiday_data["api_enhanced"] = False

                except Exception as e:
                    logger.warning(
                        f"Failed to enhance Shabbat {date_str} with API times: {e}"
                    )
                    holiday_data["api_enhanced"] = False

            holidays_dict[date_str] = holiday_data

        return holidays_dict

    def cache_holidays_for_month(
        self, year: int, month: int, holidays_dict: Dict[str, Dict]
    ):
        """Cache holidays for a month"""
        if not self.cache_available:
            return

        cache_key = self._make_key("holidays", year, month)

        try:
            # Cache for 1 week (holidays don't change often)
            self.redis_client.setex(
                cache_key,
                7 * 24 * 60 * 60,  # 1 week in seconds
                json.dumps(holidays_dict),
            )
            logger.debug(f"📋 Cached holidays for {year}-{month:02d}")
        except Exception as e:
            logger.warning(f"Redis set error for holidays: {e}")

    def get_holiday_for_date(self, target_date: date) -> Optional[Dict]:
        """
        Get holiday data for a specific date

        Returns:
            Holiday dict or None
        """
        holidays_dict = self.get_holidays_for_month(target_date.year, target_date.month)
        date_str = target_date.isoformat()
        return holidays_dict.get(date_str)

    # BULK HOLIDAY LOADING

    def get_holidays_for_date_range(
        self, start_date: date, end_date: date
    ) -> Dict[str, Dict]:
        """
        Get all holidays for a date range efficiently

        This prevents N+1 queries by loading all needed holidays at once
        """
        holidays_dict = {}

        # Get unique months in the date range
        current_date = start_date.replace(day=1)  # Start of month

        while current_date <= end_date:
            month_holidays = self.get_holidays_for_month(
                current_date.year, current_date.month
            )
            holidays_dict.update(month_holidays)

            # Move to next month
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)

        # Filter to only dates within range
        filtered_holidays = {}
        for date_str, holiday_data in holidays_dict.items():
            holiday_date = date.fromisoformat(date_str)
            if start_date <= holiday_date <= end_date:
                filtered_holidays[date_str] = holiday_data

        logger.info(
            f"📋 Loaded {len(filtered_holidays)} holidays for range {start_date} to {end_date}"
        )
        return filtered_holidays

    # DAILY PAYROLL CALCULATION CACHING

    def get_daily_calculation(
        self, employee_id: int, work_date: date
    ) -> Optional[Dict]:
        """Get cached daily payroll calculation"""
        if not self.cache_available:
            return None

        cache_key = self._make_key("daily_calc", employee_id, work_date.isoformat())

        try:
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Redis get error for daily calculation: {e}")

        return None

    def cache_daily_calculation(
        self, employee_id: int, work_date: date, calculation_data: Dict
    ):
        """Cache daily payroll calculation"""
        if not self.cache_available:
            return

        cache_key = self._make_key("daily_calc", employee_id, work_date.isoformat())

        try:
            # Cache for 24 hours (daily calculations can change with new work logs)
            self.redis_client.setex(
                cache_key,
                24 * 60 * 60,  # 24 hours
                json.dumps(calculation_data, default=self._serialize_decimal),
            )
        except Exception as e:
            logger.warning(f"Redis set error for daily calculation: {e}")

    # MONTHLY PAYROLL SUMMARY CACHING

    def get_monthly_summary(
        self, employee_id: int, year: int, month: int
    ) -> Optional[Dict]:
        """Get cached monthly payroll summary"""
        if not self.cache_available:
            return None

        cache_key = self._make_key("monthly_summary", employee_id, year, month)

        try:
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                import hashlib
                def _short_hash(v): return hashlib.sha256(str(v).encode("utf-8")).hexdigest()[:8]
                logger.debug(
                    "📊 Cache HIT: monthly summary",
                    extra={"employee": _short_hash(employee_id), "period": f"{year}-{month:02d}"}
                )
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Redis get error for monthly summary: {e}")

        return None

    def cache_monthly_summary(
        self, employee_id: int, year: int, month: int, summary_data: Dict
    ):
        """Cache monthly payroll summary"""
        if not self.cache_available:
            return

        cache_key = self._make_key("monthly_summary", employee_id, year, month)

        try:
            # Cache for 1 hour (monthly summaries can change during the month)
            self.redis_client.setex(
                cache_key,
                60 * 60,  # 1 hour
                json.dumps(summary_data, default=self._serialize_decimal),
            )
            import hashlib
            def _short_hash(v): return hashlib.sha256(str(v).encode("utf-8")).hexdigest()[:8]
            logger.debug(
                "📊 Cached monthly summary",
                extra={"employee": _short_hash(employee_id), "period": f"{year}-{month:02d}"}
            )
        except Exception as e:
            logger.warning(f"Redis set error for monthly summary: {e}")

    # CACHE INVALIDATION

    def invalidate_employee_cache(self, employee_id: int, year: int, month: int):
        """Invalidate all cache for an employee's month"""
        if not self.cache_available:
            return

        patterns = [
            self._make_key("daily_calc", employee_id, "*"),
            self._make_key("monthly_summary", employee_id, year, month),
        ]

        try:
            for pattern in patterns:
                keys = self.redis_client.keys(pattern)
                if keys:
                    self.redis_client.delete(*keys)
                    import hashlib
                    pattern_hash = hashlib.sha256(str(pattern).encode("utf-8")).hexdigest()[:8]
                    logger.info(
                        "🗑️ Invalidated cache keys",
                        extra={"pattern_hash": pattern_hash, "count": len(keys)}
                    )
        except Exception as e:
            logger.warning(f"Cache invalidation error: {e}")

    def invalidate_holidays_cache(self, year: int, month: int):
        """Invalidate holiday cache for a specific month"""
        if not self.cache_available:
            return

        cache_key = self._make_key("holidays", year, month)

        try:
            self.redis_client.delete(cache_key)
            logger.info(f"🗑️ Invalidated holidays cache for {year}-{month:02d}")
        except Exception as e:
            logger.warning(f"Holiday cache invalidation error: {e}")

    # UTILITY METHODS

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if not self.cache_available:
            return {"status": "unavailable", "redis_available": False}

        try:
            info = self.redis_client.info()
            return {
                "status": "available",
                "redis_available": True,
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


# Global cache instance
payroll_cache = PayrollRedisCache()
