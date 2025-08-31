"""
Performance tests for WorkLog race condition fixes
"""

import threading
import time
from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from users.models import Employee
from worktime.models import WorkLog


class WorkLogPerformanceTest(TransactionTestCase):
    """Test performance impact of race condition fixes"""

    def setUp(self):
        """Set up test data"""
        from django.contrib.auth.models import User

        self.user = User.objects.create_user(
            username="perfuser", email="perf@example.com", password="test123"
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Performance",
            last_name="Employee",
            email="perf@example.com",
            employment_type="full_time",
            role="employee",
        )

    def test_basic_worklog_creation_performance(self):
        """Test that basic worklog creation is performant"""
        base_time = timezone.now()

        start_time = time.time()
        worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=base_time,
            check_out=base_time + timedelta(hours=8),
        )
        end_time = time.time()

        creation_time = end_time - start_time
        self.assertLess(creation_time, 1.0, "WorkLog creation took too long")

        # Clean up
        worklog.delete()

    def test_validation_with_existing_logs(self):
        """Test validation performance with existing work logs"""
        base_time = timezone.now()

        # Create some existing work logs
        existing_logs = []
        for i in range(10):
            worklog = WorkLog.objects.create(
                employee=self.employee,
                check_in=base_time + timedelta(days=i, hours=8),
                check_out=base_time + timedelta(days=i, hours=16),
            )
            existing_logs.append(worklog)

        # Test creating new non-overlapping log
        start_time = time.time()
        new_worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=base_time + timedelta(days=20, hours=8),
            check_out=base_time + timedelta(days=20, hours=16),
        )
        end_time = time.time()

        validation_time = end_time - start_time
        self.assertLess(
            validation_time, 1.0, "Validation took too long with existing logs"
        )

        # Clean up
        for worklog in existing_logs + [new_worklog]:
            worklog.delete()

    def test_overlapping_validation_performance(self):
        """Test that overlap validation fails quickly"""
        base_time = timezone.now()

        # Create initial worklog
        initial_worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=base_time,
            check_out=base_time + timedelta(hours=8),
        )

        # Test overlapping creation (should fail quickly)
        start_time = time.time()
        with self.assertRaises(ValidationError):
            WorkLog.objects.create(
                employee=self.employee,
                check_in=base_time + timedelta(hours=2),
                check_out=base_time + timedelta(hours=10),
            )
        end_time = time.time()

        validation_time = end_time - start_time
        self.assertLess(validation_time, 0.5, "Overlap validation took too long")

        # Clean up
        initial_worklog.delete()


class WorkLogBasicTest(TestCase):
    """Basic tests for WorkLog functionality"""

    def setUp(self):
        """Set up test data"""
        from django.contrib.auth.models import User

        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="test123"
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Test",
            last_name="Employee",
            email="test@example.com",
            employment_type="full_time",
            role="employee",
        )

    def test_worklog_creation(self):
        """Test basic worklog creation"""
        base_time = timezone.now()
        worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=base_time,
            check_out=base_time + timedelta(hours=8),
        )

        self.assertIsNotNone(worklog.pk)
        self.assertEqual(worklog.employee, self.employee)
        self.assertIsNotNone(worklog.check_in)
        self.assertIsNotNone(worklog.check_out)

    def test_worklog_string_representation(self):
        """Test worklog string representation"""
        base_time = timezone.now()
        worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=base_time,
            check_out=base_time + timedelta(hours=8),
        )

        str_repr = str(worklog)
        self.assertIn(self.employee.get_full_name(), str_repr)

    def test_worklog_hours_calculation(self):
        """Test worklog hours calculation if available"""
        base_time = timezone.now()
        worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=base_time,
            check_out=base_time + timedelta(hours=8),
        )

        # If worklog has hours_worked field, test it
        if hasattr(worklog, "hours_worked"):
            self.assertGreater(worklog.hours_worked, 0)
            self.assertLessEqual(worklog.hours_worked, 24)
