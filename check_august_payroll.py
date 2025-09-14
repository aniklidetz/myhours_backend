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

def check_august_payroll():
    print("=== Checking August 2025 Payroll Status ===\n")
    
    # Get all active employees
    employees = Employee.objects.filter(is_active=True)
    print(f"Found {employees.count()} active employees\n")
    
    year = 2025
    month = 8
    
    # Check existing calculations
    existing_summaries = MonthlyPayrollSummary.objects.filter(year=year, month=month)
    print(f"Existing August summaries: {existing_summaries.count()}")
    
    for employee in employees:
        print(f"\n--- {employee.get_full_name()} (ID: {employee.id}) ---")
        
        # Check work logs for August
        work_logs = WorkLog.objects.filter(
            employee=employee,
            check_in__year=year,
            check_in__month=month,
            check_out__isnull=False
        )
        print(f"Work logs: {work_logs.count()}")
        
        if work_logs.exists():
            total_hours = sum(log.get_total_hours() for log in work_logs)
            print(f"Total hours: {total_hours}")
            
            # Check monthly summary
            monthly_summary = MonthlyPayrollSummary.objects.filter(
                employee=employee, year=year, month=month
            ).first()
            
            if monthly_summary:
                print(f"Monthly summary: {monthly_summary.total_gross_pay} ILS")
            else:
                print("NO MONTHLY SUMMARY - Need to calculate")
                
                # Try to calculate
                try:
                    service = PayrollService()
                    context = CalculationContext(
                        employee_id=employee.id,
                        year=year,
                        month=month,
                        user_id=1,
                        employee_type=EmployeeType.MONTHLY if employee.employment_type == 'monthly' else EmployeeType.HOURLY,
                        force_recalculate=True,
                        fast_mode=False
                    )
                    result = service.calculate(context, CalculationStrategy.ENHANCED)
                    print(f"Calculated: {result['total_salary']} ILS")
                except Exception as e:
                    print(f"Calculation failed: {e}")
            
            # Check daily calculations
            daily_calcs = DailyPayrollCalculation.objects.filter(
                employee=employee,
                work_date__year=year,
                work_date__month=month
            )
            print(f"Daily calculations: {daily_calcs.count()}")
            
        else:
            print("No work logs for August")

def check_daily_model():
    print("\n=== Checking Daily Payroll Calculation Model ===\n")
    
    # Check model fields using Django introspection
    from django.db import connection
    
    try:
        # PostgreSQL syntax for table info
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'payroll_dailypayrollcalculation'
                ORDER BY ordinal_position;
            """)
            fields = cursor.fetchall()
            
            print("Daily Payroll Calculation table structure:")
            for field in fields:
                print(f"  {field[0]}: {field[1]}")
    except Exception as e:
        print(f"Could not get table structure: {e}")
        
        # Alternative: check model fields
        fields = [f.name for f in DailyPayrollCalculation._meta.get_fields()]
        print("Model fields:", fields)
    
    # Check sample data
    daily_calcs = DailyPayrollCalculation.objects.all()[:5]
    print(f"\nTotal daily calculations in DB: {DailyPayrollCalculation.objects.count()}")
    print(f"Sample daily calculations (showing first 5):")
    for calc in daily_calcs:
        try:
            print(f"  {calc.employee.get_full_name()}: {calc.work_date} - {calc.total_pay} ILS")
        except AttributeError as e:
            print(f"  Field error: {e}")

def recalculate_missing_august():
    print("\n=== Recalculating Missing August Payrolls ===\n")
    
    employees_with_zero = Employee.objects.filter(
        is_active=True,
        monthly_payroll_summaries__year=2025,
        monthly_payroll_summaries__month=8,
        monthly_payroll_summaries__total_gross_pay=0
    )
    
    print(f"Employees with 0.00 ILS August salary: {employees_with_zero.count()}")
    
    service = PayrollService()
    
    for employee in employees_with_zero:
        print(f"\nRecalculating for {employee.get_full_name()}...")
        
        try:
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
        except Exception as e:
            print(f"  Calculation failed: {e}")

if __name__ == "__main__":
    check_august_payroll()
    check_daily_model()
    recalculate_missing_august()