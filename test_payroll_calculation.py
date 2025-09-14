#!/usr/bin/env python

import os
import sys
import django
from datetime import datetime, date
from decimal import Decimal

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')

# Add the project root to the Python path
sys.path.append('/Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend')

django.setup()

from users.models import Employee
from payroll.services.payroll_service import PayrollService
from payroll.models import MonthlyPayrollSummary

def test_payroll_calculation():
    print("Testing payroll calculation for all active employees...")
    
    try:
        # Get all active employees
        employees = Employee.objects.filter(is_active=True)[:5]  # Test first 5 employees
        if not employees:
            print("ERROR: No active employees found")
            return
        
        print(f"Found {len(employees)} active employees to test")
        
        # Test September calculations
        year = 2025
        month = 9
        
        print(f"Testing calculations for {month}/{year}...")
        
        from payroll.services.contracts import CalculationContext
        from payroll.services.enums import CalculationStrategy, EmployeeType
        
        service = PayrollService()
        
        for employee in employees:
            print(f"\n--- Testing {employee.get_full_name()} (ID: {employee.id}) ---")
            
            # Check existing calculation
            existing = MonthlyPayrollSummary.objects.filter(
                employee=employee,
                year=year,
                month=month
            ).first()
            
            if existing:
                print(f"Existing: {existing.total_gross_pay} ILS ({existing.total_hours}h)")
            else:
                print("No existing calculation")
            
            # Run new calculation
            context = CalculationContext(
                employee_id=employee.id,
                year=year,
                month=month,
                user_id=1,  # Admin user for testing
                employee_type=EmployeeType.MONTHLY if employee.employment_type == 'monthly' else EmployeeType.HOURLY,
                force_recalculate=True,
                fast_mode=False
            )
            
            try:
                result = service.calculate(context, CalculationStrategy.ENHANCED)
                
                if isinstance(result, dict) and 'total_salary' in result:
                    print(f"Calculated: {result['total_salary']} ILS ({result['total_hours']}h)")
                    
                    # Check if saved
                    updated = MonthlyPayrollSummary.objects.filter(
                        employee=employee,
                        year=year,
                        month=month
                    ).first()
                    
                    if updated:
                        print(f"Saved: {updated.total_gross_pay} ILS")
                    else:
                        print("ERROR: Not saved to database")
                else:
                    print(f"Unexpected result format: {result}")
                    
            except Exception as calc_error:
                print(f"Calculation error: {calc_error}")
                import traceback
                traceback.print_exc()
            
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_payroll_calculation()