"""
Enhanced Redis Cache Service with Shabbat Times Integration

Combines holiday data with precise Shabbat times from sunrise-sunset API
"""

import json
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from integrations.services.enhanced_sunrise_sunset_service import (
    enhanced_sunrise_sunset_service,
)
from payroll.redis_cache_service import PayrollRedisCache

logger = logging.getLogger(__name__)


class EnhancedPayrollCache(PayrollRedisCache):
    """
    Enhanced version that includes precise Shabbat times from API
    """

    def get_holidays_with_shabbat_times(self, year: int, month: int) -> Dict[str, Dict]:
        """
        Get holidays with enhanced Shabbat timing data

        Combines:
        1. Holiday data from Redis/DB
        2. Precise Shabbat times from sunrise-sunset API
        """
        try:
            # Get basic holiday data
            holidays_dict = self.get_holidays_for_month(year, month)
        except Exception as e:
            logger.error(f"Error getting holidays for {year}-{month}: {e}")
            return {}

        # Enhance with precise Shabbat times
        for date_str, holiday_data in holidays_dict.items():
            if holiday_data.get("is_shabbat"):
                try:
                    work_date = date.fromisoformat(date_str)

                    # Get precise timing from enhanced sunrise-sunset service (Israeli timezone)
                    shabbat_times = enhanced_sunrise_sunset_service.get_shabbat_times_israeli_timezone(
                        work_date
                    )

                    if shabbat_times:
                        # Update with precise API data (Israeli timezone)
                        holiday_data.update(
                            {
                                "precise_start_time": shabbat_times.get(
                                    "shabbat_start"
                                ),
                                "precise_end_time": shabbat_times.get("shabbat_end"),
                                "friday_sunset": shabbat_times.get("friday_sunset"),
                                "saturday_sunset": shabbat_times.get("saturday_sunset"),
                                "timezone": shabbat_times.get(
                                    "timezone", "Asia/Jerusalem"
                                ),
                                "is_estimated": shabbat_times.get(
                                    "is_estimated", False
                                ),
                                "calculation_method": shabbat_times.get(
                                    "calculation_method", "api_precise"
                                ),
                            }
                        )

                        logger.debug(f"Enhanced Shabbat {date_str} with precise times")
                except Exception as e:
                    logger.error(f"Error enhancing Shabbat data for {date_str}: {e}")
                    # Continue processing other dates

        return holidays_dict

    def cache_shabbat_times_for_month(self, year: int, month: int):
        """
        Pre-cache all Shabbat times for the month using bulk API calls
        """
        cache_key = self._make_key("enhanced_holidays", year, month)

        if not self.cache_available:
            return

        try:
            # Get all Fridays in the month
            start_date = date(year, month, 1)
            if month == 12:
                end_date = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(year, month + 1, 1) - timedelta(days=1)

            fridays = []
            current_date = start_date
            while current_date <= end_date:
                if current_date.weekday() == 4:  # Friday
                    fridays.append(current_date)
                current_date += timedelta(days=1)

            # Bulk load Shabbat times for all Fridays using enhanced service
            enhanced_data = {}
            for friday in fridays:
                shabbat_times = (
                    enhanced_sunrise_sunset_service.get_shabbat_times_israeli_timezone(
                        friday
                    )
                )
                if shabbat_times:
                    # Also cache Saturday data
                    saturday_date = friday + timedelta(days=1)

                    # Friday data (Shabbat start)
                    enhanced_data[friday.isoformat()] = {
                        "name": "Erev Shabbat",
                        "is_shabbat": True,
                        "is_holiday": False,
                        "precise_start_time": shabbat_times.get("shabbat_start"),
                        "precise_end_time": shabbat_times.get("shabbat_end"),
                        "friday_sunset": shabbat_times.get("friday_sunset"),
                        "saturday_sunset": shabbat_times.get("saturday_sunset"),
                        "timezone": shabbat_times.get("timezone", "Asia/Jerusalem"),
                        "is_estimated": shabbat_times.get("is_estimated", False),
                        "calculation_method": shabbat_times.get(
                            "calculation_method", "api_precise"
                        ),
                    }

                    # Saturday data (Shabbat continues)
                    enhanced_data[saturday_date.isoformat()] = {
                        "name": "Shabbat",
                        "is_shabbat": True,
                        "is_holiday": False,
                        "precise_start_time": shabbat_times.get("shabbat_start"),
                        "precise_end_time": shabbat_times.get("shabbat_end"),
                        "friday_sunset": shabbat_times.get("friday_sunset"),
                        "saturday_sunset": shabbat_times.get("saturday_sunset"),
                        "timezone": shabbat_times.get("timezone", "Asia/Jerusalem"),
                        "is_estimated": shabbat_times.get("is_estimated", False),
                        "calculation_method": shabbat_times.get(
                            "calculation_method", "api_precise"
                        ),
                    }

            # Cache enhanced data for 1 week
            self.redis_client.setex(
                cache_key,
                7 * 24 * 60 * 60,  # 1 week
                json.dumps(enhanced_data, default=self._serialize_decimal),
            )

            logger.info(
                f"📅 Cached enhanced Shabbat times for {len(fridays)} Fridays in {year}-{month:02d}"
            )

        except Exception as e:
            logger.error(f"Error caching enhanced Shabbat times: {e}")

    def is_work_during_shabbat(self, work_start, work_end, work_date) -> Dict[str, Any]:
        """
        Check if work time overlaps with Shabbat using precise timing

        Returns:
            Dict with overlap info and rates to apply, including:
            - is_shabbat_work: bool
            - overlap_minutes: int (always present)
            - details: dict (always present)
        """
        from datetime import datetime

        # Get precise Shabbat times
        holidays = self.get_holidays_with_shabbat_times(work_date.year, work_date.month)
        date_str = work_date.isoformat()

        shabbat_data = holidays.get(date_str)
        if not shabbat_data or not shabbat_data.get("is_shabbat"):
            return {
                "is_shabbat_work": False,
                "overlap_minutes": 0,
                "details": {"not_shabbat_day": True},
            }

        precise_start = shabbat_data.get("precise_start_time")
        precise_end = shabbat_data.get("precise_end_time")

        # Fallback logic when no precise times available
        if not precise_start or not precise_end:
            # Use basic Shabbat detection - if it's marked as Shabbat, treat as Shabbat work
            return {
                "is_shabbat_work": True,
                "overlap_minutes": 0,  # Can't calculate precise overlap
                "shabbat_rate": 1.5,
                "precise_timing": False,
                "details": {"no_precise_times": True, "fallback_logic": True},
            }

        try:
            shabbat_start = datetime.fromisoformat(precise_start.replace("Z", "+00:00"))
            shabbat_end = datetime.fromisoformat(precise_end.replace("Z", "+00:00"))

            # Check for overlap
            overlap_start = max(work_start, shabbat_start)
            overlap_end = min(work_end, shabbat_end)

            if overlap_start < overlap_end:
                overlap_seconds = (overlap_end - overlap_start).total_seconds()
                overlap_minutes = int(overlap_seconds // 60)
                overlap_hours = overlap_seconds / 3600

                return {
                    "is_shabbat_work": True,
                    "overlap_minutes": overlap_minutes,
                    "overlap_hours": overlap_hours,  # Keep for backward compatibility
                    "shabbat_rate": 1.5,
                    "precise_timing": True,
                    "details": {
                        "work_during_shabbat": {
                            "shabbat_start": precise_start,
                            "shabbat_end": precise_end,
                            "work_start": work_start.isoformat(),
                            "work_end": work_end.isoformat(),
                            "overlap_start": overlap_start.isoformat(),
                            "overlap_end": overlap_end.isoformat(),
                        }
                    },
                }
            else:
                return {
                    "is_shabbat_work": False,
                    "overlap_minutes": 0,
                    "details": {"shabbat_day_no_overlap": True},
                }

        except Exception as e:
            logger.error(f"Error calculating Shabbat overlap: {e}")

        return {
            "is_shabbat_work": False,
            "overlap_minutes": 0,
            "details": {"calculation_error": True},
        }


# Enhanced cache instance
enhanced_payroll_cache = EnhancedPayrollCache()
