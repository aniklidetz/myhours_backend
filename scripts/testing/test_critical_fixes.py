#!/usr/bin/env python
"""
Test script for critical fixes: Issues #1, #2, #6
Tests N+1 query optimizations and service references
"""

import os
import sys
from datetime import date, datetime
from decimal import Decimal

import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myhours.settings")
django.setup()

import pytest
import pytz

from django.conf import settings
from django.db import connection, reset_queries
from django.utils import timezone

from payroll.models import Salary
from users.models import Employee
from worktime.models import WorkLog

# Apply django_db mark to all tests in this module
pytestmark = pytest.mark.django_db


@pytest.fixture
def test_employee_with_salary(db):
    """Create a test employee with active salary for testing."""
    employee = Employee.objects.create(
        first_name="Test",
        last_name="Worker",
        email="test.worker@example.com",
        employment_type="hourly",
        role="employee",
    )
    salary = Salary.objects.create(
        employee=employee,
        calculation_type="hourly",
        hourly_rate=80,
        currency="ILS",
        is_active=True,
    )
    return salary


@pytest.fixture
def test_employee_with_worklogs(db):
    """Create a test employee with work logs for testing."""
    employee = Employee.objects.create(
        first_name="Test",
        last_name="Logger",
        email="test.logger@example.com",
        employment_type="hourly",
        role="employee",
    )
    salary = Salary.objects.create(
        employee=employee,
        calculation_type="hourly",
        hourly_rate=80,
        currency="ILS",
        is_active=True,
    )
    # Create some work logs
    from django.utils import timezone as tz

    check_in = tz.make_aware(datetime(2025, 7, 1, 9, 0))
    check_out = tz.make_aware(datetime(2025, 7, 1, 17, 0))
    WorkLog.objects.create(
        employee=employee,
        check_in=check_in,
        check_out=check_out,
    )
    return salary


def test_issue_1_working_days_optimization(test_employee_with_salary):
    """Test Issue #1: get_working_days_in_month() optimization"""
    print("\n" + "=" * 80)
    print("TEST #1: get_working_days_in_month() - N+1 Query Fix")
    print("=" * 80)

    salary = test_employee_with_salary

    employee_name = salary.employee.get_full_name()
    print(f"\nTesting with employee: {employee_name}")
    print(f"Salary ID: {salary.id}")

    # Test for July 2025
    year, month = 2025, 7

    # Enable query counting
    settings.DEBUG = True
    reset_queries()

    # Call the optimized method
    working_days = salary.get_working_days_in_month(year, month)

    # Count queries
    query_count = len(connection.queries)

    print(f"\nResults for {year}-{month:02d}:")
    print(f"  Working days: {working_days}")
    print(f"  Database queries executed: {query_count}")

    # Check timezone handling
    israel_tz = pytz.timezone("Asia/Jerusalem")
    test_date = timezone.datetime(2025, 7, 15, tzinfo=israel_tz).date()
    print(f"  Israeli timezone test date: {test_date}")
    print(
        f"  Timezone: {test_date.tzinfo if hasattr(test_date, 'tzinfo') else 'Applied during calculation'}"
    )

    # Validation - assert query count is optimal
    assert query_count <= 2, f"Too many queries ({query_count}). Expected <=2"
    print("\nPASS: Query count is optimal (<=2 queries)")

    # Working days should be reasonable for July 2025
    assert working_days >= 20, f"Working days {working_days} seems too low for July"
    assert (
        working_days <= 31
    ), f"Working days {working_days} cannot exceed days in month"


def test_issue_2_worked_days_optimization(test_employee_with_worklogs):
    """Test Issue #2: get_worked_days_in_month() optimization"""
    print("\n" + "=" * 80)
    print("TEST #2: get_worked_days_in_month() - values() Optimization")
    print("=" * 80)

    salary = test_employee_with_worklogs

    employee_name = salary.employee.get_full_name()
    work_log_count = WorkLog.objects.filter(
        employee=salary.employee, check_out__isnull=False
    ).count()

    print(f"\nTesting with employee: {employee_name}")
    print(f"Total work logs: {work_log_count}")

    # Test for July 2025
    year, month = 2025, 7

    # Enable query counting
    settings.DEBUG = True
    reset_queries()

    # Call the optimized method
    worked_days = salary.get_worked_days_in_month(year, month)

    # Count queries
    query_count = len(connection.queries)

    print(f"\nResults for {year}-{month:02d}:")
    print(f"  Worked days: {worked_days}")
    print(f"  Database queries executed: {query_count}")

    # Validation - assert query count is optimal
    assert query_count <= 2, f"Too many queries ({query_count}). Expected <=2"
    print("\nPASS: Query count is optimal (<=2 queries)")

    # We created 1 work log for July 1st, so worked_days should be at least 1
    assert worked_days >= 1, f"Worked days {worked_days} should be at least 1"


def test_issue_6_payroll_service_reference():
    """Test Issue #6: PayrollService reference in backward_compatible_earnings"""
    import inspect

    # Check imports in the function
    from payroll.services.contracts import CalculationContext
    from payroll.services.enums import CalculationStrategy, EmployeeType
    from payroll.services.payroll_service import PayrollService

    # Get the source file path dynamically for the earnings_views module
    from payroll.views import earnings_views

    # Import the view function - this also validates the import works
    from payroll.views.earnings_views import backward_compatible_earnings

    views_file = inspect.getfile(earnings_views)

    with open(views_file, "r") as f:
        content = f.read()

    # Check for old broken reference
    assert "PayrollCalculationService" not in content or all(
        line.strip().startswith("#")
        for line in content.split("\n")
        if "PayrollCalculationService" in line
    ), "Found PayrollCalculationService reference in earnings_views.py"

    # Check for new correct reference
    assert (
        "PayrollService()" in content
    ), "PayrollService() not found in earnings_views.py"

    # Check for CalculationContext usage
    assert (
        "CalculationContext(" in content
    ), "CalculationContext not found in earnings_views.py"

    # Check for CalculationStrategy usage
    assert (
        "CalculationStrategy.ENHANCED" in content
    ), "CalculationStrategy.ENHANCED not found"
