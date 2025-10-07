#!/usr/bin/env python
"""
Final test for monthly employee calculations with corrected logic.
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings_ci')
django.setup()

from datetime import datetime
from decimal import Decimal
from django.utils import timezone
from users.models import Employee
from payroll.models import Salary
from worktime.models import WorkLog
from payroll.services.payroll_service import PayrollService
from payroll.services.contracts import CalculationContext
from payroll.services.enums import CalculationStrategy

def test_all_monthly_scenarios():
    """Test all monthly employee scenarios with corrected expectations."""

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

    service = PayrollService()
    monthly_salary = 25000.0
    rate = monthly_salary / 182  # ~137.36

    print("="*60)
    print("MONTHLY EMPLOYEE CALCULATION TESTS")
    print("="*60)
    print(f"Base Monthly Salary: {monthly_salary} ILS")
    print(f"Effective Hourly Rate: {rate:.2f} ILS/hour")
    print("-"*60)

    tests = [
        {
            'name': 'Regular 8h day',
            'date': datetime(2025, 7, 1, 9, 0),  # Tuesday
            'hours': 8,
            'expected_premiums': 0.0,  # No premiums
            'description': 'Regular day - no premiums'
        },
        {
            'name': '10h with overtime',
            'date': datetime(2025, 7, 3, 9, 0),  # Thursday
            'hours': 10,
            'expected_premiums': 1.4 * rate * 0.25,  # 1.4h OT @ 25%
            'description': '1.4h overtime @ 25% premium'
        },
        {
            'name': '12h with two-tier overtime',
            'date': datetime(2025, 7, 4, 8, 0),  # Friday
            'hours': 12,
            'expected_premiums': 2.0 * rate * 0.25 + 1.4 * rate * 0.50,  # 2h @ 25% + 1.4h @ 50%
            'description': '2h OT1 @ 25% + 1.4h OT2 @ 50%'
        },
        {
            'name': 'Saturday 8h (Sabbath)',
            'date': datetime(2025, 7, 5, 9, 0),  # Saturday
            'hours': 8,
            'expected_premiums': 8.0 * rate * 0.50,  # 8h @ 50% Sabbath
            'description': '8h Sabbath @ 50% premium'
        },
        {
            'name': 'Saturday 12h (Sabbath + OT)',
            'date': datetime(2025, 7, 12, 8, 0),  # Saturday
            'hours': 12,
            'expected_premiums': 8.6 * rate * 0.50 + 2.0 * rate * 0.75 + 1.4 * rate * 1.00,
            'description': '8.6h @ 50% + 2h @ 75% + 1.4h @ 100%'
        },
    ]

    passed = 0
    failed = 0

    for test in tests:
        # Clean worklogs
        WorkLog.objects.filter(employee=employee).delete()

        # Create worklog
        check_in = timezone.make_aware(test['date'])
        check_out = timezone.make_aware(
            datetime(test['date'].year, test['date'].month, test['date'].day,
                    test['date'].hour + test['hours'], test['date'].minute)
        )

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

        result = service.calculate(context, CalculationStrategy.ENHANCED)

        # Expected total = Monthly salary + premiums
        expected_total = monthly_salary + test['expected_premiums']
        actual_total = float(result.get('total_salary', 0))
        difference = actual_total - expected_total
        percent_diff = (difference / expected_total * 100) if expected_total != 0 else 0

        print(f"\n{test['name']}")
        print(f"  Description: {test['description']}")
        print(f"  Expected premiums: {test['expected_premiums']:.2f} ILS")
        print(f"  Expected total: {expected_total:.2f} ILS")
        print(f"  Actual total: {actual_total:.2f} ILS")
        print(f"  Difference: {difference:.2f} ILS ({percent_diff:.1f}%)")

        # Check if within tolerance (2 ILS)
        if abs(difference) <= 2.0:
            print(f"  ✅ PASS")
            passed += 1
        else:
            print(f"  ❌ FAIL - Difference too large!")
            failed += 1

            # Print breakdown for debugging
            if 'breakdown' in result:
                breakdown = result['breakdown']
                print(f"  Breakdown:")
                print(f"    - base_monthly_salary: {breakdown.get('base_monthly_salary', 'N/A')}")
                print(f"    - total_bonuses_monthly: {breakdown.get('total_bonuses_monthly', 'N/A')}")
                print(f"    - proportional_base: {breakdown.get('proportional_base', 'N/A')}")

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"✅ Passed: {passed}/{len(tests)}")
    print(f"❌ Failed: {failed}/{len(tests)}")

    return passed == len(tests)

if __name__ == '__main__':
    try:
        success = test_all_monthly_scenarios()
        if not success:
            print("\n⚠️  Some tests failed!")
            exit(1)
        else:
            print("\n🎉 All tests passed!")
    except Exception as e:
        print(f"\n💥 Error: {e}")
        import traceback
        traceback.print_exc()
        exit(2)