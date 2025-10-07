#!/usr/bin/env python
"""
Debug script to analyze calculation differences in critical points algorithm.
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings_ci')
django.setup()

from datetime import datetime, date
from decimal import Decimal
from django.utils import timezone
from users.models import Employee
from payroll.models import Salary
from worktime.models import WorkLog
from payroll.services.payroll_service import PayrollService
from payroll.services.contracts import CalculationContext
from payroll.services.enums import CalculationStrategy
from integrations.models import Holiday

def analyze_calculation():
    print("=== CALCULATION ANALYSIS ===")

    # Clean up first
    WorkLog.objects.all().delete()
    Employee.objects.all().delete()

    # Create employee and salary
    employee = Employee.objects.create(
        email='test@test.com',
        first_name='Test',
        last_name='Employee',
        employment_type='full_time',
        role='employee'
    )

    salary = Salary.objects.create(
        employee=employee,
        calculation_type='hourly',
        hourly_rate=Decimal('100.00'),
        currency='ILS'
    )

    # Create Holiday records (same as in test)
    friday_holiday, created = Holiday.objects.get_or_create(
        date=date(2025, 1, 17),
        defaults={'name': 'Shabbat', 'is_shabbat': True}
    )
    saturday_holiday, created = Holiday.objects.get_or_create(
        date=date(2025, 1, 18),
        defaults={'name': 'Shabbat', 'is_shabbat': True}
    )

    # Create work shift: friday 11:00 to friday 20:00 (9 hours)
    start_dt = timezone.make_aware(datetime(2025, 1, 17, 11, 0))  # Friday 11:00
    end_dt = timezone.make_aware(datetime(2025, 1, 17, 20, 0))    # Friday 20:00

    worklog = WorkLog.objects.create(
        employee=employee,
        check_in=start_dt,
        check_out=end_dt
    )

    print(f"Work Period: Friday 11:00-20:00")
    print(f"Duration: {(end_dt - start_dt).total_seconds() / 3600:.1f} hours")
    print(f"Hourly Rate: {salary.hourly_rate} ILS/hour")
    print(f"Employee Type: {salary.calculation_type}")
    print()

    # Calculate payroll
    context = CalculationContext(
        employee_id=employee.id,
        year=2025,
        month=1,
        user_id=1,
        force_recalculate=True
    )

    payroll_service = PayrollService()
    result = payroll_service.calculate(context, CalculationStrategy.ENHANCED)

    print("=== PAYROLL RESULT ===")
    important_fields = [
        'total_salary', 'total_hours', 'regular_hours', 'overtime_hours',
        'shabbat_hours', 'holiday_hours', 'night_hours'
    ]

    for key in important_fields:
        if key in result:
            print(f"{key}: {result[key]}")

    if 'breakdown' in result:
        print("\n=== BREAKDOWN ===")
        breakdown = result['breakdown']
        for key, value in breakdown.items():
            print(f"{key}: {value}")

    print(f"\n=== COMPARISON ===")
    print(f"Expected: 1075.00 ILS")
    print(f"Actual: {result.get('total_salary', 0):.2f} ILS")
    difference = float(result.get('total_salary', 0)) - 1075.0
    print(f"Difference: {difference:.2f} ILS ({difference/1075.0*100:.1f}%)")

    # Check Holiday detection
    print(f"\n=== HOLIDAY DETECTION ===")
    print(f"Friday (2025-01-17) Holiday: {friday_holiday.name}, is_shabbat: {friday_holiday.is_shabbat}")
    print(f"Saturday (2025-01-18) Holiday: {saturday_holiday.name}, is_shabbat: {saturday_holiday.is_shabbat}")

    # Calculate what we EXPECT based on old logic
    print(f"\n=== EXPECTED CALCULATION ANALYSIS ===")
    hours = 9.0
    rate = 100.0

    # Regular 8.6 hours at normal rate
    regular_hours = min(hours, 8.6)
    regular_pay = regular_hours * rate
    print(f"Regular hours: {regular_hours} @ {rate} = {regular_pay} ILS")

    # Overtime (if any)
    overtime_hours = max(0, hours - 8.6)
    overtime_pay = overtime_hours * rate * 1.25  # 125% rate
    print(f"Overtime hours: {overtime_hours} @ {rate * 1.25} = {overtime_pay} ILS")

    # Expected total (without Sabbath premium)
    expected_without_sabbath = regular_pay + overtime_pay
    print(f"Expected without Sabbath: {expected_without_sabbath} ILS")

    # If Friday is treated as Sabbath (150% premium)
    sabbath_pay = hours * rate * 1.5
    print(f"If Friday counted as Sabbath: {sabbath_pay} ILS")

    print(f"\nThe difference suggests Friday is being treated as Sabbath!")

if __name__ == '__main__':
    analyze_calculation()