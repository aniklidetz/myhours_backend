#!/usr/bin/env python3
"""
Create superuser for testing biometric system
"""

import os
import sys
import django

# Setup Django
sys.path.append('/Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from django.contrib.auth.models import User
from users.models import Employee

def create_test_superuser():
    """Create superuser and employee for testing"""
    
    # Create superuser
    username = 'admin'
    email = 'admin@myhours.com'
    password = 'admin123'
    
    # Delete existing
    User.objects.filter(username=username).delete()
    
    # Create new
    user = User.objects.create_superuser(
        username=username,
        email=email,
        password=password,
        first_name='Admin',
        last_name='User'
    )
    
    # Create employee profile
    employee = Employee.objects.create(
        user=user,
        first_name='Admin',
        last_name='User',
        email=email,
        role='admin'
    )
    
    print(f"✅ Created superuser: {username}")
    print(f"   Password: [hidden]")
    print(f"   Employee ID: {employee.id}")
    print(f"   Email: {email}")
    print()
    print("🌐 Access Django Admin at: http://localhost:8000/admin/")
    print("📊 Access API stats at: http://localhost:8000/api/biometrics/management/stats/")
    print()
    
    # Create regular test user
    test_username = 'testuser'
    test_email = 'test@myhours.com'
    test_password = 'test123'
    
    User.objects.filter(username=test_username).delete()
    
    test_user = User.objects.create_user(
        username=test_username,
        email=test_email,
        password=test_password,
        first_name='Test',
        last_name='Employee'
    )
    
    test_employee = Employee.objects.create(
        user=test_user,
        first_name='Test',
        last_name='Employee',
        email=test_email,
        role='employee'
    )
    
    print(f"✅ Created test user: {test_username}")
    print(f"   Password: [hidden]")
    print(f"   Employee ID: {test_employee.id}")
    print(f"   Email: {test_email}")
    
    return user, employee, test_user, test_employee

if __name__ == "__main__":
    create_test_superuser()