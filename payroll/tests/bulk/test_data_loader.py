"""
Tests for BulkDataLoader.
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytz

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone as django_timezone

from integrations.models import Holiday
from payroll.models import Salary
from payroll.services.bulk.data_loader import BulkDataLoader
from payroll.services.bulk.types import BulkLoadedData, EmployeeData, WorkLogData
from users.models import Employee
from worktime.models import WorkLog


class BulkDataLoaderTestCase(TestCase):
    """Tests for BulkDataLoader class."""

    def setUp(self):
        """Set up test data."""
        # Create test users
        self.user1 = User.objects.create_user(
            username="testuser1", email="test1@example.com", password="testpass123"
        )
        self.user2 = User.objects.create_user(
            username="testuser2", email="test2@example.com", password="testpass123"
        )

        # Create test employees
        self.employee1 = Employee.objects.create(
            user=self.user1,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            employment_type="full_time",
            is_active=True,
        )

        self.employee2 = Employee.objects.create(
            user=self.user2,
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            employment_type="full_time",
            is_active=True,
        )

        # Create salaries
        self.salary1 = Salary.objects.create(
            employee=self.employee1,
            calculation_type="hourly",
            hourly_rate=Decimal("50.00"),
            is_active=True,
        )

        self.salary2 = Salary.objects.create(
            employee=self.employee2,
            calculation_type="monthly",
            base_salary=Decimal("8000.00"),
            is_active=True,
        )

        # Create work logs for October 2025
        # Use timezone-aware datetime
        tz = pytz.timezone("Asia/Jerusalem")

        self.worklog1 = WorkLog.objects.create(
            employee=self.employee1,
            check_in=datetime(2025, 10, 9, 9, 0, 0, tzinfo=tz),
            check_out=datetime(2025, 10, 9, 17, 0, 0, tzinfo=tz),
        )

        self.worklog2 = WorkLog.objects.create(
            employee=self.employee1,
            check_in=datetime(2025, 10, 10, 9, 0, 0, tzinfo=tz),
            check_out=datetime(2025, 10, 10, 17, 0, 0, tzinfo=tz),
        )

        self.worklog3 = WorkLog.objects.create(
            employee=self.employee2,
            check_in=datetime(2025, 10, 9, 8, 0, 0, tzinfo=tz),
            check_out=datetime(2025, 10, 9, 16, 0, 0, tzinfo=tz),
        )

        # Clear all October 2025 holidays to ensure clean test state
        Holiday.objects.filter(date__year=2025, date__month=10).delete()

        # Create a holiday (use get_or_create to avoid duplicates)
        self.holiday, _ = Holiday.objects.get_or_create(
            date=date(2025, 10, 10),
            defaults={
                "name": "Yom Kippur",
                "is_holiday": True,
                "is_shabbat": False,
            },
        )

        self.loader = BulkDataLoader()

    def test_load_employees(self):
        """Test loading employees with salaries."""
        employee_ids = [self.employee1.id, self.employee2.id]

        employees_dict = self.loader._load_employees(employee_ids)

        # Check that both employees were loaded
        self.assertEqual(len(employees_dict), 2)
        self.assertIn(self.employee1.id, employees_dict)
        self.assertIn(self.employee2.id, employees_dict)

        # Check employee1 data
        emp1_data = employees_dict[self.employee1.id]
        self.assertIsInstance(emp1_data, EmployeeData)
        self.assertEqual(emp1_data.employee_id, self.employee1.id)
        self.assertEqual(emp1_data.first_name, "John")
        self.assertEqual(emp1_data.last_name, "Doe")
        self.assertEqual(emp1_data.calculation_type, "hourly")
        self.assertEqual(emp1_data.hourly_rate, Decimal("50.00"))

        # Check employee2 data
        emp2_data = employees_dict[self.employee2.id]
        self.assertEqual(emp2_data.calculation_type, "monthly")
        self.assertEqual(emp2_data.base_salary, Decimal("8000.00"))

    def test_load_work_logs(self):
        """Test loading work logs for multiple employees."""
        employee_ids = [self.employee1.id, self.employee2.id]

        work_logs_dict = self.loader._load_work_logs(employee_ids, 2025, 10)

        # Check that work logs were grouped by employee
        self.assertIn(self.employee1.id, work_logs_dict)
        self.assertIn(self.employee2.id, work_logs_dict)

        # Employee1 should have 2 work logs
        emp1_logs = work_logs_dict[self.employee1.id]
        self.assertEqual(len(emp1_logs), 2)
        self.assertIsInstance(emp1_logs[0], WorkLogData)

        # Employee2 should have 1 work log
        emp2_logs = work_logs_dict[self.employee2.id]
        self.assertEqual(len(emp2_logs), 1)

    def test_load_work_logs_filters_by_date(self):
        """Test that work logs are filtered by year and month."""
        # Create a work log in a different month
        tz = pytz.timezone("Asia/Jerusalem")
        WorkLog.objects.create(
            employee=self.employee1,
            check_in=datetime(2025, 11, 9, 9, 0, 0, tzinfo=tz),
            check_out=datetime(2025, 11, 9, 17, 0, 0, tzinfo=tz),
        )

        employee_ids = [self.employee1.id]

        # Load October work logs
        work_logs_dict = self.loader._load_work_logs(employee_ids, 2025, 10)

        # Should only have October logs (2 logs)
        emp1_logs = work_logs_dict[self.employee1.id]
        self.assertEqual(len(emp1_logs), 2)

    def test_load_holidays(self):
        """Test loading holidays for a month."""
        holidays_dict = self.loader._load_holidays(2025, 10)

        # Check that the holiday was loaded
        self.assertEqual(len(holidays_dict), 1)
        self.assertIn(date(2025, 10, 10), holidays_dict)

        holiday_data = holidays_dict[date(2025, 10, 10)]
        self.assertEqual(holiday_data.name, "Yom Kippur")
        self.assertTrue(holiday_data.is_paid)

    @patch("payroll.services.bulk.data_loader.get_shabbat_times")
    def test_load_shabbat_times(self, mock_get_shabbat_times):
        """Test loading Shabbat times for a month."""
        # Mock Shabbat times API
        mock_get_shabbat_times.return_value = {
            "shabbat_start": "2025-10-10T18:00:00Z",
            "shabbat_end": "2025-10-11T19:00:00Z",
        }

        shabbat_times_dict = self.loader._load_shabbat_times(2025, 10)

        # Should have loaded Shabbat times for all Fridays in October 2025
        # October 2025 has 5 Fridays (3, 10, 17, 24, 31)
        # Plus one before and one after = 7 total
        self.assertGreater(len(shabbat_times_dict), 0)

        # Check that API was called
        self.assertTrue(mock_get_shabbat_times.called)

    @patch("payroll.services.bulk.data_loader.get_shabbat_times")
    def test_load_all_data(self, mock_get_shabbat_times):
        """Test loading all data at once."""
        # Mock Shabbat times API
        mock_get_shabbat_times.return_value = {
            "shabbat_start": "2025-10-10T18:00:00Z",
            "shabbat_end": "2025-10-11T19:00:00Z",
        }

        employee_ids = [self.employee1.id, self.employee2.id]

        bulk_data = self.loader.load_all_data(employee_ids, 2025, 10)

        # Check that all data was loaded
        self.assertIsInstance(bulk_data, BulkLoadedData)
        self.assertEqual(len(bulk_data.employees), 2)
        self.assertEqual(bulk_data.year, 2025)
        self.assertEqual(bulk_data.month, 10)

        # Check employees
        self.assertIn(self.employee1.id, bulk_data.employees)
        self.assertIn(self.employee2.id, bulk_data.employees)

        # Check work logs
        self.assertIn(self.employee1.id, bulk_data.work_logs)
        self.assertIn(self.employee2.id, bulk_data.work_logs)

        # Check holidays
        self.assertIn(date(2025, 10, 10), bulk_data.holidays)

        # Check Shabbat times
        self.assertGreater(len(bulk_data.shabbat_times), 0)

    def test_load_all_data_without_shabbat_times(self):
        """Test loading data without Shabbat times."""
        employee_ids = [self.employee1.id]

        bulk_data = self.loader.load_all_data(
            employee_ids, 2025, 10, include_shabbat_times=False
        )

        # Shabbat times should be empty
        self.assertEqual(len(bulk_data.shabbat_times), 0)

    def test_query_count_tracking(self):
        """Test that query count is tracked correctly."""
        employee_ids = [self.employee1.id, self.employee2.id]

        # Reset query count
        self.loader._query_count = 0

        self.loader.load_all_data(
            employee_ids,
            2025,
            10,
            include_shabbat_times=False,  # Skip Shabbat API calls for cleaner test
        )

        # Should have minimal queries:
        # 1. Employees with salaries (prefetch)
        # 2. Work logs
        # 3. Holidays
        # Total: ~3 queries
        self.assertLessEqual(self.loader.query_count, 5)

    def test_employee_without_salary(self):
        """Test handling of employee without active salary."""
        # Create employee without salary
        user3 = User.objects.create_user(
            username="testuser3", email="test3@example.com"
        )
        employee3 = Employee.objects.create(
            user=user3,
            first_name="No",
            last_name="Salary",
            email="nosalary@example.com",
            is_active=True,
        )

        employee_ids = [employee3.id]

        employees_dict = self.loader._load_employees(employee_ids)

        # Employee without salary should be skipped
        self.assertEqual(len(employees_dict), 0)

    def test_get_fridays_in_range(self):
        """Test getting all Fridays in a date range."""
        start_date = date(2025, 10, 1)
        end_date = date(2025, 10, 31)

        fridays = self.loader._get_fridays_in_range(start_date, end_date)

        # October 2025 has 5 Fridays: 3, 10, 17, 24, 31
        self.assertEqual(len(fridays), 5)
        self.assertEqual(fridays[0], date(2025, 10, 3))
        self.assertEqual(fridays[4], date(2025, 10, 31))

    def test_fallback_shabbat_times(self):
        """Test fallback Shabbat times generation."""
        friday = date(2025, 10, 10)

        fallback_times = self.loader._get_fallback_shabbat_times(friday)

        # Check that fallback times were generated
        self.assertEqual(fallback_times.friday_date, friday)
        self.assertEqual(fallback_times.source, "fallback")

        # Check times are reasonable (Friday 18:00 - Saturday 19:00)
        self.assertEqual(fallback_times.shabbat_start.hour, 18)
        self.assertEqual(fallback_times.shabbat_end.hour, 19)
