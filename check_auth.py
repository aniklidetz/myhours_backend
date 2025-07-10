#!/usr/bin/env python3
"""
Check authentication and create test session
"""

import os
import sys
import django
from django.contrib.auth import authenticate

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from django.contrib.auth.models import User
from users.models import Employee

def check_users():
    """Check available users and their credentials"""
    
    print("=== AVAILABLE USERS ===")
    
    # Check test users
    test_users = User.objects.filter(email__endswith='@test.com')
    
    for user in test_users:
        print(f"\nUsername: {user.username}")
        print(f"Email: {user.email}")
        print(f"Active: {user.is_active}")
        print(f"Staff: {user.is_staff}")
        print(f"Superuser: {user.is_superuser}")
        
        # Test password 'test123'
        auth_user = authenticate(username=user.username, password='test123')
        if auth_user:
            print(f"✅ Password 'test123' works")
        else:
            print(f"❌ Password 'test123' doesn't work")
            
        # Check if has employee profile
        try:
            employee = user.employee_profile
            print(f"Employee ID: {employee.id}")
            print(f"Role: {employee.role}")
        except:
            print("❌ No employee profile")

def get_admin_user():
    """Get admin user for testing"""
    print("\n=== ADMIN USERS ===")
    
    admin_users = User.objects.filter(is_superuser=True)
    
    for user in admin_users:
        print(f"\nAdmin: {user.username} ({user.email})")
        
        # Test password
        auth_user = authenticate(username=user.username, password='test123')
        if auth_user:
            print(f"✅ Password 'test123' works")
            return user
        else:
            # Try empty password
            auth_user = authenticate(username=user.username, password='')
            if auth_user:
                print(f"✅ Empty password works")
                return user
            else:
                print(f"❌ Need to reset password")
    
    return None

if __name__ == "__main__":
    check_users()
    admin_user = get_admin_user()
    
    if admin_user:
        print(f"\n✅ Use admin user: {admin_user.username}")
        print(f"Login at: http://localhost:8000/admin/")
    else:
        print(f"\n❌ No working admin user found")