"""
Holiday Utility Service - Provides utility functions for holiday queries

This service is responsible for:
- Querying holiday information from the database
- Providing fallback lookups via API when needed
- Simple utility functions for holiday checking

It focuses solely on read operations and utility functions,
maintaining separation from sync operations and API communication.
"""

import logging
from datetime import datetime

from integrations.config.israeli_holidays import is_official_holiday
from integrations.models import Holiday
from integrations.services.hebcal_api_client import HebcalAPIClient

logger = logging.getLogger(__name__)


class HolidayUtilityService:
    """
    Service providing utility functions for holiday queries and checks.

    This service focuses on read operations and utility functions,
    separate from sync operations and API communication.
    """

    @classmethod
    def get_holiday_name(cls, holiday_date):
        """
        Get the name of a holiday for a specific date.

        Args:
            holiday_date (date): The date to check for holiday

        Returns:
            str or None: Holiday name if found, None otherwise
        """
        try:
            # Check database first (primary source)
            holiday = Holiday.objects.filter(
                date=holiday_date,
                is_holiday=True
            ).first()

            if holiday:
                return holiday.name

            # Fallback: check API data (use year-level cache for consistency)
            return cls._get_holiday_name_from_api(holiday_date)

        except Exception as e:
            from core.logging_utils import err_tag
            logger.error(
                "Error getting holiday name",
                extra={"err": err_tag(e), "date": str(holiday_date)},
            )
            return None

    @classmethod
    def is_holiday(cls, check_date):
        """
        Check if a specific date is a holiday.

        Args:
            check_date (date): The date to check

        Returns:
            bool: True if the date is a holiday, False otherwise
        """
        try:
            # Check database first (primary source)
            holiday_exists = Holiday.objects.filter(
                date=check_date,
                is_holiday=True
            ).exists()

            if holiday_exists:
                return True

            # Fallback: check API data (use year-level cache for consistency)
            return cls._is_holiday_from_api(check_date)

        except Exception as e:
            from core.logging_utils import err_tag
            logger.error(
                "Error checking if date is holiday",
                extra={"err": err_tag(e), "date": str(check_date)},
            )
            return False

    @classmethod
    def is_shabbat(cls, check_date):
        """
        Check if a specific date is a Shabbat.

        Args:
            check_date (date): The date to check

        Returns:
            bool: True if the date is a Shabbat, False otherwise
        """
        try:
            return Holiday.objects.filter(
                date=check_date,
                is_shabbat=True
            ).exists()

        except Exception as e:
            from core.logging_utils import err_tag
            logger.error(
                "Error checking if date is Shabbat",
                extra={"err": err_tag(e), "date": str(check_date)},
            )
            return False

    @classmethod
    def is_special_shabbat(cls, check_date):
        """
        Check if a specific date is a special Shabbat.

        Args:
            check_date (date): The date to check

        Returns:
            bool: True if the date is a special Shabbat, False otherwise
        """
        try:
            return Holiday.objects.filter(
                date=check_date,
                is_special_shabbat=True
            ).exists()

        except Exception as e:
            from core.logging_utils import err_tag
            logger.error(
                "Error checking if date is special Shabbat",
                extra={"err": err_tag(e), "date": str(check_date)},
            )
            return False

    @classmethod
    def get_holiday_info(cls, check_date):
        """
        Get comprehensive holiday information for a specific date.

        Args:
            check_date (date): The date to check

        Returns:
            dict: Holiday information including name, type, and times
        """
        try:
            holiday = Holiday.objects.filter(date=check_date).first()

            if not holiday:
                return {
                    "exists": False,
                    "name": None,
                    "is_holiday": False,
                    "is_shabbat": False,
                    "is_special_shabbat": False,
                    "start_time": None,
                    "end_time": None,
                }

            return {
                "exists": True,
                "name": holiday.name,
                "is_holiday": holiday.is_holiday,
                "is_shabbat": holiday.is_shabbat,
                "is_special_shabbat": holiday.is_special_shabbat,
                "start_time": holiday.start_time,
                "end_time": holiday.end_time,
            }

        except Exception as e:
            from core.logging_utils import err_tag
            logger.error(
                "Error getting holiday info",
                extra={"err": err_tag(e), "date": str(check_date)},
            )
            return {"exists": False, "name": None}

    @classmethod
    def _get_holiday_name_from_api(cls, holiday_date):
        """Fallback method to get holiday name from API."""
        year = holiday_date.year
        holidays = HebcalAPIClient.fetch_holidays(year, use_cache=True)

        for holiday_data in holidays:
            try:
                api_date = datetime.strptime(
                    holiday_data.get("date"), "%Y-%m-%d"
                ).date()

                if api_date == holiday_date:
                    title = holiday_data.get("title", "")
                    # Only return the name if it's an official holiday
                    if is_official_holiday(title):
                        return title

            except (ValueError, TypeError):
                continue

        return None

    @classmethod
    def get_holidays_in_range(cls, start_date, end_date):
        """
        Get all holidays in a date range.

        Args:
            start_date (date): Start of the range
            end_date (date): End of the range

        Returns:
            list: List of Holiday objects in the range
        """
        try:
            holidays = Holiday.objects.filter(
                date__gte=start_date,
                date__lte=end_date,
                is_holiday=True
            )
            return list(holidays)
        except Exception as e:
            logger.warning(f"Failed to get holidays in range {start_date} to {end_date}: {e}")
            return []

    @classmethod
    def _is_holiday_from_api(cls, check_date):
        """Fallback method to check if date is holiday via API."""
        year = check_date.year
        holidays = HebcalAPIClient.fetch_holidays(year, use_cache=True)

        for holiday_data in holidays:
            try:
                api_date = datetime.strptime(
                    holiday_data.get("date"), "%Y-%m-%d"
                ).date()

                if api_date == check_date:
                    # Check if this holiday requires premium pay
                    title = holiday_data.get("title", "")
                    return is_official_holiday(title)

            except (ValueError, TypeError):
                continue

        return False