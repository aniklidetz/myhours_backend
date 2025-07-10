#!/usr/bin/env python3
"""
Check specific problem employees in detail
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from users.models import Employee
from payroll.models import Salary
from decimal import Decimal

def check_specific_employees():
    """Check the specific employees causing errors"""
    
    problem_ids = [52, 56, 58]  # 51 works
    
    print("=== DETAILED CHECK OF PROBLEM EMPLOYEES ===")
    
    for emp_id in problem_ids:
        print(f"\n--- Employee {emp_id} ---")
        
        try:
            emp = Employee.objects.get(id=emp_id)
            print(f"Name: {emp.get_full_name()}")
            print(f"Email: {emp.email}")
            print(f"Role: {emp.role}")
            
            # Check salary
            try:
                salary = emp.salary_info
                print(f"✅ Salary exists")
                print(f"  Calculation type: {salary.calculation_type}")
                print(f"  Base salary: {salary.base_salary}")
                print(f"  Hourly rate: {salary.hourly_rate}")
                print(f"  Currency: {salary.currency}")
                
                # Test the specific fix
                hourly_rate_fixed = salary.hourly_rate or Decimal('0')
                print(f"  Fixed hourly rate: {hourly_rate_fixed}")
                
                # Test multiplication
                try:
                    test_mult = hourly_rate_fixed * Decimal('1.25')
                    print(f"  ✅ Multiplication test: {test_mult}")
                except Exception as e:
                    print(f"  ❌ Multiplication failed: {e}")
                    
                # Check if they have any work logs
                from worktime.models import WorkLog
                work_logs = WorkLog.objects.filter(employee=emp).count()
                print(f"  Work logs count: {work_logs}")
                
                # Check if they have work logs in July 2025
                july_logs = WorkLog.objects.filter(
                    employee=emp,
                    check_in__year=2025,
                    check_in__month=7
                ).count()
                print(f"  July 2025 logs: {july_logs}")
                
            except Salary.DoesNotExist:
                print(f"❌ NO SALARY RECORD")
                
        except Employee.DoesNotExist:
            print(f"❌ Employee {emp_id} not found")
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_specific_employees()