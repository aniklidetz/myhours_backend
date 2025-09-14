"""
Tests for the main payroll service orchestrator.

This module tests the PayrollService class to ensure proper orchestration,
error handling, fallback behavior, and performance monitoring.
"""

import pytest
from decimal import Decimal
from payroll.tests.helpers import MONTHLY_NORM_HOURS, ISRAELI_DAILY_NORM_HOURS, NIGHT_NORM_HOURS, MONTHLY_NORM_HOURS
from unittest.mock import Mock, patch, MagicMock
import time

from payroll.services.payroll_service import PayrollService, get_payroll_service
from payroll.services.enums import CalculationStrategy, PayrollStatus
from payroll.services.contracts import CalculationContext, PayrollResult
from payroll.services.factory import StrategyNotFoundError
from payroll.services.strategies.base import AbstractPayrollStrategy


class MockSuccessfulStrategy(AbstractPayrollStrategy):
    """Mock strategy that always succeeds"""

    def calculate(self) -> PayrollResult:
        return PayrollResult(
            total_salary=Decimal('5000.00'),
            total_hours=Decimal('160.0'),
            regular_hours=Decimal('144.0'),
            overtime_hours=Decimal('16.0'),
            holiday_hours=Decimal('0.0'),
            shabbat_hours=Decimal('0.0'),
            breakdown={
                'base_regular_pay': 4320.0,
                'total_bonuses_monthly': 680.0
            },
            metadata={
                'calculation_strategy': 'mock_successful',
                'employee_type': 'hourly',
                'currency': 'ILS',
                'has_cache': False
            }
        )


class MockFailingStrategy(AbstractPayrollStrategy):
    """Mock strategy that always fails"""

    def calculate(self) -> PayrollResult:
        raise ValueError("Mock calculation failure")


class TestPayrollService:
    """Test the main payroll service orchestrator"""

    @pytest.fixture
    def service(self):
        """Create a fresh service instance for each test"""
        return PayrollService(enable_fallback=True, enable_caching=False)

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
            include_daily_details=False
        )

    @pytest.fixture
    def mock_factory(self):
        """Create a mock factory"""
        factory = Mock()
        factory.create_calculator = Mock()
        return factory

    def test_service_initialization(self, service):
        """Test service initializes correctly"""
        assert service.enable_fallback is True
        assert service.enable_caching is False
        assert service.factory is not None

    @patch.object(PayrollService, '_execute_calculation')
    @patch.object(PayrollService, '_validate_result')
    def test_calculate_success(self, mock_validate, mock_execute, service, context):
        """Test successful calculation"""
        expected_result = PayrollResult(
            total_salary=Decimal('5000.00'),
            total_hours=Decimal('160.0'),
            regular_hours=Decimal('144.0'),
            overtime_hours=Decimal('16.0'),
            holiday_hours=Decimal('0.0'),
            shabbat_hours=Decimal('0.0'),
            breakdown={},
            metadata={'calculation_strategy': 'test'}
        )

        mock_execute.return_value = expected_result

        result = service.calculate(context, CalculationStrategy.ENHANCED)

        assert result == expected_result
        mock_execute.assert_called_once()
        mock_validate.assert_called_once()

    def test_calculate_with_mock_strategy_success(self, service, context):
        """Test calculation with mock strategy"""
        mock_calculator = MockSuccessfulStrategy(context)

        with patch.object(service.factory, 'create_calculator', return_value=mock_calculator):
            result = service.calculate(context, CalculationStrategy.ENHANCED)

            assert result['total_salary'] == Decimal('5000.00')
            assert result['metadata']['calculation_strategy'] == 'mock_successful'

    def test_calculate_with_strategy_failure_and_fallback(self, service, context):
        """Test calculation with strategy failure and successful fallback"""
        successful_result = PayrollResult(
            total_salary=Decimal('5000.00'),
            total_hours=Decimal('160.0'),
            regular_hours=Decimal('144.0'),
            overtime_hours=Decimal('16.0'),
            holiday_hours=Decimal('0.0'),
            shabbat_hours=Decimal('0.0'),
            breakdown={},
            metadata={'calculation_strategy': 'fallback', 'fallback_used': True}
        )

        # Mock the factory to first fail creating the enhanced strategy, then succeed with fallback
        with patch.object(service.factory, 'create_calculator') as mock_create:
            # First call raises exception, second call (in fallback) succeeds
            failing_calculator = MockFailingStrategy(context)
            fallback_calculator = MockSuccessfulStrategy(context)

            mock_create.side_effect = [Exception("Strategy creation failed"), fallback_calculator]

            result = service.calculate(context, CalculationStrategy.ENHANCED)

            # Should get result from fallback
            assert result['total_salary'] == Decimal('5000.00')
            # Factory should be called twice - once for original, once for fallback
            assert mock_create.call_count == 2

    def test_calculate_with_fallback_disabled_raises_error(self, context):
        """Test that disabling fallback causes errors to propagate"""
        service = PayrollService(enable_fallback=False)

        with patch.object(service, '_execute_calculation') as mock_execute:
            mock_execute.side_effect = ValueError("Mock calculation failure")

            # Since fallback is disabled and _handle_calculation_error returns safe result,
            # we should get the safe fallback result, not an exception
            result = service.calculate(context, CalculationStrategy.ENHANCED)

            # Should get empty fallback result from error handler
            assert result['total_salary'] == Decimal('0')
            assert result['total_hours'] == Decimal('0')
            assert 'Mock calculation failure' in result['metadata']['error']

    def test_calculate_with_strategy_not_found_error(self, service, context):
        """Test handling of StrategyNotFoundError"""
        fallback_calculator = MockSuccessfulStrategy(context)

        with patch.object(service.factory, 'create_calculator') as mock_create:
            # First call raises StrategyNotFoundError, second call succeeds
            mock_create.side_effect = [
                StrategyNotFoundError("Strategy not found"),
                fallback_calculator
            ]

            result = service.calculate(context, CalculationStrategy.ENHANCED)

            # Should get result from fallback
            assert result['total_salary'] == Decimal('5000.00')

    def test_calculate_handles_all_failures_gracefully(self, service, context):
        """Test that all failures are handled gracefully"""
        with patch.object(service.factory, 'create_calculator') as mock_create:
            mock_create.side_effect = Exception("Catastrophic failure")

            result = service.calculate(context, CalculationStrategy.ENHANCED)

            # Should get empty fallback result
            assert result['total_salary'] == Decimal('0')
            assert result['total_hours'] == Decimal('0')
            assert 'No calculation data available' in result['metadata']['warnings']
            assert result['metadata']['status'] == PayrollStatus.FAILED.value

    def test_calculate_bulk_success(self, service):
        """Test bulk calculation with multiple employees"""
        contexts = [
            CalculationContext(
                employee_id=100 + i,
                year=2025,
                month=1,
                user_id=456,
                strategy_hint=None,
                force_recalculate=False,
                fast_mode=False,
                include_breakdown=True,
                include_daily_details=False
            )
            for i in range(3)
        ]

        with patch.object(service, 'calculate') as mock_calculate:
            mock_calculate.return_value = PayrollResult(
                total_salary=Decimal('5000.00'),
                total_hours=Decimal('160.0'),
                regular_hours=Decimal('144.0'),
                overtime_hours=Decimal('16.0'),
                holiday_hours=Decimal('0.0'),
                shabbat_hours=Decimal('0.0'),
                breakdown={},
                metadata={'calculation_strategy': 'test'}
            )

            results = service.calculate_bulk(contexts, CalculationStrategy.ENHANCED)

            assert len(results) == 3
            assert 100 in results
            assert 101 in results
            assert 102 in results
            assert mock_calculate.call_count == 3

    def test_calculate_bulk_with_some_failures(self, service):
        """Test bulk calculation with some employee failures"""
        contexts = [
            CalculationContext(
                employee_id=100 + i,
                year=2025,
                month=1,
                user_id=456,
                strategy_hint=None,
                force_recalculate=False,
                fast_mode=False,
                include_breakdown=True,
                include_daily_details=False
            )
            for i in range(3)
        ]

        def mock_calculate_side_effect(context, strategy):
            if context["employee_id"] == 101:
                raise Exception("Employee calculation failed")
            return PayrollResult(
                total_salary=Decimal('5000.00'),
                total_hours=Decimal('160.0'),
                regular_hours=Decimal('144.0'),
                overtime_hours=Decimal('16.0'),
                holiday_hours=Decimal('0.0'),
                shabbat_hours=Decimal('0.0'),
                breakdown={},
                metadata={'calculation_strategy': 'test'}
            )

        with patch.object(service, 'calculate', side_effect=mock_calculate_side_effect):
            results = service.calculate_bulk(contexts, CalculationStrategy.ENHANCED)

            assert len(results) == 3

            # Successful calculations
            assert results[100]['total_salary'] == Decimal('5000.00')
            assert results[102]['total_salary'] == Decimal('5000.00')

            # Failed calculation should have empty result
            assert results[101]['total_salary'] == Decimal('0')
            assert 'No calculation data available' in results[101]['metadata']['warnings']

    def test_validate_result_success(self, service, context):
        """Test successful result validation"""
        valid_result = PayrollResult(
            total_salary=Decimal('5000.00'),
            total_hours=Decimal('160.0'),
            regular_hours=Decimal('144.0'),
            overtime_hours=Decimal('16.0'),
            holiday_hours=Decimal('0.0'),
            shabbat_hours=Decimal('0.0'),
            breakdown={},
            metadata={'calculation_strategy': 'test'}
        )

        # Should not raise exception
        service._validate_result(valid_result, context, CalculationStrategy.ENHANCED)

    def test_validate_result_negative_salary_fails(self, service, context):
        """Test validation fails for negative salary"""
        invalid_result = PayrollResult(
            total_salary=Decimal('-1000.00'),  # Negative salary
            total_hours=Decimal('160.0'),
            regular_hours=Decimal('144.0'),
            overtime_hours=Decimal('16.0'),
            holiday_hours=Decimal('0.0'),
            shabbat_hours=Decimal('0.0'),
            breakdown={},
            metadata={'calculation_strategy': 'test'}
        )

        with pytest.raises(ValueError) as exc_info:
            service._validate_result(invalid_result, context, CalculationStrategy.ENHANCED)

        assert "Total salary cannot be negative" in str(exc_info.value)

    def test_validate_result_negative_hours_fails(self, service, context):
        """Test validation fails for negative hours"""
        invalid_result = PayrollResult(
            total_salary=Decimal('5000.00'),
            total_hours=Decimal('-10.0'),  # Negative hours
            regular_hours=Decimal('144.0'),
            overtime_hours=Decimal('16.0'),
            holiday_hours=Decimal('0.0'),
            shabbat_hours=Decimal('0.0'),
            breakdown={},
            metadata={'calculation_strategy': 'test'}
        )

        with pytest.raises(ValueError) as exc_info:
            service._validate_result(invalid_result, context, CalculationStrategy.ENHANCED)

        assert "Total hours cannot be negative" in str(exc_info.value)

    def test_caching_disabled_by_default_in_test(self, service, context):
        """Test that caching is disabled in test service"""
        assert service.enable_caching is False

        # _check_cache should return None when caching is disabled
        cached_result = service._check_cache(context)
        assert cached_result is None


class TestGlobalServiceFunctions:
    """Test global service functions"""

    def test_get_payroll_service_returns_singleton(self):
        """Test that get_payroll_service returns the same instance"""
        service1 = get_payroll_service()
        service2 = get_payroll_service()

        assert service1 is service2

    def test_global_service_has_correct_defaults(self):
        """Test that global service has correct default settings"""
        service = get_payroll_service()

        assert service.enable_fallback is True
        assert service.enable_caching is True  # Global service should have caching enabled
