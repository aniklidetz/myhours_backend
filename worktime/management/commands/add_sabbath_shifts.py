"""
Django management command to add Sabbath work shifts for testing payroll calculations.
Adds shifts that overlap with Sabbath times (Friday evening to Saturday evening).
"""

import calendar
import random
from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from integrations.services.enhanced_sunrise_sunset_service import (
    EnhancedSunriseSunsetService,
)
from users.models import Employee
from worktime.models import WorkLog


class Command(BaseCommand):
    help = "Add Sabbath work shifts for testing payroll calculations with premium pay"

    def add_arguments(self, parser):
        parser.add_argument(
            "--months",
            type=str,
            default="5,6",
            help="Comma-separated list of months (1-12). Default: 5,6 (May, June)",
        )
        parser.add_argument(
            "--year", type=int, default=2025, help="Year for work logs. Default: 2025"
        )
        parser.add_argument(
            "--employees",
            type=str,
            help="Comma-separated list of employee IDs. If not specified, uses first 4 active employees",
        )
        parser.add_argument(
            "--shifts-per-month",
            type=int,
            default=2,
            help="Number of Sabbath shifts per employee per month. Default: 2",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing Sabbath shifts before adding new ones",
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
        shifts_per_month = options["shifts_per_month"]

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
            # Get first 4 active employees
            employees = Employee.objects.filter(is_active=True)[:4]

        if not employees.exists():
            self.stdout.write(self.style.ERROR("No active employees found"))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"🕯️ Adding Sabbath shifts for {employees.count()} employees "
                f"for months {months} in year {year}"
            )
        )

        # Process each month
        total_shifts = 0
        for month in months:
            self.stdout.write(f"\n📅 Processing {calendar.month_name[month]} {year}...")

            if options["clear"]:
                self._clear_sabbath_shifts(employees, year, month)

            month_shifts = self._add_sabbath_shifts(
                employees, year, month, shifts_per_month
            )
            total_shifts += month_shifts

        self.stdout.write(
            self.style.SUCCESS(f"\n✅ Added {total_shifts} Sabbath shifts for testing!")
        )

    def _clear_sabbath_shifts(self, employees, year, month):
        """Clear existing Sabbath shifts for the month"""
        start_date = date(year, month, 1)
        _, last_day = calendar.monthrange(year, month)
        end_date = date(year, month, last_day)

        # Delete shifts that start on Friday or Saturday
        deleted_count = WorkLog.objects.filter(
            employee__in=employees,
            check_in__date__gte=start_date,
            check_in__date__lte=end_date,
            check_in__week_day__in=[6, 7],  # Friday=6, Saturday=7 in Django
            notes__icontains="Sabbath",
        ).delete()[0]

        self.stdout.write(f"   🗑️ Cleared {deleted_count} existing Sabbath shifts")

    def _add_sabbath_shifts(self, employees, year, month, shifts_per_month):
        """Add Sabbath shifts for a specific month"""
        total_shifts = 0

        # Get all Fridays in the month
        fridays = self._get_fridays_in_month(year, month)

        if len(fridays) < shifts_per_month:
            self.stdout.write(
                self.style.WARNING(
                    f"   ⚠️ Only {len(fridays)} Fridays in {calendar.month_name[month]}, "
                    f"adjusting shifts per employee to {len(fridays)}"
                )
            )
            shifts_per_month = len(fridays)

        for employee in employees:
            # Select random Fridays for this employee
            selected_fridays = random.sample(fridays, shifts_per_month)

            employee_shifts = 0
            for friday in selected_fridays:
                if self._create_sabbath_shift(employee, friday):
                    employee_shifts += 1
                    total_shifts += 1

            self.stdout.write(
                f"   ✅ {employee.get_full_name()}: {employee_shifts} Sabbath shifts"
            )

        return total_shifts

    def _get_fridays_in_month(self, year, month):
        """Get all Fridays in a given month"""
        start_date = date(year, month, 1)
        _, last_day = calendar.monthrange(year, month)
        end_date = date(year, month, last_day)

        fridays = []
        current_date = start_date

        while current_date <= end_date:
            if current_date.weekday() == 4:  # Friday is 4
                fridays.append(current_date)
            current_date += timedelta(days=1)

        return fridays

    def _create_sabbath_shift(self, employee, friday):
        """Create a work shift that overlaps with Sabbath time"""
        try:
            # Get precise Sabbath times for this Friday
            sabbath_times = (
                EnhancedSunriseSunsetService.get_shabbat_times_israeli_timezone(friday)
            )

            if not sabbath_times:
                self.stdout.write(
                    self.style.WARNING(f"   ⚠️ Could not get Sabbath times for {friday}")
                )
                return False

            sabbath_start = datetime.fromisoformat(sabbath_times["shabbat_start"])
            sabbath_end = datetime.fromisoformat(sabbath_times["shabbat_end"])

            # Create shift patterns that overlap with Sabbath
            shift_patterns = [
                # Friday evening shift (starts before, ends during Sabbath)
                {
                    "start_offset": timedelta(hours=-3),  # 3 hours before Sabbath
                    "duration": timedelta(hours=6),  # 6 hour shift
                    "description": "Friday evening shift overlapping Sabbath start",
                },
                # Friday night to Saturday shift (spans Sabbath start)
                {
                    "start_offset": timedelta(hours=-1),  # 1 hour before Sabbath
                    "duration": timedelta(hours=8),  # 8 hour shift
                    "description": "Friday night to Saturday shift during Sabbath",
                },
                # Saturday shift (fully within Sabbath)
                {
                    "start_offset": timedelta(hours=2),  # 2 hours after Sabbath start
                    "duration": timedelta(hours=6),  # 6 hour shift
                    "description": "Saturday shift during Sabbath",
                },
                # Saturday evening shift (ends after Sabbath)
                {
                    "start_offset": timedelta(
                        hours=-2, minutes=30
                    ),  # Before Sabbath end
                    "duration": timedelta(hours=4),  # 4 hour shift
                    "description": "Saturday evening shift ending after Sabbath",
                },
            ]

            # Randomly select a shift pattern
            pattern = random.choice(shift_patterns)

            # Calculate shift times
            if "Saturday" in pattern["description"]:
                # For Saturday shifts, calculate from Sabbath start
                check_in = sabbath_start + pattern["start_offset"]
            else:
                # For Friday shifts, calculate from Sabbath start
                check_in = sabbath_start + pattern["start_offset"]

            check_out = check_in + pattern["duration"]

            # Ensure shift doesn't exceed 12 hours (legal limit)
            if check_out - check_in > timedelta(hours=12):
                check_out = check_in + timedelta(hours=12)

            # Check for overlapping shifts for this employee
            existing_shift = WorkLog.objects.filter(
                employee=employee,
                check_in__date=check_in.date(),
                check_out__isnull=False,
            ).exists()

            if existing_shift:
                self.stdout.write(
                    self.style.WARNING(
                        f"   ⚠️ {employee.get_full_name()} already has shift on {check_in.date()}"
                    )
                )
                return False

            # Create the work log
            WorkLog.objects.create(
                employee=employee,
                check_in=check_in,
                check_out=check_out,
                is_approved=True,
                location_check_in=self._get_location(employee),
                location_check_out=self._get_location(employee),
                notes=f'Sabbath shift for testing - {pattern["description"]}',
            )

            # Calculate overlap for logging
            overlap_start = max(check_in, sabbath_start)
            overlap_end = min(check_out, sabbath_end)
            overlap_hours = max(0, (overlap_end - overlap_start).total_seconds() / 3600)

            self.stdout.write(
                f'     🕯️ {check_in.strftime("%a %H:%M")} - {check_out.strftime("%a %H:%M")} '
                f"({overlap_hours:.1f}h Sabbath overlap)"
            )

            return True

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f"   ❌ Error creating Sabbath shift for {employee.get_full_name()}: {e}"
                )
            )
            return False

    def _get_location(self, employee):
        """Get appropriate location for employee"""
        if employee.role == "admin":
            return "Office - Administration"
        elif employee.role == "accountant":
            return "Office - Finance Dept"
        else:
            locations = [
                "Office - Main Building",
                "Office - Tel Aviv",
                "Office - Security",
                "Office - Emergency Services",
            ]
            return random.choice(locations)
