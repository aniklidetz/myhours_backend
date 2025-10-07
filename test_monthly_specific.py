#!/usr/bin/env python
"""
Simple test runner to check specific monthly employee tests
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings_ci')
django.setup()

from datetime import datetime
from decimal import Decimal
from django.utils import timezone
from django.test import TestCase
from users.models import Employee
from payroll.models import Salary
from worktime.models import WorkLog
from payroll.services.payroll_service import PayrollService
from payroll.services.contracts import CalculationContext
from payroll.services.enums import CalculationStrategy

def test_monthly_sabbath_daytime():
    """Test that reproduces the failing test."""
    print("=== Testing Monthly Sabbath Daytime ===")

    # Clean up
    WorkLog.objects.all().delete()
    Employee.objects.all().delete()

    # Create monthly employee
    employee = Employee.objects.create(
        email='monthly_test@example.com',
        first_name='Monthly',
        last_name='Test',
        employment_type='full_time',
        role='employee'
    )

    salary = Salary.objects.create(
        employee=employee,
        calculation_type='monthly',
        base_salary=Decimal('25000.00'),
        currency='ILS',
        is_active=True
    )

    # Create Saturday shift (Sabbath daytime)
    check_in = timezone.make_aware(datetime(2025, 7, 5, 9, 0))  # Saturday 9:00
    check_out = timezone.make_aware(datetime(2025, 7, 5, 17, 0))  # Saturday 17:00 (8h)

    WorkLog.objects.create(
        employee=employee,
        check_in=check_in,
        check_out=check_out
    )

    # Calculate payroll
    context = CalculationContext(
        employee_id=employee.id,
        year=2025,
        month=7,
        user_id=1,
        force_recalculate=True
    )

    service = PayrollService()
    result = service.calculate(context, CalculationStrategy.ENHANCED)

    print(f"Result keys: {list(result.keys())}")
    print(f"Total salary: {result.get('total_salary', 'N/A')}")
    print(f"Total hours: {result.get('total_hours', 'N/A')}")
    print(f"Sabbath hours: {result.get('shabbat_hours', 'N/A')}")

    if 'breakdown' in result:
        breakdown = result['breakdown']
        print(f"Breakdown keys: {list(breakdown.keys())}")
        print(f"Base monthly salary: {breakdown.get('base_monthly_salary', 'N/A')}")
        print(f"Total bonuses monthly: {breakdown.get('total_bonuses_monthly', 'N/A')}")
        print(f"Proportional base: {breakdown.get('proportional_base', 'N/A')}")
        print(f"Sabbath pay: {breakdown.get('sabbath_pay', 'N/A')}")

    # Expected calculation for Saturday 8h work:
    # Monthly salary: 25000
    # Effective hourly rate: 25000/182 ≈ 137.36
    # Sabbath premium: 8h * 137.36 * 50% = 549.44
    # Total expected: 25000 + 549.44 = 25549.44

    expected_monthly_salary = 25000.0
    effective_hourly_rate = 25000.0 / 182  # ≈ 137.36
    sabbath_premium = 8.0 * effective_hourly_rate * 0.50  # ≈ 549.44
    expected_total = expected_monthly_salary + sabbath_premium

    print(f"\n=== Expected Calculation ===")
    print(f"Base monthly salary: {expected_monthly_salary}")
    print(f"Effective hourly rate: {effective_hourly_rate:.2f}")
    print(f"Sabbath premium (8h * {effective_hourly_rate:.2f} * 50%): {sabbath_premium:.2f}")
    print(f"Expected total: {expected_total:.2f}")

    actual_total = float(result.get('total_salary', 0))
    difference = actual_total - expected_total

    print(f"\n=== Comparison ===")
    print(f"Actual total: {actual_total:.2f}")
    print(f"Expected total: {expected_total:.2f}")
    print(f"Difference: {difference:.2f}")
    print(f"Difference %: {(difference/expected_total*100):.1f}%")

    return result

if __name__ == '__main__':
    test_monthly_sabbath_daytime()