#!/usr/bin/env python
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
sys.path.insert(0, os.getcwd())
django.setup()

from django.contrib.auth.models import User
from users.models import Employee

# Проверяем Employee с ID 15
employee = Employee.objects.get(id=15)
print(f'Employee 15: {employee.get_full_name()}')
print(f'Employee user: {employee.user}')

# Проверяем есть ли связь
admin_user = User.objects.get(email='admin@example.com')
print(f'Admin user: {admin_user}')

if admin_user != employee.user:
    # Привязываем Employee к admin user
    employee.user = admin_user
    employee.save()
    print('✅ Employee привязан к admin user')
else:
    print('✅ Employee уже привязан')

print("Done!")