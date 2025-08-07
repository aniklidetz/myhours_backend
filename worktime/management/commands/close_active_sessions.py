from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from users.models import Employee
from worktime.models import WorkLog


class Command(BaseCommand):
    help = "Close active work sessions"

    def add_arguments(self, parser):
        parser.add_argument(
            "--employee-id",
            type=int,
            help="Close sessions for specific employee ID",
        )
        parser.add_argument(
            "--employee-email",
            type=str,
            help="Close sessions for employee with specific email",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Close all active sessions",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be closed without actually closing",
        )

    def handle(self, *args, **options):
        self.stdout.write("=== Active Work Session Manager ===\n")

        # Find active sessions
        active_sessions = WorkLog.objects.filter(check_out__isnull=True)

        if not active_sessions.exists():
            self.stdout.write(self.style.SUCCESS("✓ No active work sessions found"))
            return

        # Filter by specific employee if requested
        if options["employee_id"]:
            active_sessions = active_sessions.filter(
                employee__id=options["employee_id"]
            )

        if options["employee_email"]:
            active_sessions = active_sessions.filter(
                employee__email=options["employee_email"]
            )

        if not active_sessions.exists():
            self.stdout.write(
                self.style.WARNING("No active sessions found for specified criteria")
            )
            return

        # Display active sessions
        self.stdout.write(f"Found {active_sessions.count()} active work session(s):\n")

        for i, session in enumerate(active_sessions, 1):
            duration = session.get_total_hours()
            self.stdout.write(f"  {i}. Employee: {session.employee.get_full_name()}")
            self.stdout.write(f"     Email: {session.employee.email}")
            self.stdout.write(f"     Started: {session.check_in}")
            self.stdout.write(f"     Duration: {duration} hours")
            self.stdout.write(f"     Location: {session.location_check_in or 'N/A'}")
            self.stdout.write(f"     Session ID: {session.id}")
            self.stdout.write("")

        # Close sessions if not dry run
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("DRY RUN: No sessions were closed"))
            return

        if not options["all"]:
            # Ask for confirmation unless --all is specified
            confirm = input(
                f"Close {active_sessions.count()} active session(s)? [y/N]: "
            )
            if confirm.lower() not in ["y", "yes"]:
                self.stdout.write("Operation cancelled")
                return

        # Close the sessions
        now = timezone.now()
        closed_count = 0

        for session in active_sessions:
            session.check_out = now
            session.save()
            closed_count += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ Closed session for {session.employee.get_full_name()} "
                    f"(Duration: {session.get_total_hours()} hours)"
                )
            )

        self.stdout.write(
            f"\n{self.style.SUCCESS(f'Successfully closed {closed_count} work session(s)')}"
        )
