"""
Tests for the base payroll calculation strategy.

This module tests the AbstractPayrollStrategy base class to ensure
proper logging, error handling, and interface compliance.
"""

import logging
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest

from payroll.services.contracts import (
    CalculationContext,
    PayrollResult,
    ValidationError,
)
from payroll.services.strategies.base import AbstractPayrollStrategy
from payroll.tests.helpers import (
    ISRAELI_DAILY_NORM_HOURS,
    MONTHLY_NORM_HOURS,
    NIGHT_NORM_HOURS,
)


class ConcreteTestStrategy(AbstractPayrollStrategy):
    """Concrete implementation of AbstractPayrollStrategy for testing"""

    def calculate(self) -> PayrollResult:
        """Test implementation that returns a valid result"""
        return PayrollResult(
            total_salary=Decimal("5000.00"),
            total_hours=Decimal("160.0"),
            regular_hours=Decimal("144.0"),
            overtime_hours=Decimal("16.0"),
            holiday_hours=Decimal("0.0"),
            shabbat_hours=Decimal("0.0"),
            breakdown={"base_regular_pay": 4320.0, "total_bonuses_monthly": 680.0},
            metadata={
                "calculation_strategy": "test",
                "employee_type": "hourly",
                "currency": "ILS",
            },
        )


class FailingTestStrategy(AbstractPayrollStrategy):
    """Strategy that always fails for testing error handling"""

    def calculate(self) -> PayrollResult:
        """Test implementation that always raises an exception"""
        raise ValueError("Test calculation failure")


class TestAbstractPayrollStrategy:
    """Test the abstract base strategy class"""

    @pytest.fixture
    def context(self):
        """Create a test calculation context"""
        return CalculationContext(
            employee_id=123,
            year=2025,
            month=1,
            user_id=456,
            strategy_hint=None,
            force_recalculate=False,
            fast_mode=False,
            include_breakdown=True,
            include_daily_details=False,
        )

    @pytest.fixture
    def strategy(self, context):
        """Create a concrete test strategy instance"""
        return ConcreteTestStrategy(context)

    def test_strategy_initialization(self, strategy):
        """Test strategy initialization with context"""
        assert strategy._employee_id == 123
        assert strategy._year == 2025
        assert strategy._month == 1
        assert strategy._user_id == 456
        assert strategy._fast_mode is False
        assert strategy._force_recalculate is False
        assert strategy._include_breakdown is True
        assert strategy._strategy_name == "ConcreteTestStrategy"

    def test_strategy_with_optional_context(self):
        """Test strategy initialization with all optional context fields"""
        context = CalculationContext(
            employee_id=123,
            year=2025,
            month=1,
            user_id=456,
            strategy_hint="enhanced",
            force_recalculate=True,
            fast_mode=True,
            include_breakdown=True,
            include_daily_details=True,
        )

        strategy = ConcreteTestStrategy(context)
        assert strategy._fast_mode is True
        assert strategy._force_recalculate is True

    def test_calculate_with_logging_success(self, strategy):
        """Test successful calculation with logging"""
        with patch.object(strategy, "logger") as mock_logger:
            result = strategy.calculate_with_logging()

            # Verify result structure
            assert result["total_salary"] == Decimal("5000.00")
            assert result["total_hours"] == Decimal("160.0")

            # Verify logging calls
            mock_logger.info.assert_called()

            # Check start log
            start_call = mock_logger.info.call_args_list[0]
            assert "Starting ConcreteTestStrategy" in start_call[0][0]
            assert start_call[1]["extra"]["action"] == "payroll_calculation_start"
            assert start_call[1]["extra"]["employee_id"] == 123

            # Check success log
            success_call = mock_logger.info.call_args_list[1]
            assert "completed successfully" in success_call[0][0]
            assert success_call[1]["extra"]["action"] == "payroll_calculation_success"
            assert success_call[1]["extra"]["total_salary"] == 5000.0

    def test_calculate_with_logging_failure(self):
        """Test calculation failure with error logging"""
        context = CalculationContext(
            employee_id=123,
            year=2025,
            month=1,
            user_id=456,
            strategy_hint=None,
            force_recalculate=False,
            fast_mode=False,
            include_breakdown=True,
            include_daily_details=False,
        )

        failing_strategy = FailingTestStrategy(context)

        with patch.object(failing_strategy, "logger") as mock_logger:
            result = failing_strategy.calculate_with_logging()

            # Should return fallback result, not raise exception
            assert result["total_salary"] == Decimal("0")
            assert result["total_hours"] == Decimal("0")
            assert "No calculation data available" in result["metadata"]["warnings"]

            # Verify error logging
            mock_logger.error.assert_called_once()
            error_call = mock_logger.error.call_args_list[0]
            assert "calculation failed" in error_call[0][0]
            assert error_call[1]["extra"]["action"] == "payroll_calculation_error"
            assert error_call[1]["extra"]["error"] == "Test calculation failure"
            assert error_call[1]["extra"]["error_type"] == "ValueError"

    def test_performance_metrics_logging(self, strategy):
        """Test performance metrics logging"""
        with patch.object(strategy, "logger") as mock_logger:
            strategy._log_performance_metrics(
                "database_query", 150.5, {"query_count": 3, "cache_hits": 2}
            )

            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args

            assert "database_query performance" in call_args[0][0]
            assert call_args[1]["extra"]["duration_ms"] == 150.5
            assert call_args[1]["extra"]["query_count"] == 3
            assert call_args[1]["extra"]["cache_hits"] == 2
            assert call_args[1]["extra"]["action"] == "performance_metric"

    @patch("users.models.Employee.objects.get")
    def test_get_employee_success(self, mock_get, strategy):
        """Test successful employee retrieval"""
        mock_employee = Mock()
        mock_employee.get_full_name.return_value = "Test User"
        mock_get.return_value = mock_employee

        employee = strategy._get_employee()

        assert employee == mock_employee
        mock_get.assert_called_once_with(id=123)

    @patch("users.models.Employee.objects.get")
    def test_get_employee_not_found(self, mock_get, strategy):
        """Test employee not found handling"""
        from users.models import Employee

        mock_get.side_effect = Employee.DoesNotExist()

        with pytest.raises(Employee.DoesNotExist):
            strategy._get_employee()

    def test_get_salary_info_success(self, strategy):
        """Test successful salary info retrieval"""
        mock_employee = Mock()
        mock_salary = Mock()
        mock_salary.calculation_type = "hourly"
        mock_salary.currency = "ILS"
        mock_employee.salary_info = mock_salary

        salary = strategy._get_salary_info(mock_employee)

        assert salary == mock_salary

    def test_get_salary_info_missing(self, strategy):
        """Test missing salary info handling"""
        mock_employee = Mock()
        mock_employee.salary_info = None

        with pytest.raises(AttributeError) as exc_info:
            strategy._get_salary_info(mock_employee)

        assert "No active salary configuration" in str(exc_info.value)

    def test_create_error_fallback(self, strategy):
        """Test error fallback result creation"""
        result = strategy._create_error_fallback("Test error message")

        assert result["total_salary"] == Decimal("0")
        assert result["total_hours"] == Decimal("0")
        assert result["metadata"]["calculation_strategy"] == "ConcreteTestStrategy"
        assert "No calculation data available" in result["metadata"]["warnings"]

    def test_abstract_methods_must_be_implemented(self):
        """Test that abstract methods must be implemented"""
        context = CalculationContext(
            employee_id=123,
            year=2025,
            month=1,
            user_id=456,
            strategy_hint=None,
            force_recalculate=False,
            fast_mode=False,
            include_breakdown=True,
            include_daily_details=False,
        )

        # Should not be able to instantiate abstract class directly
        with pytest.raises(TypeError):
            AbstractPayrollStrategy(context)
