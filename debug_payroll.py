#!/usr/bin/env python
"""Debug payroll issues for specific employees"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from users.models import Employee
from payroll.models import Salary
from datetime import date

print("=== DEBUGGING PAYROLL ISSUES ===\n")

# Check specific employees mentioned
problem_employees = ['Elior Weisman', 'Leah Ben-Ami', 'Noam Peretz', 'Gilad Friedman']

for name in problem_employees:
    print(f"\n--- Checking {name} ---")
    first, last = name.split()
    
    try:
        emp = Employee.objects.get(first_name=first, last_name=last)
        print(f"✓ Employee found: ID={emp.id}, Role={emp.role}, Active={emp.is_active}")
        
        # Check salary
        try:
            salary = emp.salary_info
            if salary:
                print(f"✓ Salary exists: {salary.calculation_type}, "
                      f"Rate: {salary.hourly_rate or salary.base_salary} {salary.currency}")
            else:
                print("✗ salary_info returned None")
        except Exception as e:
            print(f"✗ Error getting salary: {e}")
            
        # Check if Salary record exists directly
        salary_count = Salary.objects.filter(employee=emp).count()
        print(f"  Direct query: {salary_count} salary record(s) found")
        
    except Employee.DoesNotExist:
        print(f"✗ Employee NOT FOUND in database")

# Check total counts
print(f"\n\n=== TOTALS ===")
print(f"Total Employees: {Employee.objects.filter(is_active=True).count()}")
print(f"Total Salary records: {Salary.objects.count()}")

# Check for employees without salary
employees_without_salary = []
for emp in Employee.objects.filter(is_active=True):
    if not Salary.objects.filter(employee=emp).exists():
        employees_without_salary.append(emp)

if employees_without_salary:
    print(f"\n⚠️  {len(employees_without_salary)} employees WITHOUT salary:")
    for emp in employees_without_salary:
        print(f"  - {emp.get_full_name()} (ID: {emp.id})")
else:
    print("\n✓ All employees have salary records")