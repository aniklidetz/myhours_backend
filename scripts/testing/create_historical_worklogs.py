#!/usr/bin/env python
"""
Create historical work logs for July-August 2025 and first half of September 2025.
"""
import os
import django
import random
from datetime import datetime, timedelta
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from django.utils import timezone
from users.models import Employee
from worktime.models import WorkLog

def get_work_schedule(pattern, work_date):
    """Return (should_work, hours, start_hour) based on work pattern"""
    weekday = work_date.weekday()

    if pattern == "overtime_lover":
        if weekday == 4:  # Friday - shorter day
            return True, random.choice([6, 7, 8]), 8
        elif weekday in [5, 6]:  # Weekend rest
            return False, 0, 0
        elif weekday in [1, 2, 3]:  # Tue-Thu longer days
            return True, random.choice([10, 11, 11.5]), 8
        else:  # Monday
            return True, random.choice([9, 10]), 8

    elif pattern == "part_time":
        if weekday < 4:  # Mon-Thu
            return True, 8, 9
        else:
            return False, 0, 0

    elif pattern == "night_shifts":
        if weekday in [5, 6]:  # Weekend rest
            return False, 0, 0
        elif weekday == 4:  # Friday
            return True, 6, 22
        else:
            return True, 8, random.choice([22, 23])

    elif pattern == "sabbath_worker":
        if weekday in [0, 1]:  # Mon-Tue rest
            return False, 0, 0
        elif weekday >= 5:  # Weekend work
            return True, random.choice([8, 9, 10]), 9
        else:  # Wed-Fri
            return True, 8, 9

    elif pattern == "flexible_hours":
        if weekday in [5, 6]:  # Weekend rest
            return False, 0, 0
        work_prob = random.random()
        if work_prob < 0.15:  # 15% no work
            return False, 0, 0
        elif work_prob < 0.4:  # 25% short day
            return True, random.choice([4, 6]), random.choice([10, 11, 13])
        elif work_prob < 0.8:  # 40% normal day
            return True, 8, random.choice([8, 9, 10])
        else:  # 20% long day
            return True, random.choice([10, 11]), random.choice([7, 8])

    elif pattern == "business_trips":
        if weekday in [5, 6]:  # Weekend rest
            return False, 0, 0
        elif random.random() < 0.3:  # 30% travel day
            return False, 0, 0
        elif random.random() < 0.4:  # 40% long day
            return True, random.choice([10, 11, 12]), 8
        else:  # Normal day
            return True, 8, 9

    elif pattern == "remote_work":
        if weekday < 5:  # Weekdays
            return True, random.choice([7, 8, 9]), random.choice([8, 9, 10])
        else:
            return False, 0, 0

    elif pattern == "student_hours":
        if weekday < 5:  # Weekdays
            return True, 3, random.choice([14, 15, 16, 17])
        else:
            return False, 0, 0

    # Default pattern
    if weekday < 5:
        return True, 8, 9
    else:
        return False, 0, 0

def get_location_for_pattern(pattern):
    """Return appropriate location based on work pattern"""
    if pattern == "remote_work":
        return "Home Office"
    elif pattern == "business_trips":
        return random.choice([
            "Client Site - Tel Aviv",
            "Client Site - Jerusalem",
            "Hotel - Business Trip"
        ])
    elif pattern == "night_shifts":
        return "Office - Night Shift"
    elif pattern == "student_hours":
        return "University Campus Office"
    else:
        return random.choice([
            "Office Tel Aviv",
            "Office Main Building",
            "Office - Floor 3"
        ])

def create_work_logs_for_period(start_date, end_date):
    """Create work logs for the specified period"""
    print(f"Creating work logs from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    employees = Employee.objects.filter(email__endswith="@test.com")
    total_logs_created = 0

    for employee in employees:
        print(f"  Processing {employee.get_full_name()}...")

        # Get work pattern from employee metadata
        # Default patterns based on role
        pattern_map = {
            "leah.benami@test.com": "sabbath_worker",
            "noam.peretz@test.com": "flexible_hours",
            "yosef.abramov@test.com": "overtime_lover",
            "dana.azulay@test.com": "part_time",
            "itai.shapiro@test.com": "night_shifts",
            "elior.weisman@test.com": "business_trips",
            "yael.baron@test.com": "overtime_lover",
            "gilad.friedman@test.com": "flexible_hours",
            "maya.shechter@test.com": "remote_work",
            "omer.klein@test.com": "student_hours"
        }

        pattern = pattern_map.get(employee.email, "flexible_hours")
        logs_created = 0
        last_work_end = None

        # Clear existing logs for the period
        WorkLog.objects.filter(
            employee=employee,
            check_in__date__gte=start_date,
            check_in__date__lte=end_date
        ).delete()

        current_day = start_date
        while current_day <= end_date:
            should_work, hours, start_hour = get_work_schedule(pattern, current_day)

            if should_work:
                # Create realistic check-in time
                check_in_minute = random.randint(0, 45)
                check_in = current_day.replace(
                    hour=start_hour,
                    minute=check_in_minute,
                    second=random.randint(0, 59),
                    microsecond=0
                )

                # Ensure 36-hour rest period
                if last_work_end:
                    # Convert check_in to timezone-aware for comparison
                    check_in_aware = timezone.make_aware(check_in) if timezone.is_naive(check_in) else check_in
                    time_since_last_work = check_in_aware - last_work_end
                    if time_since_last_work < timedelta(hours=36):
                        current_day += timedelta(days=1)
                        continue

                # Add lunch break and variance
                lunch_break = timedelta(minutes=30) if hours >= 7 else timedelta(0)
                work_duration = timedelta(hours=hours) + lunch_break
                duration_variance = timedelta(minutes=random.randint(-15, 15))
                check_out = check_in + work_duration + duration_variance

                # Limit to 12 hours max
                max_duration = timedelta(hours=12)
                if check_out - check_in > max_duration:
                    check_out = check_in + max_duration

                # Ensure reasonable end times
                if check_out.hour > 23:
                    check_out = check_out.replace(hour=23, minute=59)

                # Create work log
                worklog = WorkLog.objects.create(
                    employee=employee,
                    check_in=timezone.make_aware(check_in) if timezone.is_naive(check_in) else check_in,
                    check_out=timezone.make_aware(check_out) if timezone.is_naive(check_out) else check_out,
                    is_approved=True,
                    location_check_in=get_location_for_pattern(pattern),
                    location_check_out=get_location_for_pattern(pattern),
                    notes=f"Historical data - {pattern} pattern"
                )
                logs_created += 1

                last_work_end = timezone.make_aware(check_out) if timezone.is_naive(check_out) else check_out

            current_day += timedelta(days=1)

        print(f"    Created {logs_created} work logs")
        total_logs_created += logs_created

    print(f"✅ Total work logs created: {total_logs_created}")

def main():
    print("=== Creating Historical Work Logs ===")

    # July 2025
    july_start = datetime(2025, 7, 1)
    july_end = datetime(2025, 7, 31)
    create_work_logs_for_period(july_start, july_end)

    print()

    # August 2025
    august_start = datetime(2025, 8, 1)
    august_end = datetime(2025, 8, 31)
    create_work_logs_for_period(august_start, august_end)

    print()

    # First half of September 2025
    sept_start = datetime(2025, 9, 1)
    sept_end = datetime(2025, 9, 15)
    create_work_logs_for_period(sept_start, sept_end)

    print("\n🎉 Historical work logs creation completed!")

if __name__ == '__main__':
    main()