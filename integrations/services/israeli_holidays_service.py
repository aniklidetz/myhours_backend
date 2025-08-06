"""
Service for handling Israeli national holidays that may not be in Hebcal API
"""

import logging
from datetime import date, datetime, timedelta
from integrations.models import Holiday
from django.utils import timezone

logger = logging.getLogger(__name__)


class IsraeliHolidaysService:
    """
    Handles Israeli national holidays like Independence Day that may not be in religious calendars
    """

    # Independence Day dates (5th of Iyar, but adjusted if falls on Friday/Saturday)
    INDEPENDENCE_DAY_DATES = {
        2024: date(2024, 5, 14),  # Tuesday (postponed from Monday)
        2025: date(2025, 5, 1),  # Thursday (postponed from Wednesday)
        2026: date(2026, 4, 23),  # Thursday (postponed from Tuesday)
        2027: date(2027, 5, 12),  # Wednesday
        2028: date(2028, 5, 2),  # Tuesday
    }

    @classmethod
    def sync_national_holidays(cls, year):
        """
        Sync Israeli national holidays for a given year

        Args:
            year (int): Year to sync

        Returns:
            tuple: (created_count, updated_count)
        """
        created_count = 0
        updated_count = 0

        # Add Independence Day if we have the date
        if year in cls.INDEPENDENCE_DAY_DATES:
            ind_date = cls.INDEPENDENCE_DAY_DATES[year]

            try:
                # Create datetime for start/end times
                start_time = timezone.make_aware(
                    datetime.combine(
                        ind_date - timedelta(days=1),
                        datetime.min.time().replace(hour=20),
                    )
                )
                end_time = timezone.make_aware(
                    datetime.combine(ind_date, datetime.min.time().replace(hour=20))
                )

                holiday, created = Holiday.objects.update_or_create(
                    date=ind_date,
                    defaults={
                        "name": "Yom HaAtzmaut (Independence Day)",
                        "is_holiday": True,  # Official holiday with premium pay
                        "is_shabbat": False,
                        "is_special_shabbat": False,
                        "start_time": start_time,
                        "end_time": end_time,
                    },
                )

                if created:
                    created_count += 1
                    logger.info(f"Created Independence Day for {year}")
                else:
                    updated_count += 1
                    logger.info(f"Updated Independence Day for {year}")

            except Exception as e:
                logger.error(f"Error syncing Independence Day for {year}: {e}")

        return created_count, updated_count

    @classmethod
    def ensure_independence_day(cls, year):
        """
        Ensure Independence Day exists for a given year
        Called after Hebcal sync to add missing national holidays
        """
        if year in cls.INDEPENDENCE_DAY_DATES:
            ind_date = cls.INDEPENDENCE_DAY_DATES[year]

            # Check if it already exists
            if not Holiday.objects.filter(
                date=ind_date, name__icontains="Atzmaut"
            ).exists():
                created, updated = cls.sync_national_holidays(year)
                if created > 0:
                    logger.info(f"Added missing Independence Day for {year}")
                    return True
        return False
