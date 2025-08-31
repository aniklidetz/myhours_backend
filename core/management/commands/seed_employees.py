"""
Django management command to seed the database with test employee data.
Creates employees with hourly and monthly salary types, including admin and accountant roles.
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from payroll.models import Salary
from users.models import Employee
from worktime.models import WorkLog


class Command(BaseCommand):
    help = "Seeds database with test employees including admin and accountant roles"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing test data before seeding (users with @test.com emails)",
        )
        parser.add_argument(
            "--with-worklogs",
            action="store_true",
            help="Generate work logs for the current month",
        )
        parser.add_argument(
            "--employees-count",
            type=int,
            default=None,
            help="Number of employees to create (uses predefined set if not specified)",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting employee seeding..."))

        # Set default options if not provided
        if "clear" not in options:
            options["clear"] = False
        if "with_worklogs" not in options:
            options["with_worklogs"] = False
        if "employees_count" not in options:
            options["employees_count"] = None

        if options["clear"]:
            self.clear_test_data()

        with transaction.atomic():
            employees_created = self.create_employees(options["employees_count"])
            if options["with_worklogs"]:
                self.create_work_logs(employees_created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully created {len(employees_created)} employees!"
            )
        )
        self.print_summary(employees_created)

    def clear_test_data(self):
        """Remove existing test data"""
        self.stdout.write("Clearing existing test data...")

        test_users = User.objects.filter(email__endswith="@test.com")
        count = test_users.count()
        test_users.delete()

        self.stdout.write(f"   Removed {count} test users")

    def create_employees(self, employees_count=None):
        """Create employees with hourly and monthly salary types"""

        employees_data = [
            {
                "username": "leah.benami",
                "email": "leah.benami@test.com",
                "first_name": "Leah",
                "last_name": "Ben-Ami",
                "role": "admin",
                "employment_type": "full_time",
                "base_salary": Decimal("25000.00"),
                "calculation_type": "monthly",
                "work_pattern": "sabbath_worker",
                "description": "Senior admin and accountant, works on Sabbaths and holidays",
                "is_staff": True,
                "is_superuser": True,
            },
            {
                "username": "noam.peretz",
                "email": "noam.peretz@test.com",
                "first_name": "Noam",
                "last_name": "Peretz",
                "role": "accountant",
                "employment_type": "full_time",
                "base_salary": Decimal("22000.00"),
                "calculation_type": "monthly",
                "work_pattern": "flexible_hours",
                "description": "Accountant with flexible working hours",
                "is_staff": True,
                "is_superuser": False,
            },
            {
                "username": "yosef.abramov",
                "email": "yosef.abramov@test.com",
                "first_name": "Yosef",
                "last_name": "Abramov",
                "role": "employee",
                "employment_type": "hourly",
                "hourly_rate": Decimal("120.00"),
                "calculation_type": "hourly",
                "work_pattern": "overtime_lover",
                "description": "Senior developer with frequent overtime",
            },
            {
                "username": "dana.azulay",
                "email": "dana.azulay@test.com",
                "first_name": "Dana",
                "last_name": "Azulay",
                "role": "employee",
                "employment_type": "hourly",
                "hourly_rate": Decimal("95.00"),
                "calculation_type": "hourly",
                "work_pattern": "part_time",
                "description": "UX Designer working 4 days per week",
            },
            {
                "username": "itai.shapiro",
                "email": "itai.shapiro@test.com",
                "first_name": "Itai",
                "last_name": "Shapiro",
                "role": "employee",
                "employment_type": "hourly",
                "hourly_rate": Decimal("110.00"),
                "calculation_type": "hourly",
                "work_pattern": "night_shifts",
                "description": "DevOps engineer with night shift schedules",
            },
            {
                "username": "elior.weisman",
                "email": "elior.weisman@test.com",
                "first_name": "Elior",
                "last_name": "Weisman",
                "role": "employee",
                "employment_type": "full_time",
                "base_salary": Decimal("25000.00"),
                "calculation_type": "monthly",
                "work_pattern": "business_trips",
                "description": "Sales manager with frequent business trips",
            },
            {
                "username": "yael.baron",
                "email": "yael.baron@test.com",
                "first_name": "Yael",
                "last_name": "Bar-On",
                "role": "employee",
                "employment_type": "hourly",
                "hourly_rate": Decimal("180.00"),
                "calculation_type": "hourly",
                "work_pattern": "overtime_lover",
                "description": "Senior project manager (hourly)",
            },
            {
                "username": "gilad.friedman",
                "email": "gilad.friedman@test.com",
                "first_name": "Gilad",
                "last_name": "Friedman",
                "role": "employee",
                "employment_type": "full_time",
                "base_salary": Decimal("16000.00"),
                "calculation_type": "monthly",
                "work_pattern": "flexible_hours",
                "description": "Consultant on monthly retainer",
            },
            {
                "username": "maya.shechter",
                "email": "maya.shechter@test.com",
                "first_name": "Maya",
                "last_name": "Shechter",
                "role": "employee",
                "employment_type": "hourly",
                "hourly_rate": Decimal("140.00"),
                "calculation_type": "hourly",
                "work_pattern": "remote_work",
                "description": "Remote developer (hourly)",
            },
            {
                "username": "omer.klein",
                "email": "omer.klein@test.com",
                "first_name": "Omer",
                "last_name": "Klein",
                "role": "employee",
                "employment_type": "hourly",
                "hourly_rate": Decimal("45.00"),
                "calculation_type": "hourly",
                "work_pattern": "student_hours",
                "description": "Student working 3 hours per day",
            },
        ]

        # Check if project payroll is enabled
        project_payroll_enabled = settings.FEATURE_FLAGS.get(
            "ENABLE_PROJECT_PAYROLL", False
        )

        # Convert project employees if feature is disabled
        project_count = 0
        for emp_data in employees_data:
            if emp_data.get("calculation_type") == "project":
                project_count += 1
                if not project_payroll_enabled:
                    # Convert to hourly
                    emp_data["calculation_type"] = "hourly"

        if project_count > 0 and not project_payroll_enabled:
            self.stdout.write(
                self.style.WARNING(
                    f"Project payroll disabled - converting {project_count} project employees to hourly"
                )
            )

        # Limit employees if count specified
        if employees_count is not None:
            employees_data = employees_data[:employees_count]

        total_employees = len(employees_data)
        self.stdout.write(f"Creating {total_employees} employees...")

        created_employees = []

        for emp_data in employees_data:
            self.stdout.write(
                f"   Creating {emp_data['first_name']} {emp_data['last_name']}..."
            )

            # Create or get user
            user, user_created = User.objects.get_or_create(
                username=emp_data["username"],
                defaults={
                    "email": emp_data["email"],
                    "first_name": emp_data["first_name"],
                    "last_name": emp_data["last_name"],
                    "is_active": True,
                    "is_staff": emp_data.get("is_staff", False),
                    "is_superuser": emp_data.get("is_superuser", False),
                },
            )

            if user_created:
                user.set_password("test123")
                user.save()
            elif not user_created:
                # Update existing user permissions if needed
                user.is_staff = emp_data.get("is_staff", False)
                user.is_superuser = emp_data.get("is_superuser", False)
                user.save()

            # Create or get employee
            employee, emp_created = Employee.objects.get_or_create(
                user=user,
                defaults={
                    "email": emp_data["email"],
                    "first_name": emp_data["first_name"],
                    "last_name": emp_data["last_name"],
                    "role": emp_data["role"],
                    "employment_type": (
                        "full_time"
                        if emp_data["employment_type"] == "monthly"
                        else emp_data["employment_type"]
                    ),
                    "hourly_rate": emp_data.get("hourly_rate", Decimal("100.00")),
                    "is_active": True,
                },
            )

            # Create or get salary - following validation rules: only one field per calculation_type
            salary_defaults = {
                "calculation_type": emp_data["calculation_type"],
                "currency": "ILS",
            }

            if emp_data["calculation_type"] == "hourly":
                # For hourly: only hourly_rate, base_salary = None
                salary_defaults["hourly_rate"] = emp_data["hourly_rate"]
                salary_defaults["base_salary"] = None
            elif emp_data["calculation_type"] == "monthly":
                # For monthly: only base_salary, hourly_rate = None
                salary_defaults["base_salary"] = emp_data["base_salary"]
                salary_defaults["hourly_rate"] = None

            salary, sal_created = Salary.objects.get_or_create(
                employee=employee, defaults=salary_defaults
            )

            # Store additional metadata for work log generation
            employee._work_pattern = emp_data["work_pattern"]
            employee._description = emp_data["description"]
            created_employees.append(employee)

            status = (
                "✅ Created"
                if (user_created and emp_created and sal_created)
                else "✅ Updated"
            )
            self.stdout.write(
                f"      {status}: {employee.get_full_name()} ({emp_data['calculation_type']})"
            )

        return created_employees

    def create_work_logs(self, employees):
        """Generate realistic work logs for the last 2-3 weeks"""
        self.stdout.write("Generating work logs for the last 2-3 weeks...")

        current_date = timezone.now()
        # Generate logs for the last 3 weeks (21 days)
        start_date = current_date - timedelta(days=21)

        for employee in employees:
            pattern = employee._work_pattern
            logs_created = 0
            last_work_end = None  # Track last work end time for 36-hour validation

            # Clear existing work logs for the period to avoid duplicates
            WorkLog.objects.filter(
                employee=employee, check_in__gte=start_date, check_in__lte=current_date
            ).delete()

            # Generate logs for each day in the period
            current_day = start_date
            while current_day <= current_date:
                # Pattern-specific logic
                should_work, hours, start_hour = self.get_work_schedule(
                    pattern, current_day
                )

                if should_work:
                    # More realistic check-in times with variation
                    check_in_minute = random.randint(0, 45)
                    check_in = current_day.replace(
                        hour=start_hour,
                        minute=check_in_minute,
                        second=random.randint(0, 59),
                        microsecond=0,
                    )

                    # Ensure 36-hour rest period
                    if last_work_end:
                        time_since_last_work = check_in - last_work_end
                        if time_since_last_work < timedelta(hours=36):
                            # Skip this day to ensure proper rest
                            current_day += timedelta(days=1)
                            continue

                    # Add lunch break for longer days
                    lunch_break = timedelta(minutes=30) if hours >= 7 else timedelta(0)
                    work_duration = timedelta(hours=hours) + lunch_break

                    # Add some randomness to work duration (±15 minutes)
                    duration_variance = timedelta(minutes=random.randint(-15, 15))
                    check_out = check_in + work_duration + duration_variance

                    # Ensure shifts don't exceed 12 hours
                    max_duration = timedelta(hours=12)
                    if check_out - check_in > max_duration:
                        check_out = check_in + max_duration

                    # Ensure work logs are within reasonable hours
                    if check_out.hour > 23:
                        check_out = check_out.replace(hour=23, minute=59)

                    worklog = WorkLog.objects.create(
                        employee=employee,
                        check_in=(
                            timezone.make_aware(check_in)
                            if timezone.is_naive(check_in)
                            else check_in
                        ),
                        check_out=(
                            timezone.make_aware(check_out)
                            if timezone.is_naive(check_out)
                            else check_out
                        ),
                        is_approved=True,
                        location_check_in=self.get_location_for_pattern(pattern),
                        location_check_out=self.get_location_for_pattern(pattern),
                        notes=f"Generated test data - {pattern} pattern",
                    )
                    logs_created += 1

                    # Update last work end time for rest period tracking
                    last_work_end = (
                        timezone.make_aware(check_out)
                        if timezone.is_naive(check_out)
                        else check_out
                    )

                current_day += timedelta(days=1)

            self.stdout.write(
                f"      {employee.get_full_name()}: {logs_created} work logs"
            )

    def get_location_for_pattern(self, pattern):
        """Return appropriate location based on work pattern"""
        if pattern == "remote_work":
            return "Home Office"
        elif pattern == "business_trips":
            return random.choice(
                [
                    "Client Site - Tel Aviv",
                    "Client Site - Jerusalem",
                    "Hotel - Business Trip",
                ]
            )
        elif pattern == "night_shifts":
            return "Office - Night Shift"
        elif pattern == "student_hours":
            return "University Campus Office"
        else:
            return random.choice(
                ["Office Tel Aviv", "Office Main Building", "Office - Floor 3"]
            )

    def get_work_schedule(self, pattern, work_date):
        """Return (should_work, hours, start_hour) based on work pattern with more realistic scheduling"""

        # Get day of week (0=Monday, 6=Sunday)
        weekday = work_date.weekday()

        if pattern == "overtime_lover":
            # Works most days but respects 36-hour rest period (Friday evening to Sunday morning)
            if weekday == 4:  # Friday - shorter day
                return True, random.choice([6, 7, 8]), 8
            elif weekday in [5, 6]:  # Saturday-Sunday - mandatory rest
                return False, 0, 0
            elif weekday in [
                1,
                2,
                3,
            ]:  # Tuesday-Thursday - longer days but max 12 hours
                return True, random.choice([10, 11, 11.5]), 8
            else:  # Monday
                return True, random.choice([9, 10]), 8

        elif pattern == "part_time":
            # Works 4 days a week (Monday-Thursday)
            if weekday < 4:
                return True, 8, 9
            else:
                return False, 0, 0

        elif pattern == "night_shifts":
            # Night shifts with varying schedules, respecting 36-hour weekend rest
            if weekday in [5, 6]:  # Weekend rest
                return False, 0, 0
            elif weekday == 4:  # Friday - early finish for weekend rest
                return True, 6, 22
            else:
                night_start = random.choice([22, 23])
                return True, 8, night_start

        elif pattern == "sabbath_worker":
            # Works including weekends but still needs 36-hour rest period
            # Takes rest on Monday-Tuesday instead
            if weekday in [0, 1]:  # Monday-Tuesday rest
                return False, 0, 0
            elif weekday >= 5:  # Weekend work
                return True, random.choice([8, 9, 10]), 9
            else:  # Wednesday-Friday
                return True, 8, 9

        elif pattern == "flexible_hours":
            # Very irregular schedule but respects weekend rest
            if weekday in [5, 6]:  # Weekend rest
                return False, 0, 0

            work_probability = random.random()
            if work_probability < 0.15:  # 15% chance of not working
                return False, 0, 0
            elif work_probability < 0.4:  # 25% chance of short day
                return True, random.choice([4, 6]), random.choice([10, 11, 13])
            elif work_probability < 0.8:  # 40% chance of normal day
                return True, 8, random.choice([8, 9, 10])
            else:  # 20% chance of long day (max 11 hours)
                return True, random.choice([10, 11]), random.choice([7, 8])

        elif pattern == "business_trips":
            # Irregular due to travel but respects legal limits
            if weekday in [5, 6]:  # Weekend rest even on business trips
                return False, 0, 0
            elif random.random() < 0.3:  # 30% chance of no work (travel day)
                return False, 0, 0
            elif random.random() < 0.4:  # 40% chance of long day (max 12 hours)
                return True, random.choice([10, 11, 12]), 8
            else:  # Normal day
                return True, 8, 9

        elif pattern == "long_sprints":
            # 2-month sprint cycles - intense periods but with weekend rest
            if weekday in [5, 6]:  # Weekend rest
                return False, 0, 0
            sprint_week = (work_date.day // 7) % 4  # 4-week cycle
            if sprint_week in [0, 1]:  # First half of sprint - intense (max 11 hours)
                return True, random.choice([9, 10, 11]), 8
            else:  # Second half - more normal
                return True, random.choice([8, 9]), 9

        elif pattern == "short_projects":
            # 1-2 week projects - very focused bursts
            if weekday < 5:  # Weekdays only
                return True, random.choice([6, 8, 10]), random.choice([9, 10])
            else:
                return False, 0, 0

        elif pattern == "remote_work":
            # Remote work - more flexible but consistent with mandatory weekend rest
            if weekday < 5:  # Weekdays
                return True, random.choice([7, 8, 9]), random.choice([8, 9, 10])
            else:  # Weekend rest
                return False, 0, 0

        elif pattern == "student_hours":
            # 3 hours per day, usually afternoon
            if weekday < 5:  # Weekdays only
                return True, 3, random.choice([14, 15, 16, 17])
            else:
                return False, 0, 0

        # Default pattern - regular office work
        if weekday < 5:
            return True, 8, 9
        else:
            return False, 0, 0

    def print_summary(self, employees):
        """Print summary of created employees"""
        self.stdout.write("\nEmployee Summary:")

        by_type = {}
        by_role = {}

        for emp in employees:
            calc_type = emp.salary_info.calculation_type
            role = emp.role

            if calc_type not in by_type:
                by_type[calc_type] = []
            by_type[calc_type].append(emp)

            if role not in by_role:
                by_role[role] = []
            by_role[role].append(emp)

        for calc_type, emp_list in by_type.items():
            self.stdout.write(f"\n   {calc_type.upper()} ({len(emp_list)} employees):")
            for emp in emp_list:
                salary_info = emp.salary_info
                if calc_type == "hourly":
                    rate_info = f"₪{salary_info.hourly_rate}/hour"
                elif calc_type == "monthly":
                    rate_info = f"₪{salary_info.base_salary}/month"

                self.stdout.write(f"      • {emp.get_full_name()} - {rate_info}")

        self.stdout.write(f"\nRoles Summary:")
        for role, emp_list in by_role.items():
            self.stdout.write(f"   {role.upper()}: {len(emp_list)} employees")

        self.stdout.write(f"\nAll employees created with password: test123")
        self.stdout.write(f"Test emails: @test.com domain")
        self.stdout.write(f"Re-run with --clear to reset test data")
        self.stdout.write(f"Add --with-worklogs to generate work history")

        self.stdout.write(
            self.style.SUCCESS("\n✅ All shifts are limited to 12 hours maximum")
        )
        self.stdout.write(
            self.style.SUCCESS(
                "✅ All employees have at least 36 consecutive hours of rest per week"
            )
        )
