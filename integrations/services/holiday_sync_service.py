"""
Holiday Synchronization Service - Orchestrates the synchronization of all holiday data

This service is responsible for:
- Orchestrating the sync process between multiple holiday sources
- Managing database operations for holiday data
- Coordinating between API clients and database models
- Handling the business logic of holiday data merging

It uses:
- HebcalAPIClient for Jewish holiday data
- UnifiedShabbatService for Shabbat time calculations
- IsraeliHolidaysService for national holidays
"""

import logging
from datetime import date, datetime, timedelta

from django.utils import timezone

from integrations.config.israeli_holidays import is_official_holiday
from integrations.models import Holiday
from integrations.services.hebcal_api_client import HebcalAPIClient
from integrations.services.israeli_holidays_service import IsraeliHolidaysService
from integrations.services.unified_shabbat_service import get_shabbat_times

logger = logging.getLogger(__name__)


class HolidaySyncService:
    """
    Service that orchestrates the synchronization of holiday data from multiple sources.

    This service coordinates between:
    - Hebcal API (Jewish holidays and special Shabbats)
    - UnifiedShabbatService (weekly Shabbat times)
    - IsraeliHolidaysService (national holidays)

    And manages their storage in the Holiday model.
    """

    @classmethod
    def sync_year(cls, year=None, include_weekly_shabbats=True):
        """
        Synchronize all holiday data for a given year.

        Args:
            year (int, optional): Year to synchronize. Defaults to current year.
            include_weekly_shabbats (bool): Whether to include weekly Shabbats.

        Returns:
            tuple: (created_count, updated_count)
        """
        if year is None:
            year = date.today().year

        logger.info(f"Starting holiday synchronization for year {year}")

        # Fetch holiday data from Hebcal API
        holidays = HebcalAPIClient.fetch_holidays(year, use_cache=True)

        # Generate weekly Shabbats if requested
        weekly_shabbats = (
            cls._generate_weekly_shabbats(year) if include_weekly_shabbats else []
        )

        # Initialize counters
        created_count = 0
        updated_count = 0

        # Sync different types of holidays
        special_created, special_updated = cls._sync_special_shabbats(holidays)
        other_created, other_updated = cls._sync_other_holidays(holidays)
        weekly_created, weekly_updated = cls._sync_weekly_shabbats(weekly_shabbats)

        # Sync Israeli national holidays
        national_created, national_updated = cls._sync_national_holidays(year)

        # Aggregate results
        total_created = special_created + other_created + weekly_created + national_created
        total_updated = special_updated + other_updated + weekly_updated + national_updated

        logger.info(
            f"Holiday sync completed for {year}: "
            f"created={total_created}, updated={total_updated}"
        )

        return total_created, total_updated

    @classmethod
    def _generate_weekly_shabbats(cls, year):
        """Generate weekly Shabbat data for the year using UnifiedShabbatService."""
        shabbats = []
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)

        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() == 4:  # Friday
                try:
                    shabbat_times = get_shabbat_times(current_date)
                    shabbats.append({
                        "title": "Shabbat",
                        "date": current_date.isoformat(),
                        "category": "holiday",
                        "subcat": "shabbat",
                        "start_time": shabbat_times["shabbat_start"],
                        "end_time": shabbat_times["shabbat_end"],
                    })
                except Exception as e:
                    from core.logging_utils import err_tag
                    logger.error(
                        "Error generating Shabbat",
                        extra={"err": err_tag(e), "date": str(current_date)},
                    )

            current_date += timedelta(days=1)

        return shabbats

    @classmethod
    def _sync_special_shabbats(cls, holidays):
        """Sync special Shabbats (e.g., Shabbat Chanukah, Shabbat Rosh Chodesh)."""
        created_count = 0
        updated_count = 0

        special_shabbats = [
            holiday for holiday in holidays
            if holiday.get("category") == "holiday"
            and holiday.get("subcat") == "shabbat"
        ]

        for holiday_data in special_shabbats:
            try:
                title = holiday_data.get("title")
                holiday_date_str = holiday_data.get("date")
                holiday_date = datetime.strptime(holiday_date_str, "%Y-%m-%d").date()

                defaults = {
                    "name": title,
                    "is_holiday": False,
                    "is_shabbat": True,
                    "is_special_shabbat": True,
                }

                holiday, created = Holiday.objects.get_or_create(
                    date=holiday_date,
                    defaults=defaults
                )

                if created:
                    created_count += 1
                    logger.debug(f"Created special Shabbat: {title} on {holiday_date}")
                else:
                    # Update existing record if it's different
                    updated = cls._update_holiday_if_changed(holiday, defaults)
                    if updated:
                        updated_count += 1
                        logger.debug(f"Updated special Shabbat: {title} on {holiday_date}")

            except Exception as e:
                from core.logging_utils import err_tag
                logger.error(
                    "Error syncing special Shabbat",
                    extra={"err": err_tag(e), "holiday": holiday_data}
                )

        return created_count, updated_count

    @classmethod
    def _sync_other_holidays(cls, holidays):
        """Sync regular Jewish holidays (major, minor, modern)."""
        created_count = 0
        updated_count = 0

        other_holidays = [
            holiday for holiday in holidays
            if holiday.get("category") == "holiday"
            and holiday.get("subcat") in ["major", "minor", "modern"]
            and holiday.get("subcat") != "shabbat"
        ]

        for holiday_data in other_holidays:
            try:
                title = holiday_data.get("title")
                holiday_date_str = holiday_data.get("date")
                holiday_date = datetime.strptime(holiday_date_str, "%Y-%m-%d").date()

                # Check if this is an official holiday requiring premium pay
                requires_premium_pay = is_official_holiday(title)

                defaults = {
                    "name": title,
                    "is_holiday": requires_premium_pay,
                    "is_shabbat": False,
                    "is_special_shabbat": False,
                }

                holiday, created = Holiday.objects.get_or_create(
                    date=holiday_date,
                    defaults=defaults
                )

                if created:
                    created_count += 1
                    logger.debug(f"Created holiday: {title} on {holiday_date}")
                else:
                    # Update existing record if it's different
                    updated = cls._update_holiday_if_changed(holiday, defaults)
                    if updated:
                        updated_count += 1
                        logger.debug(f"Updated holiday: {title} on {holiday_date}")

            except Exception as e:
                from core.logging_utils import err_tag
                logger.error(
                    "Error syncing holiday",
                    extra={"err": err_tag(e), "holiday": holiday_data}
                )

        return created_count, updated_count

    @classmethod
    def _sync_weekly_shabbats(cls, weekly_shabbats):
        """Sync regular weekly Shabbats."""
        created_count = 0
        updated_count = 0

        for shabbat_data in weekly_shabbats:
            try:
                holiday_date_str = shabbat_data.get("date")
                holiday_date = datetime.strptime(holiday_date_str, "%Y-%m-%d").date()

                defaults = {
                    "name": "Shabbat",
                    "is_holiday": False,
                    "is_shabbat": True,
                    "is_special_shabbat": False,
                    "start_time": (
                        datetime.fromisoformat(shabbat_data["start_time"])
                        if shabbat_data.get("start_time")
                        else None
                    ),
                    "end_time": (
                        datetime.fromisoformat(shabbat_data["end_time"])
                        if shabbat_data.get("end_time")
                        else None
                    ),
                }

                try:
                    holiday = Holiday.objects.get(date=holiday_date)
                    # Only update if it's still a regular Shabbat (preserve special/holiday status)
                    if not holiday.is_special_shabbat and not holiday.is_holiday:
                        updated = cls._update_holiday_if_changed(holiday, defaults)
                        if updated:
                            updated_count += 1
                            logger.debug(f"Updated weekly Shabbat on {holiday_date}")

                except Holiday.DoesNotExist:
                    # Create new weekly Shabbat
                    Holiday.objects.create(date=holiday_date, **defaults)
                    created_count += 1
                    logger.debug(f"Created weekly Shabbat on {holiday_date}")

            except Exception as e:
                from core.logging_utils import err_tag
                logger.error(
                    "Error syncing weekly Shabbat",
                    extra={"err": err_tag(e), "date": shabbat_data.get("date")}
                )

        return created_count, updated_count

    @classmethod
    def _sync_national_holidays(cls, year):
        """Sync Israeli national holidays using IsraeliHolidaysService."""
        try:
            return IsraeliHolidaysService.sync_national_holidays(year)
        except Exception as e:
            from core.logging_utils import err_tag
            logger.error(
                "Error syncing Israeli national holidays",
                extra={"err": err_tag(e), "year": year}
            )
            return 0, 0

    @classmethod
    def _update_holiday_if_changed(cls, holiday, defaults):
        """
        Update holiday object if any of the default values have changed.

        Args:
            holiday: Holiday object to update
            defaults: Dictionary of field values to check/update

        Returns:
            bool: True if holiday was updated, False otherwise
        """
        changed = False
        update_fields = []

        for field, value in defaults.items():
            if getattr(holiday, field) != value:
                setattr(holiday, field, value)
                update_fields.append(field)
                changed = True

        if changed:
            holiday.save(update_fields=update_fields)

        return changed