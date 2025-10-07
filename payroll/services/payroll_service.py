"""
Main payroll calculation orchestrator service.

This module provides the main PayrollService class that acts as the primary
interface for all payroll calculations, managing strategy selection,
error handling, caching, and comprehensive logging.
"""

import logging
import time
from decimal import Decimal
from typing import Optional, Dict, Any, List

from payroll.models import MonthlyPayrollSummary, DailyPayrollCalculation, CompensatoryDay
from users.models import Employee
from worktime.models import WorkLog
from integrations.models import Holiday

from .enums import CalculationStrategy, PayrollStatus, CacheSource
from .contracts import PayrollResult, CalculationContext, create_empty_payroll_result
from .factory import get_payroll_factory, StrategyNotFoundError


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
        strategy: Optional[CalculationStrategy] = None
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
            if not context.get('fast_mode', False):
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
        strategy: Optional[CalculationStrategy] = None
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
                "action": "bulk_calculation_start"
            }
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
                        "action": "bulk_calculation_employee_failed"
                    }
                )
                results[context["employee_id"]] = create_empty_payroll_result(
                    employee_id=context["employee_id"],
                    strategy=strategy.value
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
                "action": "bulk_calculation_completed"
            }
        )
        
        return results
    
    def _execute_calculation(
        self,
        context: CalculationContext,
        strategy: CalculationStrategy,
        start_time: float
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
                return self._try_fallback_calculation(context, strategy, start_time, str(e))
            else:
                raise
        except Exception as e:
            if self.enable_fallback and strategy != CalculationStrategy.get_fallback():
                return self._try_fallback_calculation(context, strategy, start_time, str(e))
            else:
                raise
    
    def _try_fallback_calculation(
        self,
        context: CalculationContext,
        original_strategy: CalculationStrategy,
        start_time: float,
        original_error: str
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
                "action": "fallback_strategy_attempt"
            }
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
                    "action": "fallback_calculation_success"
                }
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
                    "action": "fallback_calculation_failed"
                }
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
        strategy: CalculationStrategy
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
                "action": "result_validation_success"
            }
        )
    
    def _log_calculation_request(
        self,
        context: CalculationContext,
        strategy: CalculationStrategy
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
                "action": "payroll_service_request"
            }
        )
    
    def _log_calculation_success(
        self,
        context: CalculationContext,
        strategy: CalculationStrategy,
        result: PayrollResult,
        duration_ms: float
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
                "action": "payroll_service_success"
            }
        )
    
    def _log_cache_hit(
        self,
        context: CalculationContext,
        strategy: CalculationStrategy,
        duration_ms: float
    ) -> None:
        """Log cache hit"""
        logger.info(
            f"PayrollService returned cached result for {strategy.value}",
            extra={
                "employee_id": context["employee_id"],
                "strategy": strategy.value,
                "duration_ms": duration_ms,
                "action": "payroll_service_cache_hit"
            }
        )
    
    def _handle_calculation_error(
        self,
        error: Exception,
        context: CalculationContext,
        strategy: CalculationStrategy,
        start_time: float
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
                "action": "payroll_service_error"
            },
            exc_info=True
        )
        
        # Return safe fallback result
        fallback_result = create_empty_payroll_result(
            employee_id=context["employee_id"],
            strategy=strategy.value
        )
        
        # Add error information to metadata
        fallback_result["metadata"]["error"] = str(error)
        fallback_result["metadata"]["error_type"] = type(error).__name__
        fallback_result["metadata"]["status"] = PayrollStatus.FAILED.value
        
        return fallback_result

    def _get_work_logs_for_context(self, context: CalculationContext) -> List[WorkLog]:
        """Helper to fetch work logs based on the calculation context."""
        return list(WorkLog.objects.filter(
            employee_id=context['employee_id'],
            check_in__year=context['year'],
            check_in__month=context['month'],
            check_out__isnull=False
        ).order_by('check_in'))

    def _persist_results(self, context: CalculationContext, result: PayrollResult, work_logs: List[WorkLog]) -> None:
        """
        Save calculation results to database for audit and caching.
        This logic was moved from the Strategy to the Service to maintain proper separation of concerns.
        """
        try:
            employee = Employee.objects.get(id=context['employee_id'])
            breakdown = result.get('breakdown', {})

            # Create or update monthly summary
            MonthlyPayrollSummary.objects.update_or_create(
                employee=employee,
                year=context['year'],
                month=context['month'],
                defaults={
                    # 'total_salary': result['total_salary'],  # TEMPORARILY DISABLED - field missing
                    'total_gross_pay': result['total_salary'],
                    'total_hours': result['total_hours'],
                    'regular_hours': result['regular_hours'],
                    'overtime_hours': result['overtime_hours'],
                    'holiday_hours': result['holiday_hours'],
                    'sabbath_hours': result['shabbat_hours'],
                    'base_pay': Decimal(str(breakdown.get('regular_pay', 0))),
                    'overtime_pay': Decimal(str(breakdown.get('overtime_125_pay', 0))) + Decimal(str(breakdown.get('overtime_150_pay', 0))),
                    'holiday_pay': Decimal(str(breakdown.get('holiday_pay', 0))),
                    'sabbath_pay': Decimal(str(breakdown.get('sabbath_regular_pay', 0))) + Decimal(str(breakdown.get('sabbath_overtime_175_pay', 0))) + Decimal(str(breakdown.get('sabbath_overtime_200_pay', 0))),
                    'proportional_monthly': Decimal(str(breakdown.get('proportional_base', 0))),
                    'total_bonuses_monthly': Decimal(str(breakdown.get('total_bonuses_monthly', 0))),
                    'worked_days': self._calculate_worked_days(work_logs)
                }
            )

            # Create daily calculations and compensatory days
            self._create_daily_records(employee, context, work_logs, result)

            logger.info(
                f"Successfully persisted calculation results for employee {context['employee_id']}",
                extra={ "employee_id": context['employee_id'], "action": "persist_results_success" }
            )

        except Exception as e:
            logger.error(f"Failed to persist calculation results: {e}", extra={
                "employee_id": context['employee_id'],
                "error": str(e),
                "action": "persist_results_error"
            }, exc_info=True)
            # Re-raise the exception so the caller knows the transaction failed
            raise

    def _calculate_worked_days(self, work_logs: List[WorkLog]) -> int:
        """Calculate unique days worked in the period."""
        return len(set(log.check_in.date() for log in work_logs))

    def _create_daily_records(self, employee: Employee, context: CalculationContext, work_logs: List[WorkLog], result: PayrollResult) -> None:
        """
        Create DailyPayrollCalculation and CompensatoryDay records.
        This logic uses proportional distribution for simplicity.
        """
        # Clear existing daily calculations for the month to avoid duplicates
        DailyPayrollCalculation.objects.filter(
            employee=employee,
            work_date__year=context['year'],
            work_date__month=context['month']
        ).delete()

        daily_logs = {}
        for log in work_logs:
            work_date = log.check_in.date()
            daily_logs.setdefault(work_date, []).append(log)

        monthly_total_hours = result.get('total_hours', Decimal('0'))
        if monthly_total_hours <= 0:
            return

        # Distribute monthly totals proportionally based on daily hours
        for work_date, logs_for_day in daily_logs.items():
            daily_hours = sum(log.get_total_hours() for log in logs_for_day)
            proportion = daily_hours / monthly_total_hours

            # Check if it's a holiday or sabbath to create compensatory days
            holiday_record = Holiday.objects.filter(date=work_date, is_holiday=True).first()
            is_holiday = holiday_record is not None
            is_sabbath = Holiday.objects.filter(date=work_date, is_shabbat=True).exists()

            if is_holiday:
                CompensatoryDay.objects.get_or_create(employee=employee, date_earned=work_date, reason="holiday")
            if is_sabbath:
                CompensatoryDay.objects.get_or_create(employee=employee, date_earned=work_date, reason="sabbath")

            DailyPayrollCalculation.objects.create(
                employee=employee,
                work_date=work_date,
                regular_hours=result['regular_hours'] * proportion,
                total_gross_pay=result['total_salary'] * proportion,
                is_holiday=is_holiday,
                is_sabbath=is_sabbath,
                holiday_name=holiday_record.name if is_holiday else '',
                calculated_by_service='PayrollService',
                worklog=logs_for_day[0] if logs_for_day else None
            )


# Global service instance
_global_service = PayrollService()


def get_payroll_service() -> PayrollService:
    """
    Get the global payroll service instance.
    
    Returns:
        PayrollService: Global service instance
    """
    return _global_service