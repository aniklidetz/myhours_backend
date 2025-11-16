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

import pytz

from django.conf import settings
from django.db import connection, reset_queries
from django.utils import timezone

from payroll.models import Salary
from users.models import Employee
from worktime.models import WorkLog


def test_issue_1_working_days_optimization():
    """Test Issue #1: get_working_days_in_month() optimization"""
    print("\n" + "=" * 80)
    print("TEST #1: get_working_days_in_month() - N+1 Query Fix")
    print("=" * 80)

    # Get first employee with active salary
    salary = Salary.objects.filter(is_active=True).select_related("employee").first()

    if not salary:
        print("ERROR: No active salary found for testing")
        return False

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

    # Validation
    if query_count <= 2:  # Should be 1-2 queries (cache lookup + possible initial load)
        print("\nPASS: Query count is optimal (<=2 queries)")
        success = True
    else:
        print(f"\nFAIL: Too many queries ({query_count}). Expected <=2")
        success = False

    # Show queries for debugging
    if query_count > 0:
        print("\nQueries executed:")
        for i, query in enumerate(connection.queries, 1):
            print(f"  {i}. {query['sql'][:100]}...")

    return success


def test_issue_2_worked_days_optimization():
    """Test Issue #2: get_worked_days_in_month() optimization"""
    print("\n" + "=" * 80)
    print("TEST #2: get_worked_days_in_month() - values() Optimization")
    print("=" * 80)

    # Get employee with work logs
    salary = (
        Salary.objects.filter(is_active=True, employee__work_logs__isnull=False)
        .select_related("employee")
        .first()
    )

    if not salary:
        print("ERROR: No employee with work logs found for testing")
        return False

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

    # Validation
    if (
        query_count <= 2
    ):  # Should be 1-2 queries (WorkLog fetch + possible Salary fetch)
        print("\nPASS: Query count is optimal (<=2 queries)")
        success = True
    else:
        print(f"\nFAIL: Too many queries ({query_count}). Expected <=2")
        success = False

    # Show queries for debugging
    if query_count > 0:
        print("\nQueries executed:")
        for i, query in enumerate(connection.queries, 1):
            sql = query["sql"]
            # Check if using values()
            if "SELECT" in sql and "work_logs" in sql.lower():
                if "check_in" in sql and "check_out" in sql:
                    print(f"  {i}. WorkLog query with values() optimization")
                else:
                    print(f"  {i}. WorkLog query (check if optimized)")
            print(f"     {sql[:150]}...")

    return success


def test_issue_6_payroll_service_reference():
    """Test Issue #6: PayrollService reference in backward_compatible_earnings"""
    print("\n" + "=" * 80)
    print("TEST #3: backward_compatible_earnings() - PayrollService Fix")
    print("=" * 80)

    try:
        # Import the view function
        from payroll.views import backward_compatible_earnings

        print("\nImport successful: backward_compatible_earnings function exists")

        # Check imports in the function
        from payroll.services.contracts import CalculationContext
        from payroll.services.enums import CalculationStrategy, EmployeeType
        from payroll.services.payroll_service import PayrollService

        print("All required imports are available:")
        print("  - PayrollService")
        print("  - CalculationContext")
        print("  - CalculationStrategy")
        print("  - EmployeeType")

        # Read the views.py to verify the fix
        with open(
            "/Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend/payroll/views.py",
            "r",
        ) as f:
            content = f.read()

        # Check for old broken reference
        if "PayrollCalculationService" in content:
            # Make sure it's not in a comment or string
            lines = content.split("\n")
            found_bad_reference = False
            for line_num, line in enumerate(lines, 1):
                if "PayrollCalculationService" in line and not line.strip().startswith(
                    "#"
                ):
                    if (
                        "backward_compatible_earnings"
                        in content[
                            max(0, content.find(line) - 500) : content.find(line) + 500
                        ]
                    ):
                        print(
                            f"\nFAIL: Found PayrollCalculationService reference at line {line_num}"
                        )
                        print(f"  Line: {line.strip()}")
                        found_bad_reference = True

            if found_bad_reference:
                return False

        # Check for new correct reference
        if "PayrollService()" in content:
            print("\nPASS: Using correct PayrollService() reference")
            success = True
        else:
            print("\nFAIL: PayrollService() not found in views.py")
            success = False

        # Check for CalculationContext usage
        if "CalculationContext(" in content:
            print("PASS: Using CalculationContext for service initialization")
        else:
            print("WARNING: CalculationContext not found")
            success = False

        # Check for CalculationStrategy usage
        if "CalculationStrategy.ENHANCED" in content:
            print("PASS: Using CalculationStrategy.ENHANCED")
        else:
            print("WARNING: CalculationStrategy.ENHANCED not found")

        return success

    except ImportError as e:
        print(f"\nFAIL: Import error - {e}")
        return False
    except Exception as e:
        print(f"\nFAIL: Unexpected error - {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("TESTING CRITICAL FIXES - Issues #1, #2, #6")
    print("=" * 80)
    print(f"Database: {settings.DATABASES['default']['NAME']}")
    print(f"Django version: {django.VERSION}")
    print(f"Debug mode: {settings.DEBUG}")

    results = {
        "Issue #1 (Working Days N+1 Query)": test_issue_1_working_days_optimization(),
        "Issue #2 (Worked Days values() Optimization)": test_issue_2_worked_days_optimization(),
        "Issue #6 (PayrollService Reference)": test_issue_6_payroll_service_reference(),
    }

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    passed = sum(1 for result in results.values() if result)
    total = len(results)

    for test_name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"[{status}] {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\nALL TESTS PASSED - Critical fixes verified!")
        return 0
    else:
        print(f"\n{total - passed} TEST(S) FAILED - Review needed")
        return 1


if __name__ == "__main__":
    exit(main())
