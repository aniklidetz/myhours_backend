#!/usr/bin/env python
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from users.models import Employee
from django.contrib.auth.models import User

def reset_mishka_password():
    try:
        # Find Mishka's employee record
        employee = Employee.objects.filter(email='mikhail.plotnik@gmail.com').first()
        if not employee:
            print("❌ Employee with email mikhail.plotnik@gmail.com not found")
            return
            
        print(f"✅ Found employee: {employee.first_name} {employee.last_name} (ID: {employee.id})")
        
        # Check if employee has a Django user account
        if hasattr(employee, 'user') and employee.user:
            user = employee.user
            print(f"✅ Found Django user: {user.username}")
        else:
            # Create Django user if it doesn't exist
            print("⚠️ No Django user found, creating one...")
            user = User.objects.create_user(
                username=employee.email,
                email=employee.email,
                first_name=employee.first_name,
                last_name=employee.last_name
            )
            employee.user = user
            employee.save()
            print(f"✅ Created Django user: {user.username}")
        
        # Set a simple password
        new_password = 'password123'
        user.set_password(new_password)
        user.save()
        
        print(f"✅ Password reset successful!")
        print(f"📧 Email: {employee.email}")
        print(f"🔑 New password: [set successfully]")
        print(f"👤 Role: {employee.role}")
        
    except Exception as e:
        print(f"❌ Error resetting password: {e}")

if __name__ == '__main__':
    reset_mishka_password()