#!/usr/bin/env python

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
sys.path.append('/Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend')
django.setup()

from users.models import Employee
from payroll.models import DailyPayrollCalculation

def verify_all_daily_calculations():
    print("=== Verifying All August Daily Calculations ===\n")
    
    employees = Employee.objects.filter(is_active=True)
    
    for employee in employees:
        daily_calcs = DailyPayrollCalculation.objects.filter(
            employee=employee,
            work_date__year=2025,
            work_date__month=8
        ).order_by('work_date')
        
        print(f"{employee.get_full_name()}: {daily_calcs.count()} daily calculations")
        
        zero_pay_count = daily_calcs.filter(total_gross_pay=0).count()
        total_daily_pay = sum(calc.total_gross_pay for calc in daily_calcs)
        
        if zero_pay_count > 0:
            print(f"  ❌ {zero_pay_count} records with 0.00 pay")
        else:
            print(f"  ✅ All records have pay amounts")
            
        print(f"  Total daily pay: {total_daily_pay} ILS")
        
        # Show first record as example
        if daily_calcs.exists():
            first_calc = daily_calcs.first()
            print(f"  Example: {first_calc.work_date} - base={first_calc.base_pay}, bonus={first_calc.bonus_pay}, total={first_calc.total_gross_pay}")
        print()

if __name__ == "__main__":
    verify_all_daily_calculations()