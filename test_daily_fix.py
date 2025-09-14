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
from payroll.services.payroll_service import PayrollService
from payroll.services.contracts import CalculationContext
from payroll.services.enums import CalculationStrategy, EmployeeType

def test_daily_calculation_fix():
    print("Testing daily calculation fix for Yosef Abramov...")
    
    # Get Yosef Abramov
    yosef = Employee.objects.filter(first_name='Yosef', last_name='Abramov').first()
    if not yosef:
        print("Yosef not found")
        return
    
    print(f"Testing for {yosef.get_full_name()}")
    
    # Check current daily calculations
    current_dailies = DailyPayrollCalculation.objects.filter(
        employee=yosef,
        work_date__year=2025,
        work_date__month=8
    ).order_by('work_date')
    
    print(f"Current daily calculations: {current_dailies.count()}")
    for calc in current_dailies[:3]:
        print(f"  {calc.work_date}: base={calc.base_pay}, bonus={calc.bonus_pay}, total_gross={calc.total_gross_pay}")
    
    # Recalculate August to trigger daily calculation fix
    service = PayrollService()
    context = CalculationContext(
        employee_id=yosef.id,
        year=2025,
        month=8,
        user_id=1,
        employee_type=EmployeeType.HOURLY,
        force_recalculate=True,
        fast_mode=False
    )
    
    try:
        result = service.calculate(context, CalculationStrategy.ENHANCED)
        print(f"Recalculation completed: {result['total_salary']} ILS")
        
        # Check updated daily calculations
        updated_dailies = DailyPayrollCalculation.objects.filter(
            employee=yosef,
            work_date__year=2025,
            work_date__month=8
        ).order_by('work_date')
        
        print(f"Updated daily calculations: {updated_dailies.count()}")
        for calc in updated_dailies[:3]:
            print(f"  {calc.work_date}: base={calc.base_pay}, bonus={calc.bonus_pay}, total_gross={calc.total_gross_pay}")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_daily_calculation_fix()