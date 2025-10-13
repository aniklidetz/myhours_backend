"""
Bulk data loader for optimized database queries.

This module handles efficient bulk loading of all data required for payroll
calculations, minimizing database queries through prefetch_related and
select_related optimizations.

Key optimizations:
- Single query for all employees with salary information
- Single query for all work logs in the period
- Single query for all holidays in the period
- Bulk API calls for Shabbat times
- Conversion to serializable data structures for multiprocessing
"""

import calendar
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Set

from django.db import models
from django.db.models import Prefetch

from integrations.models import Holiday
from integrations.services.unified_shabbat_service import get_shabbat_times
from payroll.models import Salary
from users.models import Employee
from worktime.models import WorkLog

from .types import (
    BulkLoadedData,
    EmployeeData,
    HolidayData,
    ShabbatTimesData,
    WorkLogData,
)

logger = logging.getLogger(__name__)


class BulkDataLoader:
    """
    Optimized bulk data loader for payroll calculations.

    This class handles efficient loading of all data required for bulk payroll
    calculations with minimal database queries.
    """

    def __init__(self):
        """Initialize the bulk data loader."""
        self._query_count = 0

    def load_all_data(
        self,
        employee_ids: List[int],
        year: int,
        month: int,
        include_shabbat_times: bool = True,
    ) -> BulkLoadedData:
        """
        Load all data required for bulk payroll calculations.

        This is the main entry point that coordinates all data loading operations.

        Args:
            employee_ids: List of employee IDs to load data for
            year: Year of the calculation period
            month: Month of the calculation period
            include_shabbat_times: Whether to load Shabbat times from API

        Returns:
            BulkLoadedData: Container with all loaded data
        """
        logger.info(
            f"Starting bulk data load for {len(employee_ids)} employees ({year}-{month})",
            extra={
                "employee_count": len(employee_ids),
                "year": year,
                "month": month,
                "action": "bulk_data_load_start",
            },
        )

        start_time = datetime.now()
        self._query_count = 0

        # Load all data with optimized queries
        employees_dict = self._load_employees(employee_ids)
        work_logs_dict = self._load_work_logs(employee_ids, year, month)
        holidays_dict = self._load_holidays(year, month)

        # Optionally load Shabbat times
        shabbat_times_dict = {}
        if include_shabbat_times:
            shabbat_times_dict = self._load_shabbat_times(year, month)

        duration = (datetime.now() - start_time).total_seconds()

        logger.info(
            f"Bulk data load completed in {duration:.2f}s with {self._query_count} DB queries",
            extra={
                "duration_seconds": duration,
                "db_queries": self._query_count,
                "employees_loaded": len(employees_dict),
                "work_logs_loaded": sum(len(logs) for logs in work_logs_dict.values()),
                "holidays_loaded": len(holidays_dict),
                "shabbat_times_loaded": len(shabbat_times_dict),
                "action": "bulk_data_load_complete",
            },
        )

        return BulkLoadedData(
            employees=employees_dict,
            work_logs=work_logs_dict,
            holidays=holidays_dict,
            shabbat_times=shabbat_times_dict,
            year=year,
            month=month,
        )

    def _load_employees(self, employee_ids: List[int]) -> Dict[int, EmployeeData]:
        """
        Load all employees with salary information in a single query.

        Uses prefetch_related to avoid N+1 queries for salaries.

        Args:
            employee_ids: List of employee IDs to load

        Returns:
            Dict mapping employee_id to EmployeeData
        """
        logger.debug(f"Loading {len(employee_ids)} employees with salaries")

        # Single optimized query with prefetch
        employees = (
            Employee.objects.filter(id__in=employee_ids)
            .select_related("user")
            .prefetch_related(
                Prefetch(
                    "salaries",
                    queryset=Salary.objects.filter(is_active=True),
                    to_attr="active_salaries",
                )
            )
        )

        self._query_count += 1  # Main query + 1 prefetch

        # Convert to serializable EmployeeData
        employees_dict = {}
        for emp in employees:
            # Get active salary
            active_salary = None
            if hasattr(emp, "active_salaries") and emp.active_salaries:
                active_salary = emp.active_salaries[0]

            if not active_salary:
                logger.warning(
                    f"Employee {emp.id} has no active salary configuration",
                    extra={"employee_id": emp.id, "action": "missing_salary"},
                )
                continue

            employees_dict[emp.id] = EmployeeData(
                employee_id=emp.id,
                user_id=emp.user_id if emp.user else 0,
                first_name=emp.first_name,
                last_name=emp.last_name,
                salary_id=active_salary.id,
                calculation_type=active_salary.calculation_type,
                hourly_rate=active_salary.hourly_rate,
                base_salary=active_salary.base_salary,
                is_active=emp.is_active,
            )

        logger.debug(f"Loaded {len(employees_dict)} employees successfully")
        return employees_dict

    def _load_work_logs(
        self, employee_ids: List[int], year: int, month: int
    ) -> Dict[int, List[WorkLogData]]:
        """
        Load all work logs for the period in a single query.

        Args:
            employee_ids: List of employee IDs
            year: Year of the period
            month: Month of the period

        Returns:
            Dict mapping employee_id to list of WorkLogData
        """
        logger.debug(
            f"Loading work logs for {len(employee_ids)} employees ({year}-{month})"
        )

        # Single optimized query for all work logs
        work_logs = (
            WorkLog.objects.filter(
                employee_id__in=employee_ids,
                check_in__year=year,
                check_in__month=month,
                check_out__isnull=False,
            )
            .select_related("employee")
            .order_by("employee_id", "check_in")
        )

        self._query_count += 1

        # Group by employee_id and convert to WorkLogData
        work_logs_dict: Dict[int, List[WorkLogData]] = {}
        for log in work_logs:
            if log.employee_id not in work_logs_dict:
                work_logs_dict[log.employee_id] = []

            work_logs_dict[log.employee_id].append(
                WorkLogData(
                    worklog_id=log.id,
                    employee_id=log.employee_id,
                    check_in=log.check_in,
                    check_out=log.check_out,
                    work_date=log.check_in.date(),
                )
            )

        total_logs = sum(len(logs) for logs in work_logs_dict.values())
        logger.debug(
            f"Loaded {total_logs} work logs for {len(work_logs_dict)} employees"
        )

        return work_logs_dict

    def _load_holidays(self, year: int, month: int) -> Dict[date, HolidayData]:
        """
        Load all holidays for the month in a single query.

        Args:
            year: Year of the period
            month: Month of the period

        Returns:
            Dict mapping date to HolidayData
        """
        logger.debug(f"Loading holidays for {year}-{month}")

        # Calculate month boundaries
        first_day = date(year, month, 1)
        last_day = date(year, month, calendar.monthrange(year, month)[1])

        # Single query for all holidays in the month
        holidays = Holiday.objects.filter(
            date__gte=first_day, date__lte=last_day, is_holiday=True
        ).values("date", "name")

        self._query_count += 1

        # Convert to HolidayData
        holidays_dict = {
            holiday["date"]: HolidayData(
                date=holiday["date"],
                name=holiday["name"],
                is_paid=True,  # Assume all holidays are paid
                source="database",
            )
            for holiday in holidays
        }

        logger.debug(f"Loaded {len(holidays_dict)} holidays")

        return holidays_dict

    def _load_shabbat_times(
        self, year: int, month: int
    ) -> Dict[date, ShabbatTimesData]:
        """
        Load Shabbat times for all Fridays in the month using bulk API calls.

        Args:
            year: Year of the period
            month: Month of the period

        Returns:
            Dict mapping Friday date to ShabbatTimesData
        """
        logger.debug(f"Loading Shabbat times for {year}-{month}")

        # Find all Fridays in the month
        first_day = date(year, month, 1)
        last_day = date(year, month, calendar.monthrange(year, month)[1])

        fridays = self._get_fridays_in_range(first_day, last_day)

        # Also include Friday before month start and after month end
        # (for shifts that cross month boundaries)
        if fridays:
            # Add previous Friday
            prev_friday = fridays[0] - timedelta(days=7)
            # Add next Friday
            next_friday = fridays[-1] + timedelta(days=7)
            fridays = [prev_friday] + fridays + [next_friday]

        shabbat_times_dict = {}

        # Load Shabbat times for each Friday
        for friday in fridays:
            try:
                shabbat_times = get_shabbat_times(friday)

                shabbat_times_dict[friday] = ShabbatTimesData(
                    friday_date=friday,
                    shabbat_start=datetime.fromisoformat(
                        shabbat_times["shabbat_start"].replace("Z", "+00:00")
                    ),
                    shabbat_end=datetime.fromisoformat(
                        shabbat_times["shabbat_end"].replace("Z", "+00:00")
                    ),
                    source="api",
                )
            except Exception as e:
                logger.warning(
                    f"Failed to load Shabbat times for {friday}: {e}",
                    extra={"friday_date": friday.isoformat(), "error": str(e)},
                )
                # Use fallback times (18:00 Friday - 19:00 Saturday)
                shabbat_times_dict[friday] = self._get_fallback_shabbat_times(friday)

        logger.debug(f"Loaded Shabbat times for {len(shabbat_times_dict)} Fridays")

        return shabbat_times_dict

    def _get_fridays_in_range(self, start_date: date, end_date: date) -> List[date]:
        """
        Get all Fridays in the date range.

        Args:
            start_date: Start of range
            end_date: End of range

        Returns:
            List of Friday dates
        """
        fridays = []
        current_date = start_date

        # Find first Friday
        while current_date.weekday() != 4:  # 4 = Friday
            current_date += timedelta(days=1)
            if current_date > end_date:
                return fridays

        # Collect all Fridays
        while current_date <= end_date:
            fridays.append(current_date)
            current_date += timedelta(days=7)

        return fridays

    def _get_fallback_shabbat_times(self, friday: date) -> ShabbatTimesData:
        """
        Generate fallback Shabbat times when API is unavailable.

        Uses conservative estimates: 18:00 Friday - 19:00 Saturday

        Args:
            friday: Friday date

        Returns:
            ShabbatTimesData with fallback times
        """
        import pytz

        tz = pytz.timezone("Asia/Jerusalem")

        # Shabbat start: Friday 18:00
        shabbat_start = datetime.combine(friday, datetime.min.time()).replace(
            hour=18, minute=0, second=0, microsecond=0, tzinfo=tz
        )

        # Shabbat end: Saturday 19:00
        saturday = friday + timedelta(days=1)
        shabbat_end = datetime.combine(saturday, datetime.min.time()).replace(
            hour=19, minute=0, second=0, microsecond=0, tzinfo=tz
        )

        return ShabbatTimesData(
            friday_date=friday,
            shabbat_start=shabbat_start,
            shabbat_end=shabbat_end,
            source="fallback",
        )

    @property
    def query_count(self) -> int:
        """Get the total number of database queries executed."""
        return self._query_count
