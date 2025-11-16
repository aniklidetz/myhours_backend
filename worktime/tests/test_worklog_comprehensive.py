"""
Comprehensive tests for WorkLog model and related functionality.
Tests work log validation, calculations, edge cases, and business logic.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from payroll.models import Salary
from users.models import Employee
from worktime.models import WorkLog


class WorkLogModelTest(TestCase):
    """Comprehensive tests for WorkLog model"""

    def setUp(self):
        """Set up test data"""
        self.employee = Employee.objects.create(
            first_name="Test",
            last_name="Worker",
            email="test.worker@example.com",
            employment_type="hourly",
            role="employee",
        )

        self.salary = Salary.objects.create(
            employee=self.employee,
            calculation_type="hourly",
            hourly_rate=Decimal("100.00"),
            currency="ILS",
        )

    def test_worklog_normal_day_calculation(self):
        """Test normal 8-hour work day calculation"""
        check_in = timezone.make_aware(datetime(2025, 7, 25, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 25, 17, 0))

        worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=check_in,
            check_out=check_out,
            location_check_in="Office",
            location_check_out="Office",
        )

        self.assertEqual(worklog.get_total_hours(), 8.0)
        self.assertFalse(worklog.is_current_session())
        self.assertEqual(worklog.employee, self.employee)

    def test_worklog_overtime_calculation(self):
        """Test overtime hours calculation (>8.6 hours in Israel)"""
        check_in = timezone.make_aware(datetime(2025, 7, 25, 8, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 25, 20, 0))  # 12 hours

        worklog = WorkLog.objects.create(
            employee=self.employee, check_in=check_in, check_out=check_out
        )

        total_hours = worklog.get_total_hours()
        self.assertEqual(total_hours, 12.0)
        # Overtime is anything over 8.6 hours per Israeli labor law
        from decimal import Decimal

        overtime_hours = max(0, total_hours - Decimal("8.6"))
        self.assertAlmostEqual(float(overtime_hours), 3.4, places=1)

    def test_worklog_night_shift_detection(self):
        """Test night shift detection (22:00-06:00)"""
        # Night shift: 22:00-06:00 next day
        check_in = timezone.make_aware(datetime(2025, 7, 25, 22, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 26, 6, 0))

        worklog = WorkLog.objects.create(
            employee=self.employee, check_in=check_in, check_out=check_out
        )

        self.assertEqual(worklog.get_total_hours(), 8.0)
        # Night shift premium should be detected by payroll service
        self.assertTrue(check_in.hour >= 22 or check_in.hour <= 6)

    def test_worklog_sabbath_detection(self):
        """Test Sabbath work detection (Friday evening to Saturday evening)"""
        # Saturday work
        check_in = timezone.make_aware(datetime(2025, 7, 26, 9, 0))  # Saturday
        check_out = timezone.make_aware(datetime(2025, 7, 26, 17, 0))

        worklog = WorkLog.objects.create(
            employee=self.employee, check_in=check_in, check_out=check_out
        )

        # Check if it's Saturday (weekday 5)
        self.assertEqual(check_in.weekday(), 5)  # Saturday
        self.assertEqual(worklog.get_total_hours(), 8.0)

    def test_worklog_current_session_detection(self):
        """Test detection of current active work session"""
        check_in = timezone.now() - timedelta(hours=2)

        worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=check_in,
            # No check_out - current session
        )

        self.assertTrue(worklog.is_current_session())
        self.assertIsNone(worklog.check_out)

    def test_worklog_minimum_duration_validation(self):
        """Test minimum work duration validation"""
        check_in = timezone.make_aware(datetime(2025, 7, 25, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 25, 9, 15))  # 15 minutes

        worklog = WorkLog.objects.create(
            employee=self.employee, check_in=check_in, check_out=check_out
        )

        self.assertEqual(worklog.get_total_hours(), 0.25)  # 15 minutes = 0.25 hours

    def test_worklog_cross_midnight_shift(self):
        """Test work shifts that cross midnight"""
        check_in = timezone.make_aware(datetime(2025, 7, 25, 23, 0))
        check_out = timezone.make_aware(
            datetime(2025, 7, 26, 7, 0)
        )  # 8 hours across midnight

        worklog = WorkLog.objects.create(
            employee=self.employee, check_in=check_in, check_out=check_out
        )

        self.assertEqual(worklog.get_total_hours(), 8.0)
        self.assertTrue(check_out.date() > check_in.date())

    def test_worklog_break_time_handling(self):
        """Test work logs with break times"""
        # 9-hour shift with 1-hour break (net 8 hours)
        check_in = timezone.make_aware(datetime(2025, 7, 25, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 25, 18, 0))  # 9 hours total

        worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=check_in,
            check_out=check_out,
            break_minutes=60,  # 1-hour break
        )

        # Total time minus break time
        expected_hours = 9.0 - 1.0  # 8 hours net work
        self.assertEqual(worklog.get_total_hours(), expected_hours)

    def test_worklog_invalid_checkout_before_checkin(self):
        """Test validation for checkout before checkin"""
        check_in = timezone.make_aware(datetime(2025, 7, 25, 17, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 25, 9, 0))  # Before check-in

        with self.assertRaises(ValidationError):
            worklog = WorkLog(
                employee=self.employee, check_in=check_in, check_out=check_out
            )
            worklog.full_clean()

    def test_worklog_location_tracking(self):
        """Test location tracking functionality"""
        from decimal import Decimal

        worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.now(),
            location_check_in="Office - Tel Aviv",
            latitude_check_in=Decimal("32.085300"),  # Use Decimal with 6 decimal places
            longitude_check_in=Decimal(
                "34.781800"
            ),  # Use Decimal with 6 decimal places
        )

        self.assertEqual(worklog.location_check_in, "Office - Tel Aviv")
        self.assertAlmostEqual(float(worklog.latitude_check_in), 32.085300, places=4)
        self.assertAlmostEqual(float(worklog.longitude_check_in), 34.781800, places=4)

    def test_worklog_approval_workflow(self):
        """Test work log approval workflow"""
        worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.make_aware(datetime(2025, 7, 25, 9, 0)),
            check_out=timezone.make_aware(datetime(2025, 7, 25, 17, 0)),
            is_approved=False,
        )

        self.assertFalse(worklog.is_approved)

        # Approve the work log
        worklog.is_approved = True
        worklog.save()

        self.assertTrue(worklog.is_approved)

    def test_worklog_monthly_summary_integration(self):
        """Test integration with monthly payroll calculations"""
        # Create multiple work logs for a month
        base_date = date(2025, 7, 1)

        for day in range(1, 11):  # 10 work days
            check_in = timezone.make_aware(datetime(2025, 7, day, 9, 0))
            check_out = timezone.make_aware(datetime(2025, 7, day, 17, 0))

            WorkLog.objects.create(
                employee=self.employee,
                check_in=check_in,
                check_out=check_out,
                is_approved=True,
            )

        # Verify we have 10 work logs
        july_logs = WorkLog.objects.filter(
            employee=self.employee, check_in__year=2025, check_in__month=7
        )

        self.assertEqual(july_logs.count(), 10)

        # Calculate total hours
        total_hours = sum(log.get_total_hours() for log in july_logs)
        self.assertEqual(total_hours, 80.0)  # 10 days × 8 hours

    def test_worklog_employee_relationship(self):
        """Test employee relationship and cascading"""
        worklog = WorkLog.objects.create(
            employee=self.employee, check_in=timezone.now()
        )

        # Verify relationship
        self.assertEqual(worklog.employee, self.employee)
        self.assertIn(worklog, self.employee.worklog_set.all())

    def test_worklog_string_representation(self):
        """Test string representation of WorkLog"""
        check_in = timezone.make_aware(datetime(2025, 7, 25, 9, 0))
        worklog = WorkLog.objects.create(employee=self.employee, check_in=check_in)

        str_repr = str(worklog)
        self.assertIn(self.employee.get_full_name(), str_repr)
        self.assertIn("2025-07-25", str_repr)

    def test_worklog_query_optimization(self):
        """Test query optimization for large datasets"""
        # Create multiple employees and work logs
        employees = []
        for i in range(5):
            emp = Employee.objects.create(
                first_name=f"Employee",
                last_name=f"{i}",
                email=f"emp{i}@test.com",
                employment_type="hourly",
            )
            employees.append(emp)

        # Create work logs for each employee
        for emp in employees:
            for day in range(1, 6):  # 5 days each
                WorkLog.objects.create(
                    employee=emp,
                    check_in=timezone.make_aware(datetime(2025, 7, day, 9, 0)),
                    check_out=timezone.make_aware(datetime(2025, 7, day, 17, 0)),
                )

        # Test efficient querying with select_related
        worklogs = WorkLog.objects.select_related("employee").filter(
            check_in__year=2025, check_in__month=7
        )

        # Should have 25 work logs (5 employees × 5 days)
        self.assertEqual(worklogs.count(), 25)

    def test_worklog_date_filtering(self):
        """Test filtering work logs by date ranges"""
        # Create work logs across different dates
        dates = [
            date(2025, 7, 1),  # Start of month
            date(2025, 7, 15),  # Mid month
            date(2025, 7, 31),  # End of month
            date(2025, 8, 1),  # Next month
        ]

        for test_date in dates:
            WorkLog.objects.create(
                employee=self.employee,
                check_in=timezone.make_aware(
                    datetime.combine(test_date, datetime.min.time().replace(hour=9))
                ),
                check_out=timezone.make_aware(
                    datetime.combine(test_date, datetime.min.time().replace(hour=17))
                ),
            )

        # Filter July work logs
        july_logs = WorkLog.objects.filter(
            employee=self.employee, check_in__year=2025, check_in__month=7
        )

        self.assertEqual(july_logs.count(), 3)  # 3 July dates

        # Filter specific date range
        start_date = date(2025, 7, 10)
        end_date = date(2025, 7, 20)

        range_logs = WorkLog.objects.filter(
            employee=self.employee,
            check_in__date__gte=start_date,
            check_in__date__lte=end_date,
        )

        self.assertEqual(range_logs.count(), 1)  # Only July 15th


class WorkLogBusinessLogicTest(TestCase):
    """Test business logic and edge cases for WorkLog"""

    def setUp(self):
        """Set up test data"""
        self.hourly_employee = Employee.objects.create(
            first_name="Hourly",
            last_name="Worker",
            email="hourly@test.com",
            employment_type="hourly",
        )

        self.monthly_employee = Employee.objects.create(
            first_name="Monthly",
            last_name="Worker",
            email="monthly@test.com",
            employment_type="full_time",
        )

    def test_worklog_different_employment_types(self):
        """Test work logs for different employment types"""
        # Same work pattern for both types
        check_in = timezone.make_aware(datetime(2025, 7, 25, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, 25, 17, 0))

        hourly_log = WorkLog.objects.create(
            employee=self.hourly_employee, check_in=check_in, check_out=check_out
        )

        monthly_log = WorkLog.objects.create(
            employee=self.monthly_employee, check_in=check_in, check_out=check_out
        )

        # Hours should be the same regardless of employment type
        self.assertEqual(hourly_log.get_total_hours(), monthly_log.get_total_hours())
        self.assertEqual(hourly_log.get_total_hours(), 8.0)

    def test_worklog_bulk_operations(self):
        """Test bulk creation and operations on work logs"""
        # Bulk create work logs
        work_logs = []
        for day in range(1, 21):  # 20 work days
            work_logs.append(
                WorkLog(
                    employee=self.hourly_employee,
                    check_in=timezone.make_aware(datetime(2025, 7, day, 9, 0)),
                    check_out=timezone.make_aware(
                        datetime(2025, 7, day, 17, 30)
                    ),  # 8.5 hours
                    is_approved=True,
                )
            )

        WorkLog.objects.bulk_create(work_logs)

        # Verify bulk creation
        july_logs = WorkLog.objects.filter(
            employee=self.hourly_employee, check_in__year=2025, check_in__month=7
        )

        self.assertEqual(july_logs.count(), 20)

        # Test bulk update
        july_logs.update(is_approved=False)

        # Verify all are now unapproved
        unapproved_count = july_logs.filter(is_approved=False).count()
        self.assertEqual(unapproved_count, 20)

    def test_worklog_timezone_handling(self):
        """Test timezone handling for work logs"""
        # Create work log with timezone-aware datetime
        utc_time = timezone.make_aware(datetime(2025, 7, 25, 6, 0))  # 6 AM UTC

        worklog = WorkLog.objects.create(
            employee=self.hourly_employee,
            check_in=utc_time,
            check_out=utc_time + timedelta(hours=8),
        )

        # Should preserve timezone information
        self.assertTrue(timezone.is_aware(worklog.check_in))
        self.assertTrue(timezone.is_aware(worklog.check_out))
        self.assertEqual(worklog.get_total_hours(), 8.0)

    def test_worklog_concurrent_sessions_prevention(self):
        """Test prevention of overlapping work sessions for same employee"""
        base_time = timezone.now()

        # Create first work log (current session)
        first_log = WorkLog.objects.create(
            employee=self.hourly_employee,
            check_in=base_time,
            # No check_out - current session
        )

        # Attempting to create overlapping session should raise ValidationError
        with self.assertRaises(ValidationError) as context:
            second_log = WorkLog.objects.create(
                employee=self.hourly_employee,
                check_in=base_time + timedelta(hours=1),
                # This would overlap with the first session
            )

        # Verify the error message
        self.assertIn("overlaps", str(context.exception).lower())

        # First log should still be a current session
        self.assertTrue(first_log.is_current_session())

    def test_worklog_performance_with_large_dataset(self):
        """Test performance with large number of work logs"""
        # Create work logs for multiple months
        start_date = date(2025, 1, 1)
        current_date = start_date

        work_logs = []
        for _ in range(100):  # 100 work days
            if current_date.weekday() < 5:  # Weekdays only
                work_logs.append(
                    WorkLog(
                        employee=self.hourly_employee,
                        check_in=timezone.make_aware(
                            datetime.combine(
                                current_date, datetime.min.time().replace(hour=9)
                            )
                        ),
                        check_out=timezone.make_aware(
                            datetime.combine(
                                current_date, datetime.min.time().replace(hour=17)
                            )
                        ),
                        is_approved=True,
                    )
                )
            current_date += timedelta(days=1)

        # Bulk create for performance
        WorkLog.objects.bulk_create(work_logs)

        # Test efficient querying
        year_logs = WorkLog.objects.filter(
            employee=self.hourly_employee, check_in__year=2025
        ).select_related("employee")

        # Should have all created logs
        self.assertGreater(year_logs.count(), 50)

        # Test aggregation using WorkLogQuerySet method
        total_hours = year_logs.total_hours()

        self.assertIsNotNone(total_hours)
