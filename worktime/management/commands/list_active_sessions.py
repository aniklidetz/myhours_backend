from django.core.management.base import BaseCommand
from django.utils import timezone
from worktime.models import WorkLog
from users.models import Employee
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'List all active work sessions in the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--admin-only',
            action='store_true',
            help='Show only admin user sessions',
        )
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Show detailed information about each session',
        )

    def handle(self, *args, **options):
        self.stdout.write("=== Active Work Sessions Report ===\n")
        
        # Find all active sessions
        active_sessions = WorkLog.objects.filter(check_out__isnull=True).select_related('employee')
        
        if options['admin_only']:
            active_sessions = active_sessions.filter(employee__role='admin')
        
        if not active_sessions.exists():
            self.stdout.write(self.style.SUCCESS("✓ No active work sessions found"))
            return
        
        self.stdout.write(f"Found {active_sessions.count()} active work session(s):\n")
        
        # Group by employee for better display
        sessions_by_employee = {}
        for session in active_sessions:
            emp_id = session.employee.id
            if emp_id not in sessions_by_employee:
                sessions_by_employee[emp_id] = {
                    'employee': session.employee,
                    'sessions': []
                }
            sessions_by_employee[emp_id]['sessions'].append(session)
        
        for emp_id, emp_data in sessions_by_employee.items():
            employee = emp_data['employee']
            sessions = emp_data['sessions']
            
            self.stdout.write(f"👤 {employee.get_full_name()} ({employee.email})")
            self.stdout.write(f"   Role: {employee.get_role_display()}")
            self.stdout.write(f"   Active Sessions: {len(sessions)}")
            
            if options['detailed']:
                for i, session in enumerate(sessions, 1):
                    duration = session.get_total_hours()
                    self.stdout.write(f"   📍 Session #{i}:")
                    self.stdout.write(f"      ID: {session.id}")
                    self.stdout.write(f"      Started: {session.check_in}")
                    self.stdout.write(f"      Duration: {duration} hours")
                    self.stdout.write(f"      Location: {session.location_check_in or 'N/A'}")
                    self.stdout.write(f"      Notes: {session.notes or 'None'}")
                    
                    # Check if session is very long (over 12 hours)
                    if duration > 12:
                        self.stdout.write(
                            self.style.WARNING(f"      ⚠️  Long session detected ({duration} hours)")
                        )
            else:
                for session in sessions:
                    duration = session.get_total_hours()
                    warning = " ⚠️" if duration > 12 else ""
                    self.stdout.write(f"   - Started: {session.check_in} ({duration}h{warning})")
            
            self.stdout.write("")
        
        # Show summary
        total_hours = sum(session.get_total_hours() for session in active_sessions)
        self.stdout.write(f"📊 Summary:")
        self.stdout.write(f"   Total Active Sessions: {active_sessions.count()}")
        self.stdout.write(f"   Total Employees with Active Sessions: {len(sessions_by_employee)}")
        self.stdout.write(f"   Total Hours in Progress: {total_hours:.2f}")
        
        # Show management commands
        self.stdout.write(f"\n🛠️  Management Commands:")
        self.stdout.write(f"   Close all active sessions:")
        self.stdout.write(f"     python manage.py close_active_sessions --all")
        self.stdout.write(f"   Close sessions for specific employee:")
        self.stdout.write(f"     python manage.py close_active_sessions --employee-email EMAIL")
        self.stdout.write(f"   Dry run (preview only):")
        self.stdout.write(f"     python manage.py close_active_sessions --dry-run")
        
        # Admin-specific instructions
        admin_sessions = active_sessions.filter(employee__role='admin')
        if admin_sessions.exists() and not options['admin_only']:
            self.stdout.write(f"\n⚠️  {admin_sessions.count()} admin session(s) found!")
            self.stdout.write(f"   To view admin sessions only:")
            self.stdout.write(f"     python manage.py list_active_sessions --admin-only --detailed")