#!/usr/bin/env python
"""
Simple test to check if our enhanced strategy works
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

def test_simple():
    """Simple test."""
    print("=== Simple Payroll Test ===")

    try:
        # Clean up
        WorkLog.objects.all().delete()
        Employee.objects.all().delete()

        # Create hourly employee (should work)
        employee = Employee.objects.create(
            email='hourly_test@example.com',
            first_name='Hourly',
            last_name='Test',
            employment_type='full_time',
            role='employee'
        )

        # Try without is_active field first
        salary = Salary(
            employee=employee,
            calculation_type='hourly',
            hourly_rate=Decimal('100.00'),
            currency='ILS'
        )

        # Check available fields
        print(f"Salary model fields: {[f.name for f in Salary._meta.fields]}")

        # Try to save
        salary.save()
        print("✅ Salary saved successfully")

        # Create simple work log
        check_in = timezone.make_aware(datetime(2025, 7, 5, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 5, 17, 0))  # 8h

        WorkLog.objects.create(
            employee=employee,
            check_in=check_in,
            check_out=check_out
        )
        print("✅ WorkLog created successfully")

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
        print("✅ Payroll calculated successfully")

        print(f"Total salary: {result.get('total_salary', 'N/A')}")
        print(f"Total hours: {result.get('total_hours', 'N/A')}")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    test_simple()