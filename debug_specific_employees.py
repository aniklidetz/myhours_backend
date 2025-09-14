#!/usr/bin/env python

import os
import sys
import django
from datetime import datetime, date
from decimal import Decimal

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
sys.path.append('/Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend')
django.setup()

from users.models import Employee
from payroll.models import MonthlyPayrollSummary, DailyPayrollCalculation
from worktime.models import WorkLog
from payroll.services.payroll_service import PayrollService
from payroll.services.contracts import CalculationContext
from payroll.services.enums import CalculationStrategy, EmployeeType

def debug_yosef():
    print("=== Debugging Yosef Abramov ===\n")
    
    yosef = Employee.objects.filter(first_name='Yosef', last_name='Abramov').first()
    if not yosef:
        print("Yosef not found")
        return
    
    print(f"Employee: {yosef.get_full_name()} (ID: {yosef.id})")
    print(f"Employment type: {yosef.employment_type}")
    
    # Check salary info
    from payroll.models import Salary
    salary = Salary.objects.filter(employee=yosef, is_active=True).first()
    if salary:
        print(f"Base salary: {salary.base_salary} ILS")
        print(f"Hourly rate: {salary.hourly_rate} ILS")
    
    # August work logs
    work_logs = WorkLog.objects.filter(
        employee=yosef,
        check_in__year=2025,
        check_in__month=8,
        check_out__isnull=False
    ).order_by('check_in')
    
    print(f"\nWork logs: {work_logs.count()}")
    total_hours = Decimal('0')
    for log in work_logs:
        hours = log.get_total_hours()
        total_hours += hours
        print(f"  {log.check_in.date()}: {hours} hours")
    
    print(f"Total hours: {total_hours}")
    
    # Monthly summary
    monthly = MonthlyPayrollSummary.objects.filter(
        employee=yosef, year=2025, month=8
    ).first()
    if monthly:
        print(f"\nMonthly summary: {monthly.total_gross_pay} ILS")
    
    # Daily calculations
    daily_calcs = DailyPayrollCalculation.objects.filter(
        employee=yosef,
        work_date__year=2025,
        work_date__month=8
    )
    print(f"\nDaily calculations: {daily_calcs.count()}")
    for calc in daily_calcs:
        print(f"  {calc.work_date}: {calc.total_pay} ILS")
    
    # Try manual calculation
    print(f"\n--- Manual Recalculation ---")
    try:
        service = PayrollService()
        context = CalculationContext(
            employee_id=yosef.id,
            year=2025,
            month=8,
            user_id=1,
            employee_type=EmployeeType.MONTHLY if yosef.employment_type == 'monthly' else EmployeeType.HOURLY,
            force_recalculate=True,
            fast_mode=False
        )
        result = service.calculate(context, CalculationStrategy.ENHANCED)
        print(f"Recalculated: {result['total_salary']} ILS")
        print(f"Hours breakdown: regular={result['regular_hours']}, overtime={result['overtime_hours']}")
        
        if 'breakdown' in result:
            breakdown = result['breakdown']
            print("Detailed breakdown:")
            for key, value in breakdown.items():
                if isinstance(value, (int, float, Decimal)) and value != 0:
                    print(f"  {key}: {value}")
                    
    except Exception as e:
        print(f"Calculation error: {e}")
        import traceback
        traceback.print_exc()

def debug_dana():
    print("\n\n=== Debugging Dana Azulay ===\n")
    
    dana = Employee.objects.filter(first_name='Dana', last_name='Azulay').first()
    if not dana:
        print("Dana not found")
        return
    
    print(f"Employee: {dana.get_full_name()} (ID: {dana.id})")
    print(f"Employment type: {dana.employment_type}")
    
    # Check salary info
    from payroll.models import Salary
    salary = Salary.objects.filter(employee=dana, is_active=True).first()
    if salary:
        print(f"Base salary: {salary.base_salary} ILS")
        print(f"Hourly rate: {salary.hourly_rate} ILS")
    
    # August work logs
    work_logs = WorkLog.objects.filter(
        employee=dana,
        check_in__year=2025,
        check_in__month=8,
        check_out__isnull=False
    ).order_by('check_in')
    
    print(f"\nWork logs: {work_logs.count()}")
    total_hours = Decimal('0')
    for log in work_logs:
        hours = log.get_total_hours()
        total_hours += hours
        print(f"  {log.check_in.date()}: {hours} hours")
    
    print(f"Total hours: {total_hours}")
    
    # Monthly summary
    monthly = MonthlyPayrollSummary.objects.filter(
        employee=dana, year=2025, month=8
    ).first()
    if monthly:
        print(f"\nMonthly summary: {monthly.total_gross_pay} ILS")
        print(f"Regular hours: {monthly.regular_hours}")
        print(f"Overtime hours: {monthly.overtime_hours}")
    
    # Daily calculations
    daily_calcs = DailyPayrollCalculation.objects.filter(
        employee=dana,
        work_date__year=2025,
        work_date__month=8
    )
    print(f"\nDaily calculations: {daily_calcs.count()}")
    
    # Check if the new system is supposed to create daily calculations
    print(f"\n--- Checking Enhanced Strategy Daily Creation ---")
    
    # Manual calculation with debug
    print(f"\n--- Manual Recalculation ---")
    try:
        service = PayrollService()
        context = CalculationContext(
            employee_id=dana.id,
            year=2025,
            month=8,
            user_id=1,
            employee_type=EmployeeType.MONTHLY if dana.employment_type == 'monthly' else EmployeeType.HOURLY,
            force_recalculate=True,
            fast_mode=False
        )
        result = service.calculate(context, CalculationStrategy.ENHANCED)
        print(f"Recalculated: {result['total_salary']} ILS")
        print(f"Hours breakdown: regular={result['regular_hours']}, overtime={result['overtime_hours']}")
        
    except Exception as e:
        print(f"Calculation error: {e}")
        import traceback
        traceback.print_exc()

def check_system_logic():
    print("\n\n=== Checking System Logic ===\n")
    
    # Check if enhanced strategy creates daily calculations
    from payroll.services.strategies.enhanced import EnhancedPayrollStrategy
    
    print("Enhanced strategy methods:")
    methods = [method for method in dir(EnhancedPayrollStrategy) if not method.startswith('_')]
    for method in methods:
        print(f"  {method}")
    
    # Check if there's a method to create daily calculations
    has_daily_creation = hasattr(EnhancedPayrollStrategy, '_create_daily_calculation')
    print(f"\nHas daily calculation creation: {has_daily_creation}")
    
    # Check old vs new system
    print(f"\nSystem comparison:")
    print("Old system: Creates both MonthlyPayrollSummary AND DailyPayrollCalculation")
    print("New system: Creates only MonthlyPayrollSummary")
    print("This explains why Dana has monthly but no daily calculations")

if __name__ == "__main__":
    debug_yosef()
    debug_dana()
    check_system_logic()