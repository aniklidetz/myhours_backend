"""
Tests for the payroll calculation factory.

This module tests the PayrollCalculatorFactory to ensure proper strategy
registration, creation, and error handling.
"""

import pytest
from unittest.mock import Mock, patch

from payroll.services.factory import (
    PayrollCalculatorFactory,
    StrategyNotFoundError,
    get_payroll_factory,
    register_default_strategies,
    create_calculator_for_context
)
from payroll.services.enums import CalculationStrategy
from payroll.services.contracts import CalculationContext
from payroll.services.strategies.base import AbstractPayrollStrategy


class MockStrategy(AbstractPayrollStrategy):
    """Mock strategy for testing"""

    def calculate(self):
        return {
            'total_salary': 5000.0,
            'total_hours': 160.0,
            'regular_hours': 144.0,
            'overtime_hours': 16.0,
            'holiday_hours': 0.0,
            'shabbat_hours': 0.0,
            'breakdown': {},
            'metadata': {'calculation_strategy': 'mock'}
        }


class InvalidStrategy:
    """Invalid strategy that doesn't inherit from AbstractPayrollStrategy"""
    pass


class TestPayrollCalculatorFactory:
    """Test the payroll calculator factory"""

    @pytest.fixture
    def factory(self):
        """Create a fresh factory instance for each test"""
        return PayrollCalculatorFactory()

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

    def test_factory_initialization(self, factory):
        """Test factory initializes correctly"""
        assert len(factory.get_available_strategies()) == 0
        assert factory._fallback_strategy == CalculationStrategy.get_fallback()

    def test_register_valid_strategy(self, factory):
        """Test registering a valid strategy"""
        factory.register_strategy(CalculationStrategy.LEGACY, MockStrategy)

        available = factory.get_available_strategies()
        assert CalculationStrategy.LEGACY in available
        assert factory.is_strategy_available(CalculationStrategy.LEGACY)

    def test_register_invalid_strategy_raises_error(self, factory):
        """Test registering invalid strategy raises ValueError"""
        with pytest.raises(ValueError) as exc_info:
            factory.register_strategy(CalculationStrategy.LEGACY, InvalidStrategy)

        assert "must inherit from AbstractPayrollStrategy" in str(exc_info.value)

    def test_create_calculator_success(self, factory, context):
        """Test successful calculator creation"""
        factory.register_strategy(CalculationStrategy.LEGACY, MockStrategy)

        calculator = factory.create_calculator(CalculationStrategy.LEGACY, context)

        assert isinstance(calculator, MockStrategy)
        assert calculator._employee_id == 123
        assert calculator._year == 2025

    def test_create_calculator_strategy_not_found(self, factory, context):
        """Test calculator creation with unregistered strategy"""
        with pytest.raises(StrategyNotFoundError) as exc_info:
            factory.create_calculator(CalculationStrategy.LEGACY, context)

        assert "Strategy legacy not found" in str(exc_info.value)

    def test_create_calculator_fallback_when_strategy_missing(self, factory, context):
        """Test fallback strategy usage when requested strategy is missing"""
        # Register fallback strategy only
        fallback = CalculationStrategy.get_fallback()
        factory.register_strategy(fallback, MockStrategy)

        # Request different strategy
        calculator = factory.create_calculator(CalculationStrategy.ENHANCED, context)

        # Should get fallback strategy instance
        assert isinstance(calculator, MockStrategy)

    def test_create_calculator_no_fallback_available(self, factory, context):
        """Test error when no fallback is available"""
        # Don't register any strategies

        with pytest.raises(StrategyNotFoundError) as exc_info:
            factory.create_calculator(CalculationStrategy.ENHANCED, context)

        assert "no fallback available" in str(exc_info.value)

    def test_set_fallback_strategy_success(self, factory):
        """Test setting fallback strategy"""
        factory.register_strategy(CalculationStrategy.ENHANCED, MockStrategy)

        factory.set_fallback_strategy(CalculationStrategy.ENHANCED)
        assert factory._fallback_strategy == CalculationStrategy.ENHANCED

    def test_set_fallback_strategy_not_registered(self, factory):
        """Test setting fallback to unregistered strategy fails"""
        with pytest.raises(StrategyNotFoundError) as exc_info:
            factory.set_fallback_strategy(CalculationStrategy.ENHANCED)

        assert "Cannot set fallback to unregistered strategy" in str(exc_info.value)

    def test_is_strategy_available(self, factory):
        """Test strategy availability checking"""
        assert not factory.is_strategy_available(CalculationStrategy.LEGACY)

        factory.register_strategy(CalculationStrategy.LEGACY, MockStrategy)
        assert factory.is_strategy_available(CalculationStrategy.LEGACY)

    def test_get_available_strategies(self, factory):
        """Test getting list of available strategies"""
        assert factory.get_available_strategies() == []

        factory.register_strategy(CalculationStrategy.LEGACY, MockStrategy)
        factory.register_strategy(CalculationStrategy.ENHANCED, MockStrategy)

        available = factory.get_available_strategies()
        assert len(available) == 2
        assert CalculationStrategy.LEGACY in available
        assert CalculationStrategy.ENHANCED in available


class TestGlobalFactoryFunctions:
    """Test global factory functions"""

    def test_get_payroll_factory_returns_singleton(self):
        """Test that get_payroll_factory returns the same instance"""
        factory1 = get_payroll_factory()
        factory2 = get_payroll_factory()

        assert factory1 is factory2

    def test_register_default_strategies_logs_warning_on_import_error(self):
        """Test that register_default_strategies handles import errors gracefully"""
        with patch('payroll.services.factory.logger') as mock_logger:
            register_default_strategies()

            # Should log that strategies are registered (even though imports fail)
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[1]['extra']
            assert call_args['action'] == 'default_strategies_registered'

    @pytest.fixture
    def context(self):
        """Create test context"""
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

    def test_create_calculator_for_context_preferred_strategy(self, context):
        """Test creating calculator with preferred strategy"""
        factory = get_payroll_factory()
        factory.register_strategy(CalculationStrategy.ENHANCED, MockStrategy)

        calculator = create_calculator_for_context(context, CalculationStrategy.ENHANCED)
        assert isinstance(calculator, MockStrategy)

    def test_create_calculator_for_context_default_strategy(self, context):
        """Test creating calculator with default strategy"""
        factory = get_payroll_factory()
        default_strategy = CalculationStrategy.get_default()
        factory.register_strategy(default_strategy, MockStrategy)

        calculator = create_calculator_for_context(context)
        assert isinstance(calculator, MockStrategy)

    def test_create_calculator_for_context_no_strategies_registered(self, context):
        """Test error when no strategies are registered"""
        # Clear any registered strategies
        factory = PayrollCalculatorFactory()

        with patch('payroll.services.factory._global_factory', factory):
            with pytest.raises(StrategyNotFoundError) as exc_info:
                create_calculator_for_context(context)

            assert "No payroll calculation strategies are registered" in str(exc_info.value)

    def test_create_calculator_for_context_auto_selection(self, context):
        """Test automatic strategy selection when default is not available"""
        factory = PayrollCalculatorFactory()
        factory.register_strategy(CalculationStrategy.LEGACY, MockStrategy)

        with patch('payroll.services.factory._global_factory', factory):
            calculator = create_calculator_for_context(context)
            assert isinstance(calculator, MockStrategy)
