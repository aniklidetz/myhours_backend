"""
Bulk persister for efficient database operations.

This module handles bulk saving of payroll results to the database using
Django's bulk_create and bulk_update operations.

Key features:
- Bulk insert/update for MonthlyPayrollSummary
- Bulk insert for DailyPayrollCalculation
- Bulk insert for CompensatoryDay
- Transaction safety
- Error handling and rollback
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Set

from django.db import transaction
from django.utils import timezone

from integrations.models import Holiday
from payroll.models import (
    CompensatoryDay,
    DailyPayrollCalculation,
    MonthlyPayrollSummary,
)
from payroll.services.contracts import CalculationContext, PayrollResult
from users.models import Employee
from worktime.models import WorkLog

from .types import BulkLoadedData, BulkSaveResult

logger = logging.getLogger(__name__)


class BulkPersister:
    """
    Bulk persister for efficient database operations.

    This class handles saving payroll calculation results to the database
    using bulk operations to minimize database round-trips.
    """

    def __init__(self, batch_size: int = 1000):
        """
        Initialize bulk persister.

        Args:
            batch_size: Size of batches for bulk operations
        """
        self.batch_size = batch_size

    def save_all(
        self,
        results: Dict[int, PayrollResult],
        contexts: Dict[int, CalculationContext],
        bulk_data: BulkLoadedData,
    ) -> BulkSaveResult:
        """
        Save all payroll results to database in bulk.

        This is the main entry point that coordinates all save operations.

        Args:
            results: Calculation results by employee_id
            contexts: Calculation contexts by employee_id
            bulk_data: Loaded data with work logs

        Returns:
            BulkSaveResult: Statistics about saved records
        """
        start_time = datetime.now()
        save_result = BulkSaveResult()

        logger.info(
            f"Starting bulk save for {len(results)} employees",
            extra={"employee_count": len(results), "action": "bulk_save_start"},
        )

        try:
            with transaction.atomic():
                # Save monthly summaries
                monthly_result = self._save_monthly_summaries(results, contexts)
                save_result.monthly_summaries_created = monthly_result["created"]
                save_result.monthly_summaries_updated = monthly_result["updated"]

                # Save daily calculations
                daily_result = self._save_daily_calculations(
                    results, contexts, bulk_data
                )
                save_result.daily_calculations_created = daily_result["created"]

                # Save compensatory days
                comp_result = self._save_compensatory_days(results, contexts, bulk_data)
                save_result.compensatory_days_created = comp_result["created"]

            save_result.duration_seconds = (datetime.now() - start_time).total_seconds()

            logger.info(
                f"Bulk save completed: {save_result.total_records} records in {save_result.duration_seconds:.2f}s",
                extra={
                    "total_records": save_result.total_records,
                    "monthly_summaries": save_result.monthly_summaries_created
                    + save_result.monthly_summaries_updated,
                    "daily_calculations": save_result.daily_calculations_created,
                    "compensatory_days": save_result.compensatory_days_created,
                    "duration_seconds": save_result.duration_seconds,
                    "action": "bulk_save_complete",
                },
            )

        except Exception as e:
            logger.error(
                f"Bulk save failed: {e}",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "action": "bulk_save_error",
                },
                exc_info=True,
            )
            save_result.errors.append({"type": "transaction_error", "message": str(e)})

        return save_result

    def _save_monthly_summaries(
        self, results: Dict[int, PayrollResult], contexts: Dict[int, CalculationContext]
    ) -> Dict[str, int]:
        """
        Save monthly payroll summaries using bulk operations.

        Uses update_or_create pattern: first identifies existing records,
        then bulk_update existing and bulk_create new ones.

        Args:
            results: Calculation results
            contexts: Calculation contexts

        Returns:
            Dict with 'created' and 'updated' counts
        """
        if not results:
            return {"created": 0, "updated": 0}

        # Get year/month from first context (all should be same period)
        first_context = next(iter(contexts.values()))
        year = first_context["year"]
        month = first_context["month"]

        # Get all existing summaries for this period
        existing_summaries = {
            summary.employee_id: summary
            for summary in MonthlyPayrollSummary.objects.filter(
                employee_id__in=results.keys(), year=year, month=month
            ).select_for_update()
        }

        summaries_to_update = []
        summaries_to_create = []

        for employee_id, result in results.items():
            context = contexts[employee_id]
            breakdown = result.get("breakdown", {})

            # Prepare summary data
            summary_data = {
                "total_gross_pay": result.get("total_salary", Decimal("0")),
                "total_hours": result.get("total_hours", Decimal("0")),
                "regular_hours": result.get("regular_hours", Decimal("0")),
                "overtime_hours": result.get("overtime_hours", Decimal("0")),
                "holiday_hours": result.get("holiday_hours", Decimal("0")),
                "sabbath_hours": result.get("shabbat_hours", Decimal("0")),
                "base_pay": Decimal(str(breakdown.get("regular_pay", 0))),
                "overtime_pay": (
                    Decimal(str(breakdown.get("overtime_125_pay", 0)))
                    + Decimal(str(breakdown.get("overtime_150_pay", 0)))
                ),
                "holiday_pay": Decimal(str(breakdown.get("holiday_pay", 0))),
                "sabbath_pay": (
                    Decimal(str(breakdown.get("sabbath_regular_pay", 0)))
                    + Decimal(str(breakdown.get("sabbath_overtime_175_pay", 0)))
                    + Decimal(str(breakdown.get("sabbath_overtime_200_pay", 0)))
                ),
                "proportional_monthly": Decimal(
                    str(breakdown.get("proportional_base", 0))
                ),
                "total_bonuses_monthly": Decimal(
                    str(breakdown.get("total_bonuses_monthly", 0))
                ),
                "worked_days": self._count_worked_days(employee_id, context, result),
            }

            if employee_id in existing_summaries:
                # Update existing
                summary = existing_summaries[employee_id]
                for field, value in summary_data.items():
                    setattr(summary, field, value)
                summaries_to_update.append(summary)
            else:
                # Create new
                summaries_to_create.append(
                    MonthlyPayrollSummary(
                        employee_id=employee_id, year=year, month=month, **summary_data
                    )
                )

        # Bulk operations
        created_count = 0
        updated_count = 0

        if summaries_to_create:
            MonthlyPayrollSummary.objects.bulk_create(
                summaries_to_create, batch_size=self.batch_size
            )
            created_count = len(summaries_to_create)

        if summaries_to_update:
            MonthlyPayrollSummary.objects.bulk_update(
                summaries_to_update,
                fields=[
                    "total_gross_pay",
                    "total_hours",
                    "regular_hours",
                    "overtime_hours",
                    "holiday_hours",
                    "sabbath_hours",
                    "base_pay",
                    "overtime_pay",
                    "holiday_pay",
                    "sabbath_pay",
                    "proportional_monthly",
                    "total_bonuses_monthly",
                    "worked_days",
                ],
                batch_size=self.batch_size,
            )
            updated_count = len(summaries_to_update)

        logger.info(
            f"Saved monthly summaries: {created_count} created, {updated_count} updated",
            extra={
                "created": created_count,
                "updated": updated_count,
                "action": "monthly_summaries_saved",
            },
        )

        return {"created": created_count, "updated": updated_count}

    def _save_daily_calculations(
        self,
        results: Dict[int, PayrollResult],
        contexts: Dict[int, CalculationContext],
        bulk_data: BulkLoadedData,
    ) -> Dict[str, int]:
        """
        Save daily payroll calculations using bulk operations.

        Deletes existing daily calculations for the period, then bulk creates new ones.

        Args:
            results: Calculation results
            contexts: Calculation contexts
            bulk_data: Loaded data with work logs and holidays

        Returns:
            Dict with 'created' count
        """
        if not results:
            return {"created": 0}

        # Get year/month from first context
        first_context = next(iter(contexts.values()))
        year = first_context["year"]
        month = first_context["month"]

        # Delete existing daily calculations for this period and employees
        deleted_count, _ = DailyPayrollCalculation.objects.filter(
            employee_id__in=results.keys(), work_date__year=year, work_date__month=month
        ).delete()

        if deleted_count > 0:
            logger.debug(f"Deleted {deleted_count} existing daily calculations")

        # Prepare daily calculations
        daily_calculations = []

        for employee_id, result in results.items():
            work_logs = bulk_data.get_work_logs(employee_id)

            if not work_logs:
                continue

            # Group work logs by date
            daily_logs = {}
            for log in work_logs:
                work_date = log.work_date
                if work_date not in daily_logs:
                    daily_logs[work_date] = []
                daily_logs[work_date].append(log)

            # Calculate total hours for proportional distribution
            total_hours = result.get("total_hours", Decimal("0"))
            if total_hours <= 0:
                continue

            total_salary = result.get("total_salary", Decimal("0"))
            regular_hours = result.get("regular_hours", Decimal("0"))

            # Create daily calculation for each day
            for work_date, logs in daily_logs.items():
                # Sum hours for this day
                daily_hours = sum(log.total_hours for log in logs)

                # Calculate proportional amounts
                proportion = (
                    daily_hours / total_hours if total_hours > 0 else Decimal("0")
                )

                # Check if holiday or sabbath
                holiday_data = bulk_data.holidays.get(work_date)
                is_holiday = holiday_data is not None
                is_sabbath = False  # Can check from Holiday model if needed

                holiday_name = holiday_data.name if holiday_data else ""

                daily_calculations.append(
                    DailyPayrollCalculation(
                        employee_id=employee_id,
                        work_date=work_date,
                        regular_hours=regular_hours * proportion,
                        total_gross_pay=total_salary * proportion,
                        is_holiday=is_holiday,
                        is_sabbath=is_sabbath,
                        holiday_name=holiday_name,
                        calculated_by_service="BulkEnhancedPayrollService",
                        worklog_id=logs[0].worklog_id if logs else None,
                    )
                )

        # Bulk create
        created_count = 0
        if daily_calculations:
            DailyPayrollCalculation.objects.bulk_create(
                daily_calculations, batch_size=self.batch_size
            )
            created_count = len(daily_calculations)

        logger.info(
            f"Created {created_count} daily calculations",
            extra={"created": created_count, "action": "daily_calculations_saved"},
        )

        return {"created": created_count}

    def _save_compensatory_days(
        self,
        results: Dict[int, PayrollResult],
        contexts: Dict[int, CalculationContext],
        bulk_data: BulkLoadedData,
    ) -> Dict[str, int]:
        """
        Save compensatory days for holiday/sabbath work.

        Args:
            results: Calculation results
            contexts: Calculation contexts
            bulk_data: Loaded data with work logs and holidays

        Returns:
            Dict with 'created' count
        """
        if not results:
            return {"created": 0}

        compensatory_days = []
        existing_comp_days: Set[tuple] = set()

        # Get existing compensatory days to avoid duplicates
        first_context = next(iter(contexts.values()))
        year = first_context["year"]
        month = first_context["month"]

        existing = CompensatoryDay.objects.filter(
            employee_id__in=results.keys(),
            date_earned__year=year,
            date_earned__month=month,
        ).values_list("employee_id", "date_earned", "reason")

        existing_comp_days = set(existing)

        # Create compensatory days for holiday/sabbath work
        for employee_id in results.keys():
            work_logs = bulk_data.get_work_logs(employee_id)

            for log in work_logs:
                work_date = log.work_date

                # Check if holiday
                holiday_data = bulk_data.holidays.get(work_date)
                if (
                    holiday_data
                    and (employee_id, work_date, "holiday") not in existing_comp_days
                ):
                    compensatory_days.append(
                        CompensatoryDay(
                            employee_id=employee_id,
                            date_earned=work_date,
                            reason="holiday",
                        )
                    )

                # Check if sabbath (would need to check Holiday model)
                # For now, simplified check based on day of week
                if (
                    work_date.weekday() == 5
                    and (employee_id, work_date, "sabbath") not in existing_comp_days
                ):  # Saturday
                    compensatory_days.append(
                        CompensatoryDay(
                            employee_id=employee_id,
                            date_earned=work_date,
                            reason="sabbath",
                        )
                    )

        # Bulk create
        created_count = 0
        if compensatory_days:
            CompensatoryDay.objects.bulk_create(
                compensatory_days,
                batch_size=self.batch_size,
                ignore_conflicts=True,  # Skip duplicates if any
            )
            created_count = len(compensatory_days)

        logger.info(
            f"Created {created_count} compensatory days",
            extra={"created": created_count, "action": "compensatory_days_saved"},
        )

        return {"created": created_count}

    def _count_worked_days(
        self, employee_id: int, context: CalculationContext, result: PayrollResult
    ) -> int:
        """
        Count unique days worked in the period.

        Args:
            employee_id: Employee ID
            context: Calculation context
            result: Calculation result

        Returns:
            int: Number of unique days worked
        """
        # Try to get from metadata
        work_log_count = result.get("metadata", {}).get("work_log_count", 0)

        # Rough estimate: assume 1 log per day
        # For more accuracy, would need to query WorkLog model
        return work_log_count if work_log_count > 0 else 0
