#!/usr/bin/env python
"""
Script to change password for mikhail.plotnik@gmail.com
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

try:
    user = User.objects.get(email='mikhail.plotnik@gmail.com')
    user.set_password('pes12345')
    user.save()
    print(f"✅ Password changed for {user.email}")
    
    # Test the password
    from django.contrib.auth import authenticate
    test_user = authenticate(username='mikhail.plotnik@gmail.com', password='pes12345')
    if test_user:
        print("✅ Password verification successful")
    else:
        print("❌ Password verification failed")
        
except User.DoesNotExist:
    print("❌ User mikhail.plotnik@gmail.com not found")
except Exception as e:
    print(f"❌ Error: {e}")