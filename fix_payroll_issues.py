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

def fix_all_august_calculations():
    print("=== Fixing All August 2025 Calculations ===\n")
    
    employees = Employee.objects.filter(is_active=True)
    service = PayrollService()
    
    for employee in employees:
        print(f"Fixing {employee.get_full_name()}...")
        
        # Check if they have work logs for August
        work_logs = WorkLog.objects.filter(
            employee=employee,
            check_in__year=2025,
            check_in__month=8,
            check_out__isnull=False
        )
        
        if not work_logs.exists():
            print(f"  No work logs - skipping")
            continue
            
        total_hours = sum(log.get_total_hours() for log in work_logs)
        print(f"  Work logs: {work_logs.count()}, Total hours: {total_hours}")
        
        # Get current monthly summary
        current = MonthlyPayrollSummary.objects.filter(
            employee=employee, year=2025, month=8
        ).first()
        
        if current:
            print(f"  Current: {current.total_gross_pay} ILS")
        
        try:
            # Force recalculation
            context = CalculationContext(
                employee_id=employee.id,
                year=2025,
                month=8,
                user_id=1,
                employee_type=EmployeeType.MONTHLY if employee.employment_type == 'monthly' else EmployeeType.HOURLY,
                force_recalculate=True,
                fast_mode=False
            )
            result = service.calculate(context, CalculationStrategy.ENHANCED)
            
            print(f"  New calculation: {result['total_salary']} ILS")
            
            # Verify it was saved
            updated = MonthlyPayrollSummary.objects.filter(
                employee=employee, year=2025, month=8
            ).first()
            
            if updated:
                print(f"  Saved: {updated.total_gross_pay} ILS")
                if abs(float(updated.total_gross_pay) - float(result['total_salary'])) > 1:
                    print(f"  WARNING: Save mismatch!")
            else:
                print(f"  ERROR: Not saved to database")
                
        except Exception as e:
            print(f"  ERROR: {e}")
    
    print("\n=== Summary ===")
    summaries = MonthlyPayrollSummary.objects.filter(year=2025, month=8)
    for summary in summaries:
        print(f"{summary.employee.get_full_name()}: {summary.total_gross_pay} ILS ({summary.total_hours}h)")

if __name__ == "__main__":
    fix_all_august_calculations()