#!/usr/bin/env python
"""
Database setup script for MyHours
Handles migrations, initial data, and test users
"""
import os
import sys
import django
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from django.core.management import call_command
from django.contrib.auth.models import User
from users.models import Employee
from datetime import datetime, timedelta
from django.utils import timezone


def run_migrations():
    """Run database migrations"""
    print("🔄 Running database migrations...")
    try:
        call_command('migrate', verbosity=2)
        print("✅ Migrations completed successfully!")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)


def create_superuser():
    """Create admin superuser if not exists"""
    if not User.objects.filter(username='admin').exists():
        print("👤 Creating superuser...")
        user = User.objects.create_superuser(
            username='admin',
            email='admin@myhours.com',
            password='admin123',
            first_name='System',
            last_name='Administrator'
        )
        
        # Create Employee profile for admin
        Employee.objects.create(
            user=user,
            first_name='System',
            last_name='Administrator',
            email='admin@myhours.com',
            role='ADMIN',
            employment_type='FULL_TIME',
            hourly_rate=100.00
        )
        print("✅ Superuser created: admin@myhours.com / admin123")
    else:
        print("ℹ️  Superuser already exists")


def create_test_users():
    """Create test users with different roles"""
    test_users = [
        {
            'username': 'john.doe',
            'email': 'john.doe@company.com',
            'password': 'test123',
            'first_name': 'John',
            'last_name': 'Doe',
            'role': 'EMPLOYEE',
            'hourly_rate': 50.00,
            'employment_type': 'FULL_TIME'
        },
        {
            'username': 'jane.smith',
            'email': 'jane.smith@company.com',
            'password': 'test123',
            'first_name': 'Jane',
            'last_name': 'Smith',
            'role': 'EMPLOYEE',
            'hourly_rate': 45.00,
            'employment_type': 'PART_TIME'
        },
        {
            'username': 'bob.accountant',
            'email': 'bob@company.com',
            'password': 'test123',
            'first_name': 'Bob',
            'last_name': 'Johnson',
            'role': 'ACCOUNTANT',
            'hourly_rate': 70.00,
            'employment_type': 'FULL_TIME'
        },
        {
            'username': 'alice.manager',
            'email': 'alice@company.com',
            'password': 'test123',
            'first_name': 'Alice',
            'last_name': 'Williams',
            'role': 'ADMIN',
            'hourly_rate': 90.00,
            'employment_type': 'FULL_TIME'
        }
    ]
    
    print("\n👥 Creating test users...")
    for user_data in test_users:
        if not User.objects.filter(username=user_data['username']).exists():
            # Create Django user
            user = User.objects.create_user(
                username=user_data['username'],
                email=user_data['email'],
                password=user_data['password'],
                first_name=user_data['first_name'],
                last_name=user_data['last_name']
            )
            
            # Set staff status for admin/accountant roles
            if user_data['role'] in ['ADMIN', 'ACCOUNTANT']:
                user.is_staff = True
                if user_data['role'] == 'ADMIN':
                    user.is_superuser = True
                user.save()
            
            # Create Employee profile
            Employee.objects.create(
                user=user,
                first_name=user_data['first_name'],
                last_name=user_data['last_name'],
                email=user_data['email'],
                phone=f'+1555{user.id:04d}',
                role=user_data['role'],
                employment_type=user_data['employment_type'],
                hourly_rate=user_data['hourly_rate']
            )
            
            print(f"✅ Created {user_data['role']}: {user_data['email']} (password set)")
        else:
            print(f"ℹ️  User already exists: {user_data['username']}")


def create_sample_worklogs():
    """Create sample work logs for testing"""
    from worktime.models import WorkLog
    
    print("\n📊 Creating sample work logs...")
    
    employees = Employee.objects.filter(role='EMPLOYEE')
    if not employees.exists():
        print("⚠️  No employees found to create work logs")
        return
    
    # Create work logs for the past 7 days
    for employee in employees[:2]:  # Just first 2 employees
        for days_ago in range(7):
            date = timezone.now().date() - timedelta(days=days_ago)
            
            # Skip weekends
            if date.weekday() >= 5:
                continue
            
            # Check if worklog already exists
            existing = WorkLog.objects.filter(
                employee=employee,
                check_in__date=date
            ).exists()
            
            if not existing:
                # Create morning check-in
                check_in = timezone.make_aware(
                    datetime.combine(date, datetime.min.time().replace(hour=9))
                )
                check_out = check_in + timedelta(hours=8, minutes=30)
                
                WorkLog.objects.create(
                    employee=employee,
                    check_in=check_in,
                    check_out=check_out,
                    location_check_in='Office',
                    location_check_out='Office',
                    is_approved=days_ago > 2  # Approve older entries
                )
    
    print("✅ Sample work logs created")


def create_sample_salaries():
    """Create sample salary records"""
    from payroll.models import Salary
    
    print("\n💰 Creating sample salary records...")
    
    employees = Employee.objects.all()
    for employee in employees:
        if not Salary.objects.filter(employee=employee).exists():
            # Set calculation type based on employment type
            calc_type = 'monthly' if employee.employment_type == 'FULL_TIME' else 'hourly'
            
            Salary.objects.create(
                employee=employee,
                base_salary=employee.hourly_rate * 160,  # Monthly base
                hourly_rate=employee.hourly_rate,
                calculation_type=calc_type,
                currency='ILS'  # Israeli Shekel as default
            )
    
    print("✅ Sample salary records created")


def sync_holidays():
    """Sync holidays from external API"""
    print("\n📅 Syncing holidays...")
    try:
        from integrations.services.hebcal_service import HebcalService
        current_year = datetime.now().year
        created, updated = HebcalService.sync_holidays_to_db(current_year)
        print(f"✅ Holidays synced: {created} created, {updated} updated")
    except Exception as e:
        print(f"⚠️  Holiday sync failed (non-critical): {e}")


def main():
    """Main setup function"""
    print("🚀 Setting up MyHours database...\n")
    
    # Run migrations
    run_migrations()
    
    # Create users
    create_superuser()
    create_test_users()
    
    # Create sample data
    create_sample_worklogs()
    create_sample_salaries()
    
    # Sync external data
    sync_holidays()
    
    print("\n✨ Database setup completed!")
    print("\n📝 Login credentials:")
    print("=" * 50)
    print("Admin:      admin@myhours.com / admin123")
    print("Manager:    alice@company.com / test123")
    print("Accountant: bob@company.com / test123")
    print("Employee:   john.doe@company.com / test123")
    print("Employee:   jane.smith@company.com / test123")
    print("=" * 50)


if __name__ == '__main__':
    main()