#!/usr/bin/env python

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
sys.path.append('/Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend')
django.setup()

from django.core.management import execute_from_command_line

def create_unified_fields_migration():
    """Create migration to unify payroll fields"""
    print("Creating migration for unified payroll fields...")
    
    # Create empty migration
    execute_from_command_line([
        'manage.py', 
        'makemigrations', 
        'payroll', 
        '--empty',
        '--name', 
        'unify_daily_payroll_fields'
    ])
    
    print("Migration created. Please edit it manually to:")
    print("1. Add overtime_pay field (sum of overtime_pay_1 + overtime_pay_2)")
    print("2. Add holiday_pay field")  
    print("3. Add sabbath_pay field")
    print("4. Update data from old fields to new unified fields")
    print("5. Remove old duplicate fields (base_pay, bonus_pay)")

if __name__ == "__main__":
    create_unified_fields_migration()