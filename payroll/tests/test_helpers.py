"""
Test helpers for payroll tests
"""
from datetime import date, datetime, timedelta
import pytz
from integrations.models import Holiday

def create_shabbat_for_date(saturday_date):
    """
    Create proper Shabbat records for a given Saturday date.

    Creates both Friday evening and Saturday portions with correct times.

    Args:
        saturday_date (date): The Saturday date

    Returns:
        tuple: (friday_holiday, saturday_holiday)
    """
    israel_tz = pytz.timezone("Asia/Jerusalem")
    friday_date = saturday_date - timedelta(days=1)

    # Use approximate times for tests (19:30 start, 20:30 end)
    # Friday evening portion
    friday_start = israel_tz.localize(datetime(friday_date.year, friday_date.month, friday_date.day, 19, 30))
    friday_end = israel_tz.localize(datetime(saturday_date.year, saturday_date.month, saturday_date.day, 0, 0))

    friday_holiday, created = Holiday.objects.get_or_create(
        date=friday_date,
        name="Shabbat",
        defaults={
            'is_shabbat': True,
            'start_time': friday_start,
            'end_time': friday_end
        }
    )

    # Saturday portion
    saturday_start = israel_tz.localize(datetime(saturday_date.year, saturday_date.month, saturday_date.day, 0, 0))
    saturday_end = israel_tz.localize(datetime(saturday_date.year, saturday_date.month, saturday_date.day, 20, 30))

    saturday_holiday, created = Holiday.objects.get_or_create(
        date=saturday_date,
        name="Shabbat",
        defaults={
            'is_shabbat': True,
            'start_time': saturday_start,
            'end_time': saturday_end
        }
    )

    return friday_holiday, saturday_holiday


def create_shabbats_for_month(year, month):
    """
    Create Shabbat records for all Saturdays in a given month.

    Args:
        year (int): Year
        month (int): Month

    Returns:
        list: List of created Saturday holiday records
    """
    saturday_holidays = []

    # Find all Saturdays in the month
    for day in range(1, 32):
        try:
            test_date = date(year, month, day)
            if test_date.weekday() == 5:  # Saturday
                friday_holiday, saturday_holiday = create_shabbat_for_date(test_date)
                saturday_holidays.append(saturday_holiday)
        except ValueError:
            # Invalid date (e.g., Feb 30)
            break

    return saturday_holidays