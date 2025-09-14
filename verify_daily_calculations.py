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

def check_daily_calculations():
    print("=== Checking Daily Calculations After Enhancement ===\n")
    
    employees = Employee.objects.filter(is_active=True)
    
    for employee in employees:
        daily_calcs = DailyPayrollCalculation.objects.filter(
            employee=employee,
            work_date__year=2025,
            work_date__month=8
        )
        
        print(f"{employee.get_full_name()}: {daily_calcs.count()} daily calculations")
        
        # Show first few records
        for calc in daily_calcs[:3]:
            print(f"  {calc.work_date}: {calc.total_pay} ILS ({calc.regular_hours}h reg + {calc.overtime_hours_1}h OT1 + {calc.overtime_hours_2}h OT2)")

if __name__ == "__main__":
    check_daily_calculations()