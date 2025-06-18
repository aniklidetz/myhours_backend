#!/usr/bin/env python3
"""
API Debug Script - для диагностики проблем с API и данными в БД
"""

import os
import sys
import django
import requests
import json
from datetime import datetime, timedelta

# Настраиваем Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from django.contrib.auth import get_user_model
from users.models import Employee, EnhancedDeviceToken
from worktime.models import WorkLog
from payroll.models import Salary
from core.models import OfficeSettings

User = get_user_model()

def print_section(title):
    print(f"\n{'='*50}")
    print(f" {title}")
    print(f"{'='*50}")

def check_database_data():
    """Проверяем данные в базе данных"""
    print_section("DATABASE CHECK")
    
    # Проверка пользователей
    print(f"👥 Users in database: {User.objects.count()}")
    for user in User.objects.all()[:5]:
        print(f"  - {user.email} ({user.first_name} {user.last_name}) - Staff: {user.is_staff}")
    
    # Проверка сотрудников
    print(f"\n👔 Employees in database: {Employee.objects.count()}")
    for emp in Employee.objects.all()[:5]:
        print(f"  - {emp.first_name} {emp.last_name} ({emp.email}) - Role: {emp.role}")
    
    # Проверка рабочих логов
    print(f"\n⏰ WorkLogs in database: {WorkLog.objects.count()}")
    recent_logs = WorkLog.objects.order_by('-check_in_time')[:3]
    for log in recent_logs:
        print(f"  - {log.employee.first_name if log.employee else 'Unknown'}: {log.check_in_time} -> {log.check_out_time}")
    
    # Проверка зарплат
    print(f"\n💰 Salaries in database: {Salary.objects.count()}")
    for salary in Salary.objects.all()[:3]:
        print(f"  - {salary.employee.first_name if salary.employee else 'Unknown'}: {salary.base_salary}₪ ({salary.period_start} - {salary.period_end})")
    
    # Проверка токенов
    print(f"\n🔑 Active tokens: {EnhancedDeviceToken.objects.filter(is_active=True).count()}")

def test_api_endpoints():
    """Тестируем API endpoints напрямую"""
    print_section("API ENDPOINTS TEST")
    
    base_url = "http://127.0.0.1:8000"  # Локальный адрес
    
    # Тест health endpoint
    try:
        response = requests.get(f"{base_url}/api/health/", timeout=5)
        print(f"✅ Health check: {response.status_code} - {response.json()}")
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False
    
    # Получаем токен для тестирования
    try:
        # Попробуем войти как admin
        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            print("❌ No admin user found for testing")
            return False
        
        login_data = {
            "email": admin_user.email,
            "password": "admin123",  # Стандартный пароль для теста
            "device_id": "test_device_123",
            "device_info": {
                "platform": "test",
                "os_version": "1.0",
                "app_version": "1.0.0",
                "device_model": "Test Device",
                "device_id": "test_device_123"
            }
        }
        
        response = requests.post(f"{base_url}/api/v1/users/auth/enhanced-login/", 
                               json=login_data, timeout=5)
        print(f"🔐 Login test: {response.status_code}")
        
        if response.status_code == 200:
            token = response.json().get('token')
            headers = {'Authorization': f'DeviceToken {token}'}
            
            # Тест employees endpoint
            try:
                response = requests.get(f"{base_url}/api/v1/users/employees/", 
                                      headers=headers, timeout=5)
                print(f"👥 Employees API: {response.status_code} - Count: {len(response.json().get('results', []))}")
            except Exception as e:
                print(f"❌ Employees API failed: {e}")
            
            # Тест worktime endpoint
            try:
                response = requests.get(f"{base_url}/api/v1/worktime/worklogs/", 
                                      headers=headers, timeout=5)
                print(f"⏰ Worktime API: {response.status_code} - Count: {len(response.json().get('results', []))}")
            except Exception as e:
                print(f"❌ Worktime API failed: {e}")
            
            # Тест payroll endpoint
            try:
                response = requests.get(f"{base_url}/api/v1/payroll/salaries/", 
                                      headers=headers, timeout=5)
                print(f"💰 Payroll API: {response.status_code} - Count: {len(response.json().get('results', []))}")
            except Exception as e:
                print(f"❌ Payroll API failed: {e}")
                
        else:
            print(f"❌ Login failed: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"❌ API test failed: {e}")
        return False
    
    return True

def create_test_data():
    """Создаем тестовые данные если их нет"""
    print_section("CREATING TEST DATA")
    
    # Создаем тестовых пользователей если их нет
    test_users = [
        {
            'email': 'admin@example.com',
            'first_name': 'Admin',
            'last_name': 'User',
            'role': 'admin',
            'is_staff': True,
            'is_superuser': True
        },
        {
            'email': 'mikhail.plotnik@gmail.com',
            'first_name': 'Mishka',
            'last_name': 'Plotnik', 
            'role': 'accountant',
            'is_staff': True,
            'is_superuser': False
        },
        {
            'email': 'employee1@example.com',
            'first_name': 'John',
            'last_name': 'Employee',
            'role': 'employee',
            'is_staff': False,
            'is_superuser': False
        }
    ]
    
    for user_data in test_users:
        user, created = User.objects.get_or_create(
            email=user_data['email'],
            defaults={
                'first_name': user_data['first_name'],
                'last_name': user_data['last_name'],
                'is_staff': user_data['is_staff'],
                'is_superuser': user_data['is_superuser']
            }
        )
        if created:
            user.set_password('admin123')
            user.save()
            print(f"✅ Created user: {user.email}")
        
        # Создаем Employee запись
        employee, emp_created = Employee.objects.get_or_create(
            email=user_data['email'],
            defaults={
                'first_name': user_data['first_name'],
                'last_name': user_data['last_name'],
                'role': user_data['role'],
                'user': user,
                'hourly_rate': 50.0,
                'employment_type': 'full_time'
            }
        )
        if emp_created:
            print(f"✅ Created employee: {employee.email}")
    
    # Создаем тестовые WorkLogs
    employees = Employee.objects.all()
    if employees.exists() and WorkLog.objects.count() < 5:
        print("Creating test work logs...")
        for emp in employees[:2]:  # Только для первых 2 сотрудников
            # Создаем записи за последние 3 дня
            for days_ago in range(3):
                check_in = datetime.now() - timedelta(days=days_ago, hours=8)
                check_out = check_in + timedelta(hours=8)
                
                WorkLog.objects.get_or_create(
                    employee=emp,
                    check_in_time=check_in,
                    defaults={
                        'check_out_time': check_out,
                        'location': 'Office',
                        'is_approved': True
                    }
                )
        print(f"✅ Work logs created. Total: {WorkLog.objects.count()}")
    
    # Создаем тестовые Salaries
    if employees.exists() and Salary.objects.count() < 3:
        print("Creating test salaries...")
        current_date = datetime.now()
        period_start = current_date.replace(day=1)
        
        for emp in employees:
            Salary.objects.get_or_create(
                employee=emp,
                period_start=period_start,
                defaults={
                    'period_end': period_start.replace(month=period_start.month+1) - timedelta(days=1),
                    'base_salary': 50000,
                    'status': 'draft'
                }
            )
        print(f"✅ Salaries created. Total: {Salary.objects.count()}")

def main():
    print("🔍 API & Database Diagnostic Tool")
    print("=" * 50)
    
    # 1. Проверяем данные в БД
    check_database_data()
    
    # 2. Создаем тестовые данные если нужно
    create_test_data()
    
    # 3. Тестируем API endpoints
    test_api_endpoints()
    
    print_section("DIAGNOSTIC COMPLETE")
    print("📋 Summary:")
    print(f"   - Users: {User.objects.count()}")
    print(f"   - Employees: {Employee.objects.count()}")
    print(f"   - Work Logs: {WorkLog.objects.count()}")
    print(f"   - Salaries: {Salary.objects.count()}")
    print(f"   - Active Tokens: {EnhancedDeviceToken.objects.filter(is_active=True).count()}")

if __name__ == "__main__":
    main()