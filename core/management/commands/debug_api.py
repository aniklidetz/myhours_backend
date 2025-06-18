from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from users.models import Employee, EnhancedDeviceToken
from worktime.models import WorkLog
from payroll.models import Salary
from datetime import datetime, timedelta
import requests

User = get_user_model()

class Command(BaseCommand):
    help = 'Debug API and database issues'

    def handle(self, *args, **options):
        self.stdout.write("🔍 API & Database Diagnostic Tool")
        self.stdout.write("=" * 50)
        
        # 1. Database check
        self.check_database_data()
        
        # 2. Create test data if needed
        self.create_test_data()
        
        # 3. Test API
        self.test_api_endpoints()
        
        self.stdout.write("=" * 50)
        self.stdout.write(self.style.SUCCESS("✅ Diagnostic complete!"))

    def check_database_data(self):
        self.stdout.write("\n👥 DATABASE CHECK:")
        self.stdout.write(f"Users: {User.objects.count()}")
        for user in User.objects.all()[:3]:
            self.stdout.write(f"  - {user.email} ({user.first_name} {user.last_name})")
        
        self.stdout.write(f"Employees: {Employee.objects.count()}")
        for emp in Employee.objects.all()[:3]:
            self.stdout.write(f"  - {emp.first_name} {emp.last_name} ({emp.role})")
        
        self.stdout.write(f"WorkLogs: {WorkLog.objects.count()}")
        self.stdout.write(f"Salaries: {Salary.objects.count()}")
        self.stdout.write(f"Active tokens: {EnhancedDeviceToken.objects.filter(is_active=True).count()}")

    def create_test_data(self):
        self.stdout.write("\n🏗️  CREATING TEST DATA:")
        
        # Create test users
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
                self.stdout.write(f"✅ Created user: {user.email}")
            
            # Create Employee record
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
                self.stdout.write(f"✅ Created employee: {employee.email}")

        # Create test work logs if none exist
        if WorkLog.objects.count() < 3:
            employees = Employee.objects.all()[:2]
            for emp in employees:
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
            self.stdout.write(f"✅ Created work logs. Total: {WorkLog.objects.count()}")

        # Create test salaries if none exist
        if Salary.objects.count() < 3:
            employees = Employee.objects.all()
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
            self.stdout.write(f"✅ Created salaries. Total: {Salary.objects.count()}")

    def test_api_endpoints(self):
        self.stdout.write("\n🔗 API ENDPOINTS TEST:")
        
        try:
            # Test health endpoint
            response = requests.get("http://127.0.0.1:8000/api/health/", timeout=5)
            self.stdout.write(f"Health check: {response.status_code}")
            
            # Test login
            admin_user = User.objects.filter(is_superuser=True).first()
            if admin_user:
                login_data = {
                    "email": admin_user.email,
                    "password": "admin123",
                    "device_id": "test_device_123",
                    "device_info": {
                        "platform": "test",
                        "os_version": "1.0",
                        "app_version": "1.0.0",
                        "device_model": "Test Device",
                        "device_id": "test_device_123"
                    }
                }
                
                response = requests.post("http://127.0.0.1:8000/api/v1/users/auth/enhanced-login/", 
                                       json=login_data, timeout=5)
                self.stdout.write(f"Login: {response.status_code}")
                
                if response.status_code == 200:
                    token = response.json().get('token')
                    headers = {'Authorization': f'DeviceToken {token}'}
                    
                    # Test other endpoints
                    endpoints = [
                        ('/api/v1/users/employees/', 'Employees'),
                        ('/api/v1/worktime/worklogs/', 'Work Time'),
                        ('/api/v1/payroll/salaries/', 'Payroll')
                    ]
                    
                    for url, name in endpoints:
                        try:
                            resp = requests.get(f"http://127.0.0.1:8000{url}", headers=headers, timeout=5)
                            count = len(resp.json().get('results', [])) if resp.status_code == 200 else 0
                            self.stdout.write(f"{name}: {resp.status_code} (count: {count})")
                        except Exception as e:
                            self.stdout.write(f"{name}: ERROR - {e}")
                else:
                    self.stdout.write(f"Login failed: {response.text}")
                    
        except Exception as e:
            self.stdout.write(f"API test failed: {e}")
            self.stdout.write("Make sure Django server is running on port 8000")