"""
Main payroll calculation orchestrator service.

This module provides the main PayrollService class that acts as the primary
interface for all payroll calculations, managing strategy selection,
error handling, caching, and comprehensive logging.
"""

import logging
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

from integrations.models import Holiday
from payroll.models import (
    CompensatoryDay,
    DailyPayrollCalculation,
    MonthlyPayrollSummary,
)
from users.models import Employee
from worktime.models import WorkLog

from .bulk import BulkEnhancedPayrollService
from .contracts import CalculationContext, PayrollResult, create_empty_payroll_result
from .enums import CacheSource, CalculationStrategy, PayrollStatus
from .factory import StrategyNotFoundError, get_payroll_factory

logger = logging.getLogger(__name__)


class PayrollService:
    """
    Main orchestrator for payroll calculations.

    This service provides a unified interface for all payroll calculations,
    handling strategy selection, error recovery, performance monitoring,
    and result validation.
    """

    def __init__(self, enable_fallback: bool = True, enable_caching: bool = True):
        """
        Initialize the payroll service.

        Args:
            enable_fallback: Whether to use fallback strategies on failures
            enable_caching: Whether to use cached results when available
        """
        self.factory = get_payroll_factory()
        self.enable_fallback = enable_fallback
        self.enable_caching = enable_caching

    def calculate(
        self,
        context: CalculationContext,
        strategy: Optional[CalculationStrategy] = None,
    ) -> PayrollResult:
        """
        Calculate payroll using the specified or default strategy.

        This is the main entry point for all payroll calculations. It handles:
        - Strategy selection and fallback
        - Performance monitoring
        - Error handling and recovery
        - Result validation
        - Comprehensive logging

        Args:
            context: Complete calculation context
            strategy: Preferred calculation strategy (optional)

        Returns:
            PayrollResult: Standardized payroll calculation result
        """
        start_time = time.time()
        strategy = strategy or CalculationStrategy.get_default()

        self._log_calculation_request(context, strategy)

        try:
            # Check for cached results if caching is enabled
            if self.enable_caching:
                cached_result = self._check_cache(context)
                if cached_result:
                    self._log_cache_hit(context, strategy, time.time() - start_time)
                    return cached_result

            # Perform the calculation
            result = self._execute_calculation(context, strategy, start_time)

            # Validate the result
            self._validate_result(result, context, strategy)

            # Persist the result if not in fast mode
            if not context.get("fast_mode", False):
                work_logs = self._get_work_logs_for_context(context)
                self._persist_results(context, result, work_logs)

            # Cache the result if caching is enabled
            if self.enable_caching:
                self._cache_result(context, result)

            return result

        except Exception as e:
            return self._handle_calculation_error(e, context, strategy, start_time)

    def calculate_bulk(
        self,
        contexts: list[CalculationContext],
        strategy: Optional[CalculationStrategy] = None,
    ) -> Dict[int, PayrollResult]:
        """
        Calculate payroll for multiple employees efficiently.

        Args:
            contexts: List of calculation contexts
            strategy: Preferred calculation strategy for all calculations

        Returns:
            Dict[int, PayrollResult]: Results keyed by employee_id
        """
        start_time = time.time()
        strategy = strategy or CalculationStrategy.get_default()

        logger.info(
            f"Starting bulk payroll calculation for {len(contexts)} employees",
            extra={
                "employee_count": len(contexts),
                "strategy": strategy.value,
                "action": "bulk_calculation_start",
            },
        )

        results = {}
        successful_count = 0
        failed_count = 0

        for context in contexts:
            try:
                result = self.calculate(context, strategy)
                results[context["employee_id"]] = result
                successful_count += 1
            except Exception as e:
                logger.error(
                    f"Bulk calculation failed for employee {context['employee_id']}",
                    extra={
                        "employee_id": context["employee_id"],
                        "error": str(e),
                        "action": "bulk_calculation_employee_failed",
                    },
                )
                results[context["employee_id"]] = create_empty_payroll_result(
                    employee_id=context["employee_id"], strategy=strategy.value
                )
                failed_count += 1

        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            f"Bulk calculation completed: {successful_count} successful, {failed_count} failed",
            extra={
                "total_employees": len(contexts),
                "successful_count": successful_count,
                "failed_count": failed_count,
                "duration_ms": duration_ms,
                "strategy": strategy.value,
                "action": "bulk_calculation_completed",
            },
        )

        return results

    def calculate_bulk_optimized(
        self,
        employee_ids: List[int],
        year: int,
        month: int,
        strategy: Optional[CalculationStrategy] = None,
        use_parallel: bool = True,
        use_cache: bool = True,
        save_to_db: bool = True,
    ) -> Dict[int, PayrollResult]:
        """
        Calculate payroll for multiple employees using optimized bulk operations.

        This method uses BulkEnhancedPayrollService for high-performance calculations:
        - Optimized data loading (3-5 queries instead of N*100+)
        - Parallel processing with multiprocessing
        - Redis cache with pipeline operations
        - Bulk database persistence

        For small batches (<10 employees), the regular calculate_bulk may be faster
        due to lower overhead.

        Args:
            employee_ids: List of employee IDs to process
            year: Year for calculation
            month: Month for calculation (1-12)
            strategy: Calculation strategy (default: ENHANCED)
            use_parallel: Enable parallel processing (default: True)
            use_cache: Enable Redis caching (default: True)
            save_to_db: Save results to database (default: True)

        Returns:
            Dict[int, PayrollResult]: Results keyed by employee_id

        Example:
            >>> service = get_payroll_service()
            >>> results = service.calculate_bulk_optimized(
            ...     employee_ids=[1, 2, 3, 4, 5],
            ...     year=2025,
            ...     month=10
            ... )
            >>> print(f"Processed {len(results)} employees")
        """
        start_time = time.time()
        strategy = strategy or CalculationStrategy.ENHANCED

        logger.info(
            f"Starting optimized bulk calculation for {len(employee_ids)} employees",
            extra={
                "employee_count": len(employee_ids),
                "year": year,
                "month": month,
                "strategy": strategy.value,
                "use_parallel": use_parallel,
                "use_cache": use_cache,
                "action": "bulk_optimized_start",
            },
        )

        try:
            # Create bulk service
            bulk_service = BulkEnhancedPayrollService(
                use_cache=use_cache and self.enable_caching,
                use_parallel=use_parallel,
                max_workers=None,  # Auto-detect
                batch_size=1000,
                show_progress=False,  # Disable for API calls
            )

            # Execute bulk calculation
            bulk_result = bulk_service.calculate_bulk(
                employee_ids=employee_ids,
                year=year,
                month=month,
                strategy=strategy,
                save_to_db=save_to_db,
            )

            duration_seconds = time.time() - start_time

            logger.info(
                f"Optimized bulk calculation completed: {bulk_result.successful_count} successful, "
                f"{bulk_result.failed_count} failed in {duration_seconds:.2f}s",
                extra={
                    "total_employees": len(employee_ids),
                    "successful_count": bulk_result.successful_count,
                    "failed_count": bulk_result.failed_count,
                    "cached_count": bulk_result.cached_count,
                    "calculated_count": bulk_result.calculated_count,
                    "duration_seconds": duration_seconds,
                    "cache_hit_rate": bulk_result.cache_hit_rate,
                    "db_queries": bulk_result.db_queries_count,
                    "action": "bulk_optimized_completed",
                },
            )

            return bulk_result.results

        except Exception as e:
            duration_seconds = time.time() - start_time
            logger.error(
                f"Optimized bulk calculation failed after {duration_seconds:.2f}s: {e}",
                extra={
                    "employee_count": len(employee_ids),
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_seconds": duration_seconds,
                    "action": "bulk_optimized_error",
                },
                exc_info=True,
            )

            # Fallback to sequential calculation
            if self.enable_fallback:
                logger.warning(
                    "Falling back to sequential calculation",
                    extra={"action": "bulk_optimized_fallback"},
                )

                # Build contexts
                contexts = []
                for emp_id in employee_ids:
                    try:
                        employee = Employee.objects.get(id=emp_id)
                        context: CalculationContext = {
                            "employee_id": emp_id,
                            "user_id": employee.user_id,
                            "year": year,
                            "month": month,
                        }
                        contexts.append(context)
                    except Employee.DoesNotExist:
                        logger.warning(
                            f"Employee {emp_id} not found",
                            extra={"employee_id": emp_id},
                        )

                return self.calculate_bulk(contexts, strategy)
            else:
                raise

    def _execute_calculation(
        self,
        context: CalculationContext,
        strategy: CalculationStrategy,
        start_time: float,
    ) -> PayrollResult:
        """
        Execute the actual payroll calculation with the specified strategy.

        Args:
            context: Calculation context
            strategy: Strategy to use
            start_time: Calculation start time for performance monitoring

        Returns:
            PayrollResult: Calculation result
        """
        try:
            calculator = self.factory.create_calculator(strategy, context)
            result = calculator.calculate_with_logging()

            duration_ms = (time.time() - start_time) * 1000
            self._log_calculation_success(context, strategy, result, duration_ms)

            return result

        except StrategyNotFoundError as e:
            if self.enable_fallback:
                return self._try_fallback_calculation(
                    context, strategy, start_time, str(e)
                )
            else:
                raise
        except Exception as e:
            if self.enable_fallback and strategy != CalculationStrategy.get_fallback():
                return self._try_fallback_calculation(
                    context, strategy, start_time, str(e)
                )
            else:
                raise

    def _try_fallback_calculation(
        self,
        context: CalculationContext,
        original_strategy: CalculationStrategy,
        start_time: float,
        original_error: str,
    ) -> PayrollResult:
        """
        Attempt calculation with fallback strategy.

        Args:
            context: Calculation context
            original_strategy: Strategy that failed
            start_time: Original calculation start time
            original_error: Error message from original attempt

        Returns:
            PayrollResult: Fallback calculation result
        """
        fallback_strategy = CalculationStrategy.get_fallback()

        logger.warning(
            f"Strategy {original_strategy.value} failed, trying fallback {fallback_strategy.value}",
            extra={
                "original_strategy": original_strategy.value,
                "fallback_strategy": fallback_strategy.value,
                "original_error": original_error,
                "employee_id": context["employee_id"],
                "action": "fallback_strategy_attempt",
            },
        )

        try:
            calculator = self.factory.create_calculator(fallback_strategy, context)
            result = calculator.calculate_with_logging()

            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                f"Fallback calculation successful with {fallback_strategy.value}",
                extra={
                    "original_strategy": original_strategy.value,
                    "fallback_strategy": fallback_strategy.value,
                    "employee_id": context["employee_id"],
                    "duration_ms": duration_ms,
                    "action": "fallback_calculation_success",
                },
            )

            # Mark result as coming from fallback
            result["metadata"]["original_strategy"] = original_strategy.value
            result["metadata"]["fallback_used"] = True

            return result

        except Exception as fallback_error:
            logger.error(
                f"Fallback calculation also failed with {fallback_strategy.value}",
                extra={
                    "original_strategy": original_strategy.value,
                    "fallback_strategy": fallback_strategy.value,
                    "original_error": original_error,
                    "fallback_error": str(fallback_error),
                    "employee_id": context["employee_id"],
                    "action": "fallback_calculation_failed",
                },
            )
            raise

    def _check_cache(self, context: CalculationContext) -> Optional[PayrollResult]:
        """
        Check for cached payroll results.

        Args:
            context: Calculation context

        Returns:
            Optional[PayrollResult]: Cached result if available, None otherwise
        """
        # Implementation would depend on specific caching strategy
        # For now, return None to indicate no cache
        return None

    def _cache_result(self, context: CalculationContext, result: PayrollResult) -> None:
        """
        Cache the calculation result for future use.

        Args:
            context: Calculation context
            result: Result to cache
        """
        # Implementation would depend on specific caching strategy
        pass

    def _validate_result(
        self,
        result: PayrollResult,
        context: CalculationContext,
        strategy: CalculationStrategy,
    ) -> None:
        """
        Validate that the calculation result is reasonable and complete.

        Args:
            result: Result to validate
            context: Calculation context
            strategy: Strategy used for calculation

        Raises:
            ValueError: If result validation fails
        """
        # Basic validation checks
        if result["total_salary"] < 0:
            raise ValueError("Total salary cannot be negative")

        if result["total_hours"] < 0:
            raise ValueError("Total hours cannot be negative")

        # Log validation success
        logger.debug(
            f"Result validation passed for {strategy.value}",
            extra={
                "employee_id": context["employee_id"],
                "strategy": strategy.value,
                "total_salary": float(result["total_salary"]),
                "action": "result_validation_success",
            },
        )

    def _log_calculation_request(
        self, context: CalculationContext, strategy: CalculationStrategy
    ) -> None:
        """Log the incoming calculation request"""
        logger.info(
            f"PayrollService calculation requested with {strategy.value}",
            extra={
                "employee_id": context["employee_id"],
                "user_id": context["user_id"],
                "strategy": strategy.value,
                "year": context["year"],
                "month": context["month"],
                "fast_mode": context.get("fast_mode", False),
                "force_recalculate": context.get("force_recalculate", False),
                "action": "payroll_service_request",
            },
        )

    def _log_calculation_success(
        self,
        context: CalculationContext,
        strategy: CalculationStrategy,
        result: PayrollResult,
        duration_ms: float,
    ) -> None:
        """Log successful calculation completion"""
        logger.info(
            f"PayrollService calculation completed successfully with {strategy.value}",
            extra={
                "employee_id": context["employee_id"],
                "strategy": strategy.value,
                "total_salary": float(result["total_salary"]),
                "total_hours": float(result["total_hours"]),
                "duration_ms": duration_ms,
                "has_cache": result["metadata"].get("has_cache", False),
                "action": "payroll_service_success",
            },
        )

    def _log_cache_hit(
        self,
        context: CalculationContext,
        strategy: CalculationStrategy,
        duration_ms: float,
    ) -> None:
        """Log cache hit"""
        logger.info(
            f"PayrollService returned cached result for {strategy.value}",
            extra={
                "employee_id": context["employee_id"],
                "strategy": strategy.value,
                "duration_ms": duration_ms,
                "action": "payroll_service_cache_hit",
            },
        )

    def _handle_calculation_error(
        self,
        error: Exception,
        context: CalculationContext,
        strategy: CalculationStrategy,
        start_time: float,
    ) -> PayrollResult:
        """
        Handle calculation errors and return safe fallback result.

        Args:
            error: The exception that occurred
            context: Calculation context
            strategy: Strategy that was attempted
            start_time: Calculation start time

        Returns:
            PayrollResult: Safe fallback result
        """
        duration_ms = (time.time() - start_time) * 1000

        logger.error(
            f"PayrollService calculation failed with {strategy.value}",
            extra={
                "employee_id": context["employee_id"],
                "strategy": strategy.value,
                "error": str(error),
                "error_type": type(error).__name__,
                "duration_ms": duration_ms,
                "action": "payroll_service_error",
            },
            exc_info=True,
        )

        # Return safe fallback result
        fallback_result = create_empty_payroll_result(
            employee_id=context["employee_id"], strategy=strategy.value
        )

        # Add error information to metadata
        fallback_result["metadata"]["error"] = str(error)
        fallback_result["metadata"]["error_type"] = type(error).__name__
        fallback_result["metadata"]["status"] = PayrollStatus.FAILED.value

        return fallback_result

    def _get_work_logs_for_context(self, context: CalculationContext) -> List[WorkLog]:
        """Helper to fetch work logs based on the calculation context."""
        return list(
            WorkLog.objects.filter(
                employee_id=context["employee_id"],
                check_in__year=context["year"],
                check_in__month=context["month"],
                check_out__isnull=False,
            ).order_by("check_in")
        )

    def _persist_results(
        self,
        context: CalculationContext,
        result: PayrollResult,
        work_logs: List[WorkLog],
    ) -> None:
        """
        Save calculation results to database for audit and caching.
        This logic was moved from the Strategy to the Service to maintain proper separation of concerns.
        """
        try:
            employee = Employee.objects.get(id=context["employee_id"])
            breakdown = result.get("breakdown", {})

            # Create or update monthly summary
            MonthlyPayrollSummary.objects.update_or_create(
                employee=employee,
                year=context["year"],
                month=context["month"],
                defaults={
                    # 'total_salary': result['total_salary'],  # TEMPORARILY DISABLED - field missing
                    "total_gross_pay": result["total_salary"],
                    "total_hours": result["total_hours"],
                    "regular_hours": result["regular_hours"],
                    "overtime_hours": result["overtime_hours"],
                    "holiday_hours": result["holiday_hours"],
                    "sabbath_hours": result["shabbat_hours"],
                    "base_pay": Decimal(str(breakdown.get("regular_pay", 0))),
                    "overtime_pay": Decimal(str(breakdown.get("overtime_125_pay", 0)))
                    + Decimal(str(breakdown.get("overtime_150_pay", 0))),
                    "holiday_pay": Decimal(str(breakdown.get("holiday_pay", 0))),
                    "sabbath_pay": Decimal(str(breakdown.get("sabbath_regular_pay", 0)))
                    + Decimal(str(breakdown.get("sabbath_overtime_175_pay", 0)))
                    + Decimal(str(breakdown.get("sabbath_overtime_200_pay", 0))),
                    "proportional_monthly": Decimal(
                        str(breakdown.get("proportional_base", 0))
                    ),
                    "total_bonuses_monthly": Decimal(
                        str(breakdown.get("total_bonuses_monthly", 0))
                    ),
                    "worked_days": self._calculate_worked_days(work_logs),
                },
            )

            # Create daily calculations from detailed shift results
            self._create_daily_records(employee, context, result)

            # Create compensatory days for Sabbath/Holiday work
            self._create_compensatory_days(employee, context, work_logs)

            logger.info(
                f"Successfully persisted calculation results for employee {context['employee_id']}",
                extra={
                    "employee_id": context["employee_id"],
                    "action": "persist_results_success",
                },
            )

        except Exception as e:
            logger.error(
                f"Failed to persist calculation results: {e}",
                extra={
                    "employee_id": context["employee_id"],
                    "error": str(e),
                    "action": "persist_results_error",
                },
                exc_info=True,
            )
            # Re-raise the exception so the caller knows the transaction failed
            raise

    def _calculate_worked_days(self, work_logs: List[WorkLog]) -> int:
        """Calculate unique days worked in the period."""
        return len(set(log.check_in.date() for log in work_logs))

    def _create_daily_records(
        self,
        employee: Employee,
        context: CalculationContext,
        result: PayrollResult,
    ) -> None:
        """
        Create DailyPayrollCalculation records from daily_results in PayrollResult.

        Uses the detailed shift-by-shift calculations from the strategy
        instead of proportional distribution.
        """
        # Clear existing daily calculations for the month to avoid duplicates
        DailyPayrollCalculation.objects.filter(
            employee=employee,
            work_date__year=context["year"],
            work_date__month=context["month"],
        ).delete()

        # Get daily_results from PayrollResult
        daily_results = result.get("daily_results", [])

        if not daily_results:
            # No detailed results available - skip DailyPayrollCalculation creation
            logger.warning(
                f"No daily_results in PayrollResult for employee {context['employee_id']}. "
                "Skipping DailyPayrollCalculation creation."
            )
            return

        # Build DailyPayrollCalculation objects for bulk create
        daily_calculations = []

        for daily_shift in daily_results:
            # Get holiday name if applicable
            holiday_name = ""
            if daily_shift.get("is_holiday", False):
                holiday_record = Holiday.objects.filter(
                    date=daily_shift["work_date"], is_holiday=True
                ).first()
                if holiday_record:
                    holiday_name = holiday_record.name

            daily_calculations.append(
                DailyPayrollCalculation(
                    employee=employee,
                    work_date=daily_shift["work_date"],
                    worklog_id=daily_shift.get("worklog_id"),
                    # Hours breakdown
                    regular_hours=daily_shift.get("regular_hours", Decimal("0")),
                    overtime_hours_1=daily_shift.get(
                        "overtime_125_hours", Decimal("0")
                    ),
                    overtime_hours_2=daily_shift.get(
                        "overtime_150_hours", Decimal("0")
                    ),
                    sabbath_regular_hours=daily_shift.get(
                        "sabbath_regular_hours", Decimal("0")
                    ),
                    sabbath_overtime_hours_1=daily_shift.get(
                        "sabbath_overtime_175_hours", Decimal("0")
                    ),
                    sabbath_overtime_hours_2=daily_shift.get(
                        "sabbath_overtime_200_hours", Decimal("0")
                    ),
                    night_hours=daily_shift.get("night_shift_hours", Decimal("0")),
                    # Payment breakdown
                    base_regular_pay=daily_shift.get("regular_pay", Decimal("0")),
                    bonus_overtime_pay_1=(
                        daily_shift.get("overtime_125_pay", Decimal("0"))
                        - daily_shift.get("overtime_125_hours", Decimal("0"))
                        * (
                            daily_shift.get("regular_pay", Decimal("0"))
                            / max(
                                daily_shift.get("regular_hours", Decimal("1")),
                                Decimal("1"),
                            )
                        )
                        if daily_shift.get("regular_hours", Decimal("0")) > 0
                        else daily_shift.get("overtime_125_pay", Decimal("0"))
                        * Decimal("0.2")
                    ),
                    bonus_overtime_pay_2=(
                        daily_shift.get("overtime_150_pay", Decimal("0"))
                        - daily_shift.get("overtime_150_hours", Decimal("0"))
                        * (
                            daily_shift.get("regular_pay", Decimal("0"))
                            / max(
                                daily_shift.get("regular_hours", Decimal("1")),
                                Decimal("1"),
                            )
                        )
                        if daily_shift.get("regular_hours", Decimal("0")) > 0
                        else daily_shift.get("overtime_150_pay", Decimal("0"))
                        * Decimal("0.333")
                    ),
                    bonus_sabbath_overtime_pay_1=daily_shift.get(
                        "sabbath_overtime_175_pay", Decimal("0")
                    ),
                    bonus_sabbath_overtime_pay_2=daily_shift.get(
                        "sabbath_overtime_200_pay", Decimal("0")
                    ),
                    # Aggregated payment fields
                    base_pay=daily_shift.get("base_pay", Decimal("0")),
                    bonus_pay=daily_shift.get("bonus_pay", Decimal("0")),
                    total_gross_pay=daily_shift.get("total_gross_pay", Decimal("0")),
                    # Flags
                    is_holiday=daily_shift.get("is_holiday", False),
                    is_sabbath=daily_shift.get("is_sabbath", False),
                    holiday_name=holiday_name,
                    calculated_by_service="PayrollService",
                )
            )

        # Bulk create all daily calculations
        if daily_calculations:
            DailyPayrollCalculation.objects.bulk_create(daily_calculations)

    def _create_compensatory_days(
        self,
        employee: Employee,
        context: CalculationContext,
        work_logs: List[WorkLog],
    ) -> None:
        """
        Create CompensatoryDay records based on WorkLogs and Holidays.

        This method is separate from _create_daily_records to maintain
        separation of concerns between financial calculations and employee benefits.
        """
        # Delete existing unused compensatory days for the period to avoid duplicates
        CompensatoryDay.objects.filter(
            employee=employee,
            date_earned__year=context["year"],
            date_earned__month=context["month"],
            date_used__isnull=True,  # Only delete unused days
        ).delete()

        # Collect unique days that qualify for compensatory time
        days_to_earn = set()

        for log in work_logs:
            work_date = log.check_in.date()

            # Check if Saturday (Shabbat)
            is_saturday = work_date.weekday() == 5

            # Check if holiday in database
            is_holiday = Holiday.objects.filter(
                date=work_date, is_holiday=True
            ).exists()

            if is_saturday:
                days_to_earn.add((work_date, "shabbat"))
            elif is_holiday:
                days_to_earn.add((work_date, "holiday"))

        # Bulk create compensatory days
        new_days = []
        for date_earned, reason in days_to_earn:
            new_days.append(
                CompensatoryDay(
                    employee=employee,
                    date_earned=date_earned,
                    reason=reason,
                )
            )

        if new_days:
            CompensatoryDay.objects.bulk_create(new_days, ignore_conflicts=True)


# Global service instance
_global_service = PayrollService()


def get_payroll_service() -> PayrollService:
    """
    Get the global payroll service instance.

    Returns:
        PayrollService: Global service instance
    """
    return _global_service
