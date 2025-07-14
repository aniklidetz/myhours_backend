#!/usr/bin/env python
"""Check which employees don't have salary records"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from users.models import Employee
from payroll.models import Salary

print("Checking salary records...\n")

# Get all active employees
employees = Employee.objects.filter(is_active=True).order_by('id')
print(f"Total active employees: {employees.count()}\n")

# Check each employee
missing_salary = []
has_salary = []

from core.logging_utils import mask_name
for emp in employees:
    try:
        salary = emp.salary_info
        has_salary.append(emp)
        print(f"✅ {mask_name(emp.get_full_name())} (ID: [REDACTED]) - Has salary: {salary.calculation_type}")
    except Salary.DoesNotExist:
        missing_salary.append(emp)
        print(f"❌ {mask_name(emp.get_full_name())} (ID: [REDACTED]) - NO SALARY RECORD")

print(f"\n\nSummary:")
print(f"Employees with salary: {len(has_salary)}")
print(f"Employees WITHOUT salary: {len(missing_salary)}")

if missing_salary:
    print("\nEmployees missing salary configuration:")
    for emp in missing_salary:
        print(f"  - {mask_name(emp.get_full_name())} (ID: [REDACTED], Role: {emp.role})")