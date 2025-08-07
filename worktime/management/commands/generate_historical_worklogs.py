"""
Django management command to generate historical work logs for existing employees.
Generates work logs for specified months while respecting legal limits.
"""

import calendar
import random
from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from users.models import Employee
from worktime.models import WorkLog


class Command(BaseCommand):
    help = "Generate historical work logs for existing employees for specified months"

    def add_arguments(self, parser):
        parser.add_argument(
            "--months",
            type=str,
            default="5,6",
            help="Comma-separated list of months (1-12). Default: 5,6 (May, June)",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=datetime.now().year,
            help="Year for work logs. Default: current year",
        )
        parser.add_argument(
            "--employees",
            type=str,
            help="Comma-separated list of employee IDs. If not specified, generates for all active employees",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing work logs for the specified period before generating",
        )
        parser.add_argument(
            "--pattern",
            type=str,
            default="standard",
            choices=["standard", "flexible", "intensive", "part_time"],
            help="Work pattern to apply (default: standard)",
        )

    def handle(self, *args, **options):
        # Parse months
        try:
            months = [int(m.strip()) for m in options["months"].split(",")]
        except ValueError:
            self.stdout.write(
                self.style.ERROR(
                    "Invalid months format. Use comma-separated numbers (e.g., 5,6)"
                )
            )
            return

        year = options["year"]
        pattern = options["pattern"]

        # Validate months
        if not all(1 <= m <= 12 for m in months):
            self.stdout.write(self.style.ERROR("Months must be between 1 and 12"))
            return

        # Get employees
        if options["employees"]:
            try:
                employee_ids = [int(e.strip()) for e in options["employees"].split(",")]
                employees = Employee.objects.filter(id__in=employee_ids, is_active=True)
            except ValueError:
                self.stdout.write(self.style.ERROR("Invalid employee IDs format"))
                return
        else:
            employees = Employee.objects.filter(is_active=True)

        if not employees.exists():
            self.stdout.write(self.style.ERROR("No active employees found"))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"🚀 Generating work logs for {employees.count()} employees "
                f"for months {months} in year {year}"
            )
        )

        # Process each month
        for month in months:
            self.stdout.write(f"\n📅 Processing {calendar.month_name[month]} {year}...")

            if options["clear"]:
                self._clear_month_logs(employees, year, month)

            self._generate_month_logs(employees, year, month, pattern)

        self.stdout.write(self.style.SUCCESS("\n✅ Work log generation completed!"))

    def _clear_month_logs(self, employees, year, month):
        """Clear existing logs for the month"""
        start_date = date(year, month, 1)
        _, last_day = calendar.monthrange(year, month)
        end_date = date(year, month, last_day)

        deleted_count = WorkLog.objects.filter(
            employee__in=employees,
            check_in__date__gte=start_date,
            check_in__date__lte=end_date,
        ).delete()[0]

        self.stdout.write(f"   🗑️ Cleared {deleted_count} existing work logs")

    def _generate_month_logs(self, employees, year, month, pattern):
        """Generate logs for a specific month"""
        start_date = date(year, month, 1)
        _, last_day = calendar.monthrange(year, month)
        end_date = date(year, month, last_day)

        total_logs = 0

        for employee in employees:
            logs_created = self._generate_employee_month(
                employee, start_date, end_date, pattern
            )
            total_logs += logs_created

            self.stdout.write(
                f"   ✅ {employee.get_full_name()}: {logs_created} work logs"
            )

        self.stdout.write(f"   📊 Total: {total_logs} work logs created")

    def _generate_employee_month(self, employee, start_date, end_date, pattern):
        """Generate logs for one employee for one month"""
        logs_created = 0
        last_work_end = None
        current_date = start_date

        while current_date <= end_date:
            # Get work schedule based on pattern
            should_work, hours, start_hour = self._get_work_schedule(
                pattern, current_date, employee
            )

            if should_work:
                # Create check-in time with some randomness
                check_in = timezone.make_aware(
                    datetime.combine(
                        current_date,
                        datetime.min.time().replace(
                            hour=start_hour,
                            minute=random.randint(0, 30),
                            second=random.randint(0, 59),
                        ),
                    )
                )

                # Ensure 36-hour rest period
                if last_work_end and (check_in - last_work_end) < timedelta(hours=36):
                    current_date += timedelta(days=1)
                    continue

                # Calculate check-out (max 12 hours)
                work_duration = timedelta(hours=min(hours, 12))
                # Add lunch break for long shifts
                if hours >= 7:
                    work_duration += timedelta(minutes=30)

                # Add some randomness (±15 minutes)
                work_duration += timedelta(minutes=random.randint(-15, 15))

                check_out = check_in + work_duration

                # Ensure we don't go past midnight
                if check_out.date() > check_in.date():
                    check_out = check_in.replace(hour=23, minute=59)

                # Create work log
                WorkLog.objects.create(
                    employee=employee,
                    check_in=check_in,
                    check_out=check_out,
                    is_approved=True,
                    location_check_in=self._get_location(employee),
                    location_check_out=self._get_location(employee),
                    notes=f"Historical data - {pattern} pattern",
                )

                logs_created += 1
                last_work_end = check_out

            current_date += timedelta(days=1)

        return logs_created

    def _get_work_schedule(self, pattern, work_date, employee):
        """Determine work schedule based on pattern and date"""
        weekday = work_date.weekday()

        # Always respect weekends (36-hour rest)
        if weekday in [5, 6]:  # Saturday, Sunday
            return False, 0, 0

        if pattern == "standard":
            # Standard 5-day work week, 8-9 hours
            if weekday < 5:
                return True, random.choice([8, 8.5, 9]), random.choice([8, 9])
            return False, 0, 0

        elif pattern == "flexible":
            # Flexible schedule with occasional days off
            if weekday < 5:
                if random.random() < 0.15:  # 15% chance of day off
                    return False, 0, 0
                hours = random.choice([6, 7, 8, 9, 10])
                start = random.choice([7, 8, 9, 10, 11])
                return True, hours, start
            return False, 0, 0

        elif pattern == "intensive":
            # Intensive but legal (max 12 hours, weekends off)
            if weekday == 4:  # Friday - shorter day
                return True, random.choice([6, 7, 8]), 8
            elif weekday < 4:  # Monday-Thursday
                return True, random.choice([10, 11, 11.5]), 8
            return False, 0, 0

        elif pattern == "part_time":
            # Part-time: 4 days a week, 6 hours
            if weekday < 4:  # Monday-Thursday only
                return True, 6, random.choice([9, 10, 14])
            return False, 0, 0

        # Default to standard
        return True, 8, 9

    def _get_location(self, employee):
        """Get appropriate location for employee"""
        # Check employee role for location hints
        if employee.role == "admin":
            return "Office - Administration"
        elif employee.role == "accountant":
            return "Office - Finance Dept"
        else:
            locations = [
                "Office - Main Building",
                "Office - Tel Aviv",
                "Office - Floor 3",
                "Office - Development",
            ]
            return random.choice(locations)
