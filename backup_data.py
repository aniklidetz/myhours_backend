#!/usr/bin/env python3
"""
Simple backup script to preserve important data
"""
import os
import sys
import json
import datetime

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
sys.path.insert(0, '/app')

import django
django.setup()

from django.contrib.auth.models import User
from users.models import Employee
from payroll.models import Salary
from worktime.models import WorkLog

def backup_data():
    """Create backup of essential data"""
    backup_time = datetime.datetime.now().isoformat()
    
    backup_data = {
        'timestamp': backup_time,
        'users': [],
        'employees': [],
        'salaries': [],
        'worklogs': []
    }
    
    # Backup users
    for user in User.objects.all():
        backup_data['users'].append({
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'date_joined': user.date_joined.isoformat(),
            'last_login': user.last_login.isoformat() if user.last_login else None
        })
    
    # Backup employees
    for employee in Employee.objects.all():
        backup_data['employees'].append({
            'user_username': employee.user.username,
            'first_name': employee.first_name,
            'last_name': employee.last_name,
            'email': employee.email,
            'phone': employee.phone,
            'employment_type': employee.employment_type,
            'hourly_rate': str(employee.hourly_rate),
            'role': employee.role,
            'created_at': employee.created_at.isoformat(),
            'updated_at': employee.updated_at.isoformat()
        })
    
    # Backup salaries
    for salary in Salary.objects.all():
        backup_data['salaries'].append({
            'employee_email': salary.employee.email,
            'calculation_type': salary.calculation_type,
            'base_salary': str(salary.base_salary) if salary.base_salary else None,
            'hourly_rate': str(salary.hourly_rate) if salary.hourly_rate else None,
            'overtime_rate': str(salary.overtime_rate) if salary.overtime_rate else None,
            'effective_date': salary.effective_date.isoformat()
        })
    
    # Backup recent work logs (last 30 days)
    thirty_days_ago = datetime.datetime.now() - datetime.timedelta(days=30)
    for worklog in WorkLog.objects.filter(created_at__gte=thirty_days_ago):
        backup_data['worklogs'].append({
            'employee_email': worklog.employee.email,
            'check_in': worklog.check_in.isoformat(),
            'check_out': worklog.check_out.isoformat() if worklog.check_out else None,
            'date': worklog.date.isoformat(),
            'hours_worked': str(worklog.hours_worked) if worklog.hours_worked else None,
            'is_approved': worklog.is_approved,
            'created_at': worklog.created_at.isoformat()
        })
    
    # Save backup
    backup_filename = f"/app/backups/backup_{backup_time.replace(':', '-')}.json"
    os.makedirs('/app/backups', exist_ok=True)
    
    with open(backup_filename, 'w') as f:
        json.dump(backup_data, f, indent=2)
    
    print(f"✅ Backup created: {backup_filename}")
    print(f"📊 Backed up: {len(backup_data['users'])} users, {len(backup_data['employees'])} employees, {len(backup_data['salaries'])} salaries, {len(backup_data['worklogs'])} work logs")
    
    return backup_filename

if __name__ == '__main__':
    backup_data()