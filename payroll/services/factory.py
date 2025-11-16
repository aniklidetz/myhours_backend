"""
Factory for creating payroll calculation strategies.

This module provides the factory pattern implementation for creating
appropriate payroll calculation strategies based on context and requirements.
"""

import logging
from typing import Dict, Type

from .contracts import CalculationContext
from .enums import CalculationStrategy
from .strategies.base import AbstractPayrollStrategy

logger = logging.getLogger(__name__)


class StrategyNotFoundError(Exception):
    """Raised when requested strategy is not available or not registered"""

    pass


class PayrollCalculatorFactory:
    """
    Factory class for creating payroll calculation strategies.

    This factory manages the registration and creation of different payroll
    calculation strategies, providing a centralized way to instantiate
    the appropriate strategy based on requirements.
    """

    def __init__(self):
        """Initialize the factory with empty strategy registry"""
        self._strategies: Dict[CalculationStrategy, Type[AbstractPayrollStrategy]] = {}
        self._fallback_strategy: CalculationStrategy = (
            CalculationStrategy.get_fallback()
        )

    def register_strategy(
        self,
        strategy_type: CalculationStrategy,
        strategy_class: Type[AbstractPayrollStrategy],
    ) -> None:
        """
        Register a strategy implementation with the factory.

        Args:
            strategy_type: The strategy enum identifier
            strategy_class: The concrete strategy class to register

        Raises:
            ValueError: If strategy_class doesn't inherit from AbstractPayrollStrategy
        """
        if not issubclass(strategy_class, AbstractPayrollStrategy):
            raise ValueError(
                f"Strategy class {strategy_class} must inherit from AbstractPayrollStrategy"
            )

        self._strategies[strategy_type] = strategy_class
        logger.debug(
            f"Registered strategy {strategy_type.value} with class {strategy_class.__name__}",
            extra={
                "strategy_type": strategy_type.value,
                "strategy_class": strategy_class.__name__,
                "action": "strategy_registered",
            },
        )

    def create_calculator(
        self, strategy_type: CalculationStrategy, context: CalculationContext
    ) -> AbstractPayrollStrategy:
        """
        Create a payroll calculator instance for the specified strategy.

        Args:
            strategy_type: The type of calculation strategy to create
            context: Calculation context containing all necessary data

        Returns:
            AbstractPayrollStrategy: Configured strategy instance

        Raises:
            StrategyNotFoundError: If the requested strategy is not registered
        """
        if strategy_type not in self._strategies:
            # Try fallback strategy if available
            if self._fallback_strategy in self._strategies:
                logger.warning(
                    f"Strategy {strategy_type.value} not found, using fallback {self._fallback_strategy.value}",
                    extra={
                        "requested_strategy": strategy_type.value,
                        "fallback_strategy": self._fallback_strategy.value,
                        "employee_id": context["employee_id"],
                        "action": "strategy_fallback",
                    },
                )
                strategy_type = self._fallback_strategy
            else:
                raise StrategyNotFoundError(
                    f"Strategy {strategy_type.value} not found and no fallback available. "
                    f"Available strategies: {list(self._strategies.keys())}"
                )

        strategy_class = self._strategies[strategy_type]

        try:
            calculator = strategy_class(context)
            logger.debug(
                f"Created calculator for strategy {strategy_type.value}",
                extra={
                    "strategy_type": strategy_type.value,
                    "strategy_class": strategy_class.__name__,
                    "employee_id": context["employee_id"],
                    "action": "calculator_created",
                },
            )
            return calculator

        except Exception as e:
            logger.error(
                f"Failed to create calculator for strategy {strategy_type.value}",
                extra={
                    "strategy_type": strategy_type.value,
                    "strategy_class": strategy_class.__name__,
                    "employee_id": context["employee_id"],
                    "error": str(e),
                    "action": "calculator_creation_failed",
                },
            )
            raise

    def get_available_strategies(self) -> list[CalculationStrategy]:
        """
        Get list of all registered strategies.

        Returns:
            list[CalculationStrategy]: List of available strategy types
        """
        return list(self._strategies.keys())

    def is_strategy_available(self, strategy_type: CalculationStrategy) -> bool:
        """
        Check if a specific strategy is available.

        Args:
            strategy_type: Strategy type to check

        Returns:
            bool: True if strategy is registered and available
        """
        return strategy_type in self._strategies

    def set_fallback_strategy(self, strategy_type: CalculationStrategy) -> None:
        """
        Set the fallback strategy to use when requested strategy is not available.

        Args:
            strategy_type: Strategy type to use as fallback

        Raises:
            StrategyNotFoundError: If fallback strategy is not registered
        """
        if strategy_type not in self._strategies:
            raise StrategyNotFoundError(
                f"Cannot set fallback to unregistered strategy {strategy_type.value}"
            )

        old_fallback = self._fallback_strategy
        self._fallback_strategy = strategy_type

        logger.info(
            f"Fallback strategy changed from {old_fallback.value} to {strategy_type.value}",
            extra={
                "old_fallback": old_fallback.value,
                "new_fallback": strategy_type.value,
                "action": "fallback_strategy_changed",
            },
        )


# Global factory instance
_global_factory = PayrollCalculatorFactory()


def get_payroll_factory() -> PayrollCalculatorFactory:
    """
    Get the global payroll calculator factory instance.

    Returns:
        PayrollCalculatorFactory: Global factory instance
    """
    return _global_factory


def register_default_strategies() -> None:
    """
    Register all default payroll calculation strategies.

    This function should be called during application startup to ensure
    all standard strategies are available.
    """
    factory = get_payroll_factory()

    # Import strategies here to avoid circular imports
    try:
        from .strategies.enhanced import EnhancedPayrollStrategy

        factory.register_strategy(CalculationStrategy.ENHANCED, EnhancedPayrollStrategy)

        # Note: Legacy strategy will be added when we create it
        # from .strategies.legacy import LegacyPayrollStrategy
        # factory.register_strategy(CalculationStrategy.LEGACY, LegacyPayrollStrategy)

        logger.info(
            "Default payroll calculation strategies registered",
            extra={
                "action": "default_strategies_registered",
                "registered_strategies": ["enhanced"],
            },
        )

    except ImportError as e:
        logger.warning(
            f"Some default strategies could not be imported: {e}",
            extra={"error": str(e), "action": "strategy_import_warning"},
        )


def create_calculator_for_context(
    context: CalculationContext, preferred_strategy: CalculationStrategy = None
) -> AbstractPayrollStrategy:
    """
    Convenience function to create a calculator with automatic strategy selection.

    Args:
        context: Calculation context
        preferred_strategy: Preferred strategy, or None for default

    Returns:
        AbstractPayrollStrategy: Configured calculator instance
    """
    factory = get_payroll_factory()

    # Use preferred strategy if provided and available, otherwise use default
    if preferred_strategy and factory.is_strategy_available(preferred_strategy):
        strategy_type = preferred_strategy
    else:
        strategy_type = CalculationStrategy.get_default()

        # If default is not available, use any available strategy
        if not factory.is_strategy_available(strategy_type):
            available = factory.get_available_strategies()
            if available:
                strategy_type = available[0]
                logger.warning(
                    f"Default strategy not available, using {strategy_type.value}",
                    extra={
                        "default_strategy": CalculationStrategy.get_default().value,
                        "used_strategy": strategy_type.value,
                        "action": "strategy_auto_selection",
                    },
                )
            else:
                raise StrategyNotFoundError(
                    "No payroll calculation strategies are registered"
                )

    return factory.create_calculator(strategy_type, context)
