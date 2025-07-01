#!/usr/bin/env python
"""
Quick password reset script for MyHours users
Run this from the Django project root directory
"""

import os
import sys
import django

# Add the project directory to Python path
sys.path.append('/Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend')

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from users.models import Employee
from django.contrib.auth.models import User

def reset_user_passwords():
    """Reset passwords for all main users"""
    
    users_to_reset = [
        ('admin@example.com', 'admin123'),
        ('mikhail.plotnik@gmail.com', 'password123'),
        ('accountant1@example.com', 'password123'),
        ('employee1@example.com', 'password123'),
    ]
    
    print("🔄 Resetting user passwords...")
    
    for email, password in users_to_reset:
        try:
            # Find employee
            employee = Employee.objects.filter(email=email).first()
            if not employee:
                print(f"❌ Employee {email} not found")
                continue
                
            print(f"✅ Found: {employee.first_name} {employee.last_name}")
            
            # Get or create Django user
            if hasattr(employee, 'user') and employee.user:
                user = employee.user
            else:
                user = User.objects.filter(email=email).first()
                if not user:
                    user = User.objects.create_user(
                        username=email,
                        email=email,
                        first_name=employee.first_name,
                        last_name=employee.last_name
                    )
                    employee.user = user
                    employee.save()
            
            # Set password
            user.set_password(password)
            user.save()
            
            print(f"✅ Password reset for {email} (password updated)")
            
        except Exception as e:
            print(f"❌ Error resetting {email}: {e}")
    
    print("\n🎯 Credentials updated - use the default test passwords")

if __name__ == '__main__':
    reset_user_passwords()