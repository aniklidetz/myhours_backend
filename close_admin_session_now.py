#!/usr/bin/env python3
"""
Emergency script to close admin's long-running session
Run this from the Django project root directory
"""

import os
import sys
import django

# Setup Django
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from django.contrib.auth.models import User
from users.models import Employee
from worktime.models import WorkLog
from django.utils import timezone

def close_admin_session():
    print("🔄 Closing admin's active session...")
    
    # Look for admin sessions with common admin emails
    admin_emails = ['admin@example.com', 'admin@myhours.com', 'admin2@example.com']
    
    closed_sessions = 0
    
    for email in admin_emails:
        try:
            # Find active sessions for this admin email
            admin_sessions = WorkLog.objects.filter(
                check_out__isnull=True,
                employee__email=email
            )
            
            for session in admin_sessions:
                duration = session.get_total_hours()
                print(f"Found admin session: {email}")
                print(f"  Session ID: {session.id}")
                print(f"  Duration: {duration:.2f} hours")
                print(f"  Started: {session.check_in}")
                
                if duration > 100:  # 100+ hours is definitely a forgotten session
                    print(f"  🔴 LONG SESSION DETECTED - Closing session {session.id}")
                    session.check_out = timezone.now()
                    session.save()
                    closed_sessions += 1
                    print(f"  ✅ Session {session.id} closed successfully")
                elif duration > 12:  # 12+ hours might be forgotten
                    print(f"  ⚠️  Long session ({duration:.2f}h) - consider closing manually")
                else:
                    print(f"  ℹ️  Recent session - keeping active")
                    
        except Employee.DoesNotExist:
            print(f"No employee found with email: {email}")
            continue
    
    if closed_sessions == 0:
        print("No long-running admin sessions found to close.")
    else:
        print(f"✅ Closed {closed_sessions} admin session(s)")

if __name__ == "__main__":
    try:
        close_admin_session()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()