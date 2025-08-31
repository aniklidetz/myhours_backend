"""
Test utilities for consistent handling of Employee salary_info contract.
This module provides helpers to prevent regressions in the salary_info interface
where salary_info is a property returning active Salary object or None.
"""

from typing import Optional

from payroll.models import Salary
from users.models import Employee


def get_active_salary(employee: Employee) -> Optional[Salary]:
    """Get active salary for employee using the salary_info property.

    This helper ensures consistent usage across tests and catches interface regressions early.

    Args:
        employee: Employee instance

    Returns:
        Active Salary object or None if no active salary exists

    Usage:
        # Correct usage
        salary = get_active_salary(employee)
        if salary:
            assert salary.calculation_type == "hourly"

        # Avoid this
        salary = employee.salary_info.filter(is_active=True).first()  # WRONG!
    """
    salary = getattr(employee, "salary_info", None)

    # Protective assertion to catch contract violations
    assert salary is None or salary.__class__.__name__ == "Salary", (
        f"salary_info should return Salary instance or None, "
        f"got {type(salary)} instead"
    )

    return salary


def get_all_employee_salaries(employee: Employee):
    """Get all salaries for employee using the salaries RelatedManager.

    Use this when you need a QuerySet of all employee salaries.

    Args:
        employee: Employee instance

    Returns:
        QuerySet[Salary] of all salaries for this employee

    Usage:
        # For QuerySet operations
        all_salaries = get_all_employee_salaries(employee)
        active_salaries = all_salaries.filter(is_active=True)

        # Single active salary (preferred)
        salary = get_active_salary(employee)
    """
    return employee.salaries.all()


def assert_salary_contract(employee: Employee) -> None:
    """Assert that employee follows salary_info contract correctly.

    Use this in test setup to catch contract violations early.
    """
    salary = getattr(employee, "salary_info", None)

    # Contract assertions
    assert salary is None or isinstance(
        salary, Salary
    ), f"salary_info must return Salary instance or None, got {type(salary)}"

    # If salary exists, verify it's active
    if salary:
        assert salary.is_active, "salary_info should only return active salaries"
        assert (
            salary.employee_id == employee.id
        ), "salary_info returned wrong employee's salary"


def create_test_salary(
    employee: Employee, salary_type: str = "hourly", **kwargs
) -> Salary:
    """Create test salary with safe defaults.

    Args:
        employee: Employee to create salary for
        salary_type: "hourly", "monthly", or "project"
        **kwargs: Additional salary fields

    Returns:
        Created Salary instance
    """
    from decimal import Decimal

    defaults = {
        "employee": employee,
        "calculation_type": salary_type,
        "currency": "ILS",
        "is_active": True,
    }

    # Type-specific defaults
    if salary_type == "hourly":
        defaults.update(
            {
                "hourly_rate": Decimal("50.00"),
            }
        )
    elif salary_type == "monthly":
        defaults.update(
            {
                "base_salary": Decimal("12000.00"),
            }
        )
    elif salary_type == "project":
        defaults.update(
            {
                "base_salary": Decimal("25000.00"),
                "project_start_date": "2025-01-01",
                "project_end_date": "2025-12-31",
            }
        )

    defaults.update(kwargs)
    return Salary.objects.create(**defaults)


def assert_response_not_server_error(response, test_case):
    """Assert response doesn't have 500 server error and provide debug info if it does.

    Use this in tests that previously had unexpected 500 errors.
    """
    if response.status_code >= 500:
        test_case.fail(
            f"Unexpected server error {response.status_code}: "
            f"{response.content.decode()[:500]}..."
        )
