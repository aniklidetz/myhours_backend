#!/usr/bin/env python
"""
Script to search for admin user's current work session in the database
"""
import os
import sys
import django

# Add the project path to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from users.models import Employee
from worktime.models import WorkLog
from django.contrib.auth.models import User
from django.utils import timezone

def search_admin_sessions():
    """Search for admin user's active work sessions"""
    print("=== Searching for Admin User's Active Work Sessions ===\n")
    
    # First, try to find admin user by email
    admin_emails = ['admin@myhours.com', 'admin@example.com', 'admin2@example.com', 'admin@localhost', 'admin@admin.com']
    admin_user = None
    admin_employee = None
    
    for email in admin_emails:
        try:
            admin_user = User.objects.get(email=email)
            print(f"✓ Admin user found: {admin_user.username} ({admin_user.email})")
            break
        except User.DoesNotExist:
            continue
    
    if not admin_user:
        print("⚠️  Admin user not found by standard emails. Checking all users with 'admin' in email...")
        admin_users = User.objects.filter(email__icontains='admin')
        if admin_users.exists():
            print(f"Found {admin_users.count()} users with 'admin' in email:")
            for user in admin_users:
                print(f"  - {user.username} ({user.email}) - Staff: {user.is_staff}, Superuser: {user.is_superuser}")
                if user.is_superuser:
                    admin_user = user
                    print(f"  → Using this user as admin: {user.email}")
                    break
    
    if admin_user:
        # Check for employee profile
        if hasattr(admin_user, 'employee_profile'):
            admin_employee = admin_user.employee_profile
            print(f"✓ Admin employee profile: {admin_employee.get_full_name()} - Role: {admin_employee.role}")
        else:
            # Try to find employee by email
            try:
                admin_employee = Employee.objects.get(email=admin_user.email)
                print(f"✓ Admin employee found by email: {admin_employee.get_full_name()} - Role: {admin_employee.role}")
            except Employee.DoesNotExist:
                print("❌ No admin employee profile found")
    
    if not admin_employee:
        # Last resort: check all employees with admin role
        admin_employees = Employee.objects.filter(role='admin')
        if admin_employees.exists():
            print(f"\nFound {admin_employees.count()} employees with admin role:")
            for emp in admin_employees:
                print(f"  - {emp.get_full_name()} ({emp.email})")
                if not admin_employee:
                    admin_employee = emp
                    print(f"  → Using this employee: {emp.email}")
    
    if admin_employee:
        print(f"\n=== Active Work Sessions for {admin_employee.get_full_name()} ===")
        
        # Find active work sessions (check_in without check_out)
        active_sessions = WorkLog.objects.filter(
            employee=admin_employee,
            check_out__isnull=True
        ).order_by('-check_in')
        
        print(f"Active work sessions found: {active_sessions.count()}")
        
        if active_sessions.exists():
            for i, session in enumerate(active_sessions, 1):
                print(f"\n📍 Session #{i}:")
                print(f"   ID: {session.id}")
                print(f"   Started: {session.check_in}")
                print(f"   Duration: {session.get_total_hours()} hours")
                print(f"   Location: [location data hidden]")
                print(f"   Notes: [private notes hidden]")
                print(f"   Status: {session.get_status()}")
        else:
            print("✓ No active work sessions found")
        
        # Also show recent completed sessions for context
        recent_sessions = WorkLog.objects.filter(
            employee=admin_employee,
            check_out__isnull=False
        ).order_by('-check_in')[:5]
        
        if recent_sessions.exists():
            print(f"\n=== Recent Completed Sessions (last 5) ===")
            for i, session in enumerate(recent_sessions, 1):
                print(f"  {i}. {session.check_in.strftime('%Y-%m-%d %H:%M')} to {session.check_out.strftime('%H:%M')} ({session.get_total_hours()}h)")
    
    else:
        print("❌ No admin employee found in the system")

def suggest_close_session_methods():
    """Suggest methods to close active sessions"""
    print(f"\n=== Methods to Close Active Work Sessions ===")
    print("1. Django Admin Interface:")
    print("   - Go to /admin/worktime/worklog/")
    print("   - Find the active session (check_out is None)")
    print("   - Edit and set check_out time")
    
    print("\n2. API Endpoint:")
    print("   - POST /api/worktime/worklogs/{id}/")
    print("   - Set check_out field to current timestamp")
    
    print("\n3. Quick Checkout API:")
    print("   - POST /api/worktime/worklogs/quick_checkout/")
    print("   - Include employee_id in request body")
    
    print("\n4. Django Shell:")
    print("   python manage.py shell")
    print("   >>> from worktime.models import WorkLog")
    print("   >>> from django.utils import timezone")
    print("   >>> session = WorkLog.objects.get(id=SESSION_ID)")
    print("   >>> session.check_out = timezone.now()")
    print("   >>> session.save()")
    
    print("\n5. Database Direct Query (if needed):")
    print("   UPDATE worktime_worklog SET check_out = NOW() WHERE id = SESSION_ID;")

if __name__ == "__main__":
    try:
        search_admin_sessions()
        suggest_close_session_methods()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()