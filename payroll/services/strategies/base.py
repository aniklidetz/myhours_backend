"""
Base strategy interface for payroll calculations.

This module defines the abstract base class that all payroll calculation
strategies must implement, ensuring consistent interface and logging.
"""

import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional

from ..contracts import CalculationContext, PayrollResult, create_empty_payroll_result
from ..enums import CalculationStrategy, PayrollStatus

logger = logging.getLogger(__name__)


class AbstractPayrollStrategy(ABC):
    """
    Abstract base class for all payroll calculation strategies.

    This class provides:
    - Consistent interface across all strategies
    - Comprehensive logging for debugging and monitoring
    - Error handling with graceful fallbacks
    - Context management for calculations
    """

    def __init__(self, context: CalculationContext):
        """
        Initialize the strategy with calculation context.

        Args:
            context: All necessary data for payroll calculations
        """
        self.context = context
        self.logger = logger
        self._employee_id = context["employee_id"]
        self._year = context["year"]
        self._month = context["month"]
        self._user_id = context["user_id"]

        # Optional context settings with defaults
        self._fast_mode = context.get("fast_mode", False)
        self._force_recalculate = context.get("force_recalculate", False)
        self._include_breakdown = context.get("include_breakdown", True)
        self._include_daily_details = context.get("include_daily_details", True)

        # Strategy identification
        self._strategy_name = self.__class__.__name__

    @abstractmethod
    def calculate(self) -> PayrollResult:
        """
        Calculate payroll for the employee and period.

        This method must be implemented by all concrete strategy classes.

        Returns:
            PayrollResult: Standardized payroll calculation result

        Raises:
            Any exceptions should be caught and handled appropriately
        """
        pass

    def calculate_with_logging(self) -> PayrollResult:
        """
        Main entry point that wraps calculate() with comprehensive logging.

        This method should be called instead of calculate() directly to ensure
        proper logging and error handling.

        Returns:
            PayrollResult: Calculation result or safe fallback on error
        """
        self._log_calculation_start()

        try:
            result = self.calculate()
            self._log_calculation_success(result)
            return result

        except Exception as e:
            self._log_calculation_error(e)
            return self._create_error_fallback(str(e))

    def _log_calculation_start(self) -> None:
        """Log the start of payroll calculation with context"""
        self.logger.info(
            f"Starting {self._strategy_name} payroll calculation",
            extra={
                "strategy": self._strategy_name,
                "employee_id": self._employee_id,
                "user_id": self._user_id,
                "year": self._year,
                "month": self._month,
                "fast_mode": self._fast_mode,
                "force_recalculate": self._force_recalculate,
                "action": "payroll_calculation_start",
            },
        )

    def _log_calculation_success(self, result: PayrollResult) -> None:
        """Log successful calculation completion"""
        self.logger.info(
            f"{self._strategy_name} calculation completed successfully",
            extra={
                "strategy": self._strategy_name,
                "employee_id": self._employee_id,
                "total_salary": float(result["total_salary"]),
                "total_hours": float(result["total_hours"]),
                "regular_hours": float(result["regular_hours"]),
                "overtime_hours": float(result["overtime_hours"]),
                "has_cache": result["metadata"].get("has_cache", False),
                "cache_source": result["metadata"].get("cache_source"),
                "action": "payroll_calculation_success",
            },
        )

    def _log_calculation_error(self, error: Exception) -> None:
        """Log calculation errors with full context"""
        self.logger.error(
            f"{self._strategy_name} calculation failed",
            extra={
                "strategy": self._strategy_name,
                "employee_id": self._employee_id,
                "user_id": self._user_id,
                "year": self._year,
                "month": self._month,
                "error": str(error),
                "error_type": type(error).__name__,
                "action": "payroll_calculation_error",
            },
            exc_info=True,  # Include full traceback
        )

    def _create_error_fallback(self, error_message: str) -> PayrollResult:
        """
        Create a safe fallback result when calculation fails.

        Args:
            error_message: Description of the error

        Returns:
            PayrollResult: Empty result with error information
        """
        return create_empty_payroll_result(
            employee_id=self._employee_id,
            strategy=self._strategy_name,
            currency="ILS",  # Default currency
        )

    def _get_employee(self):
        """
        Get employee instance from database.

        Returns:
            Employee: Employee model instance

        Raises:
            Employee.DoesNotExist: If employee not found
        """
        from users.models import Employee

        try:
            employee = Employee.objects.get(id=self._employee_id)
            self.logger.debug(
                f"Employee loaded for {self._strategy_name}",
                extra={
                    "employee_id": self._employee_id,
                    "employee_name": employee.get_full_name(),
                    "action": "employee_loaded",
                },
            )
            return employee
        except Employee.DoesNotExist:
            self.logger.error(
                f"Employee {self._employee_id} not found for {self._strategy_name}",
                extra={
                    "employee_id": self._employee_id,
                    "strategy": self._strategy_name,
                    "action": "employee_not_found",
                },
            )
            raise

    def _get_salary_info(self, employee):
        """
        Get active salary information for employee.

        Args:
            employee: Employee model instance

        Returns:
            Salary: Active salary configuration

        Raises:
            AttributeError: If no active salary found
        """
        try:
            salary = employee.salary_info
            if salary is None:
                raise AttributeError(
                    f"No active salary configuration for employee {self._employee_id}"
                )

            self.logger.debug(
                f"Salary info loaded for {self._strategy_name}",
                extra={
                    "employee_id": self._employee_id,
                    "calculation_type": salary.calculation_type,
                    "currency": salary.currency,
                    "action": "salary_info_loaded",
                },
            )
            return salary
        except AttributeError as e:
            self.logger.error(
                f"No salary configuration found for employee {self._employee_id}",
                extra={
                    "employee_id": self._employee_id,
                    "strategy": self._strategy_name,
                    "error": str(e),
                    "action": "salary_info_missing",
                },
            )
            raise

    def _log_performance_metrics(
        self,
        operation: str,
        duration_ms: float,
        additional_metrics: Optional[dict] = None,
    ) -> None:
        """
        Log performance metrics for monitoring.

        Args:
            operation: Name of the operation being measured
            duration_ms: Duration in milliseconds
            additional_metrics: Optional additional metrics to log
        """
        metrics = {
            "strategy": self._strategy_name,
            "employee_id": self._employee_id,
            "operation": operation,
            "duration_ms": duration_ms,
            "action": "performance_metric",
        }

        if additional_metrics:
            metrics.update(additional_metrics)

        self.logger.info(
            f"{self._strategy_name} {operation} performance", extra=metrics
        )
