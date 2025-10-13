"""
Test configuration and fixtures for payroll tests.

Provides common test utilities for transitioning from legacy adapters
to direct PayrollService usage.
"""

from decimal import Decimal
from typing import Optional

import pytest

# Imports moved to functions to avoid Django setup issues during conftest loading


@pytest.fixture
def payroll_service():
    """Provide PayrollService instance for tests."""
    from payroll.services.payroll_service import PayrollService

    return PayrollService()


def make_context(
    employee,
    year: int,
    month: int,
    *,
    employee_type=None,
    user_id: int = 1,
    fast_mode: bool = False,
    **kwargs,
):
    """
    Factory function to create CalculationContext for tests.

    Replaces the old adapter pattern:
    OLD: PayrollService(employee, year, month)
    NEW: make_context(employee, year, month)

    Args:
        employee: Employee model instance
        year: Calculation year
        month: Calculation month
        employee_type: Override employee type detection
        user_id: User ID for context (default: system user)
        fast_mode: Enable fast calculation mode
        **kwargs: Additional context parameters

    Returns:
        CalculationContext ready for PayrollService.calculate()
    """
    from payroll.services.contracts import CalculationContext
    from payroll.services.enums import EmployeeType

    # Auto-detect employee type if not provided
    if employee_type is None:
        if (
            hasattr(employee, "salaries")
            and employee.salaries.filter(
                is_active=True, calculation_type="hourly"
            ).exists()
        ):
            employee_type = EmployeeType.HOURLY
        else:
            employee_type = EmployeeType.MONTHLY

    return CalculationContext(
        employee_id=employee.id,
        year=year,
        month=month,
        user_id=user_id,
        employee_type=employee_type,
        fast_mode=fast_mode,
        **kwargs,
    )


def assert_result_structure(result: dict, expected_keys: Optional[set] = None):
    """
    Assert that PayrollService result has expected structure.

    Validates the new PayrollService response format to prevent
    regressions when migrating from adapter responses.
    """
    if expected_keys is None:
        expected_keys = {
            "total_salary",
            "total_hours",
            "base_pay",
            "bonus_pay",
            "breakdown",
            "is_sabbath",
            "calculation_method",
        }

    missing_keys = expected_keys - set(result.keys())
    assert not missing_keys, f"Missing keys in result: {missing_keys}"

    # Validate numeric fields are Decimal
    for key in ["total_salary", "total_hours", "base_pay", "bonus_pay"]:
        if key in result:
            assert isinstance(
                result[key], Decimal
            ), f"{key} should be Decimal, got {type(result[key])}"


# Migration helpers for common test patterns
def legacy_to_new_result_mapping(legacy_result: dict) -> dict:
    """
    Map legacy adapter result format to new PayrollService format.

    Helps during transition period where some tests expect old format.
    """
    return {
        "total_salary": legacy_result.get("total_salary", Decimal("0")),
        "total_hours": legacy_result.get("total_hours", Decimal("0")),
        "regular_hours": legacy_result.get("regular_hours", Decimal("0")),
        "overtime_hours": legacy_result.get("overtime_hours", Decimal("0")),
    }


# Constants for Israeli labor law compliance
ISRAELI_DAILY_NORM_HOURS = Decimal("8.6")
NIGHT_NORM_HOURS = Decimal("7")
MONTHLY_NORM_HOURS = Decimal("182")

OVERTIME_RATES = {
    "regular": Decimal("1.0"),
    "overtime_125": Decimal("1.25"),
    "overtime_150": Decimal("1.50"),
    "overtime_175": Decimal("1.75"),
    "overtime_200": Decimal("2.00"),
}


@pytest.fixture
def israeli_labor_constants():
    """Provide Israeli labor law constants for tests."""
    return {
        "daily_norm_hours": ISRAELI_DAILY_NORM_HOURS,
        "night_norm_hours": NIGHT_NORM_HOURS,
        "monthly_norm_hours": MONTHLY_NORM_HOURS,
        "overtime_rates": OVERTIME_RATES,
    }
