#!/usr/bin/env python3
"""
Quick fix for employment types
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from users.models import Employee

print("Fixing employment types...")

# Fix problem employees specifically (those with empty employment_type)
problem_employees = Employee.objects.filter(id__in=[51, 52, 56, 58])

for emp in problem_employees:
    try:
        salary = emp.salary_info
        if salary.calculation_type == 'monthly':
            emp.employment_type = 'full_time'
        else:
            emp.employment_type = 'hourly'
        emp.save()
        print(f"✅ Fixed {emp.get_full_name()}: {emp.employment_type}")
    except Exception as e:
        print(f"❌ Error: {e}")

print("Done!")