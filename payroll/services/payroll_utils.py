"""
Payroll utility functions for calculating working days and worked days.

This module extracts business logic from the Salary model to follow
the Service Layer pattern and avoid Fat Model anti-pattern.
"""

import calendar
import logging
from datetime import date, timedelta
from typing import Optional

import pytz

from django.utils import timezone

logger = logging.getLogger(__name__)


class PayrollUtils:
    """Utility methods for payroll calculations"""

    @staticmethod
    def get_working_days_in_month(year: int, month: int) -> int:
        """
        Calculate the number of working days in a month (excluding Shabbat and holidays)
        Updated for 5-day work week (Sunday-Thursday in Israel)

        OPTIMIZED: Single query instead of N queries (was 30+ queries, now 1)
        Uses Israeli timezone for date calculations

        Args:
            year: Year (YYYY)
            month: Month number (1-12)

        Returns:
            Number of working days in the month
        """
        try:
            from payroll.redis_cache_service import payroll_cache

            israel_tz = pytz.timezone("Asia/Jerusalem")

            # OPTIMIZED: Get ALL holidays for month at once (single query)
            holidays_dict = payroll_cache.get_holidays_for_month(year, month)

            # Build set of holiday dates for O(1) lookup
            holiday_dates = {
                date.fromisoformat(date_str)
                for date_str, data in holidays_dict.items()
                if data.get("is_holiday", False)
            }

            _, num_days = calendar.monthrange(year, month)
            working_days = 0

            # Count working days (weekdays that are not holidays)
            for day in range(1, num_days + 1):
                # Use Israeli timezone for date creation
                current_date = timezone.datetime(
                    year, month, day, tzinfo=israel_tz
                ).date()

                # Check if it's Shabbat (Saturday - 5 in Python) or Sunday (6)
                if current_date.weekday() in [5, 6]:  # Saturday or Sunday
                    continue

                # OPTIMIZED: Check holiday using set (O(1)) - no database query
                if current_date in holiday_dates:
                    continue

                working_days += 1

            logger.info(
                f"Working days in {year}-{month:02d}: {working_days}",
                extra={
                    "year": year,
                    "month": month,
                    "working_days": working_days,
                    "holidays_count": len(holiday_dates),
                    "optimized": True,
                },
            )
            return working_days

        except Exception as e:
            from core.logging_utils import err_tag

            logger.error(
                "Error calculating working days",
                extra={"err": err_tag(e), "year": year, "month": month},
            )
            # Fallback: approximate working days for 5-day week
            _, num_days = calendar.monthrange(year, month)
            return max(1, int(num_days * 5 / 7))  # Approximate 5-day work week

    @staticmethod
    def get_worked_days_for_employee(employee_id: int, year: int, month: int) -> int:
        """
        Calculate the actual worked days for an employee in a given month

        OPTIMIZED: Uses values() to fetch only date fields instead of full objects

        Args:
            employee_id: Employee ID
            year: Year (YYYY)
            month: Month number (1-12)

        Returns:
            Number of days the employee actually worked
        """
        try:
            from worktime.models import WorkLog

            # Calculate exact month boundaries
            start_date = date(year, month, 1)
            _, last_day = calendar.monthrange(year, month)
            end_date = date(year, month, last_day)

            # OPTIMIZED: Use values() to fetch only the date fields we need
            # This avoids loading full WorkLog objects with all related data
            work_logs = WorkLog.objects.filter(
                employee_id=employee_id,
                check_in__date__lte=end_date,
                check_out__date__gte=start_date,
                check_out__isnull=False,
            ).values("check_in__date", "check_out__date")

            work_logs_count = len(work_logs)
            logger.info(
                f"Found {work_logs_count} work logs for employee {employee_id} in {year}-{month:02d}"
            )

            if not work_logs_count:
                logger.info(
                    f"No work logs found for employee {employee_id} in {year}-{month:02d}"
                )
                return 0

            # Build set of unique worked dates
            worked_days = set()
            for log in work_logs:
                # Count days where work was performed within the month
                work_start = max(log["check_in__date"], start_date)
                work_end = min(log["check_out__date"], end_date)

                current_date = work_start
                while current_date <= work_end:
                    worked_days.add(current_date)
                    current_date += timedelta(days=1)

            worked_days_count = len(worked_days)
            logger.info(
                f"Worked days for employee {employee_id} in {year}-{month:02d}: {worked_days_count}"
            )
            return worked_days_count

        except Exception as e:
            logger.error(
                f"Error calculating worked days for employee {employee_id} in {year}-{month:02d}: {e}"
            )
            # Fallback: count unique work session dates
            try:
                from worktime.models import WorkLog

                start_date = date(year, month, 1)
                _, last_day = calendar.monthrange(year, month)
                end_date = date(year, month, last_day)

                # Use values() in fallback as well
                work_logs = WorkLog.objects.filter(
                    employee_id=employee_id,
                    check_in__year=year,
                    check_in__month=month,
                    check_out__isnull=False,
                ).values("check_in__date")

                unique_dates = set()
                for log in work_logs:
                    check_in_date = log["check_in__date"]
                    if start_date <= check_in_date <= end_date:
                        unique_dates.add(check_in_date)

                return len(unique_dates)
            except Exception as fallback_error:
                logger.error(f"Fallback calculation also failed: {fallback_error}")
                return 0


# Convenience functions for backward compatibility
def get_working_days_in_month(year: int, month: int) -> int:
    """
    Calculate working days in a month.
    Convenience function that calls PayrollUtils.get_working_days_in_month()
    """
    return PayrollUtils.get_working_days_in_month(year, month)


def get_worked_days_for_employee(employee_id: int, year: int, month: int) -> int:
    """
    Calculate worked days for an employee in a month.
    Convenience function that calls PayrollUtils.get_worked_days_for_employee()
    """
    return PayrollUtils.get_worked_days_for_employee(employee_id, year, month)
