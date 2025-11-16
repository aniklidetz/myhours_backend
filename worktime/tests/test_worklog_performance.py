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


class WorkLogOverlapOptimizationTest(TestCase):
    """Test O(N²) -> O(1) overlap validation optimization (Issue #5)"""

    def setUp(self):
        """Set up test data"""
        from django.contrib.auth.models import User

        self.user = User.objects.create_user(
            username="overlapuser", email="overlap@example.com", password="test123"
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Overlap",
            last_name="Test",
            email="overlap@example.com",
            employment_type="full_time",
            role="employee",
        )

    def test_overlap_validation_query_count(self):
        """Test that overlap validation uses single database query, not loop"""
        base_time = timezone.now()

        # Create 100 non-overlapping work logs
        for i in range(100):
            WorkLog.objects.create(
                employee=self.employee,
                check_in=base_time + timedelta(days=i, hours=8),
                check_out=base_time + timedelta(days=i, hours=16),
            )

        # Reset query counter
        from django.conf import settings

        settings.DEBUG = True
        from django.db import reset_queries

        reset_queries()

        # Create new non-overlapping log
        # Should use O(1) query (single EXISTS check), not O(N) loop
        new_log = WorkLog.objects.create(
            employee=self.employee,
            check_in=base_time + timedelta(days=200, hours=8),
            check_out=base_time + timedelta(days=200, hours=16),
        )

        # Count queries - should be minimal (insert + validation check)
        query_count = len(connection.queries)

        # OPTIMIZED: Should use EXISTS query for overlap check, not iterate through all logs
        # Note: Total queries may include signals (payroll, notifications)
        # The key is that validation doesn't scale with number of existing logs
        # With 100 existing logs, should not have 100+ queries from validation loop
        self.assertLessEqual(
            query_count,
            30,
            f"Too many queries ({query_count}). Expected <=30 (includes signals)",
        )

    def test_overlap_validation_performance_with_many_logs(self):
        """Test validation performance scales O(1), not O(N)"""
        base_time = timezone.now()

        # Create 1000 work logs
        for i in range(1000):
            WorkLog.objects.create(
                employee=self.employee,
                check_in=base_time + timedelta(days=i, hours=8),
                check_out=base_time + timedelta(days=i, hours=16),
            )

        # Time the validation
        start_time = time.time()
        new_log = WorkLog.objects.create(
            employee=self.employee,
            check_in=base_time + timedelta(days=2000, hours=8),
            check_out=base_time + timedelta(days=2000, hours=16),
        )
        end_time = time.time()

        validation_time = end_time - start_time

        # Should be fast even with 1000 existing logs
        # Old O(N²) would iterate through all 1000 logs in Python
        # New O(1) uses database EXISTS query
        self.assertLess(
            validation_time,
            2.0,
            f"Validation took {validation_time:.2f}s with 1000 logs. Expected <2s",
        )

    def test_overlap_detection_still_works(self):
        """Verify overlap detection still correctly identifies overlaps"""
        base_time = timezone.now()

        # Create initial log
        WorkLog.objects.create(
            employee=self.employee,
            check_in=base_time,
            check_out=base_time + timedelta(hours=8),
        )

        # Test various overlap scenarios
        overlap_cases = [
            # Starts during existing session
            (base_time + timedelta(hours=2), base_time + timedelta(hours=10)),
            # Ends during existing session
            (base_time - timedelta(hours=2), base_time + timedelta(hours=2)),
            # Completely overlaps existing session
            (base_time - timedelta(hours=1), base_time + timedelta(hours=9)),
            # Completely within existing session
            (base_time + timedelta(hours=2), base_time + timedelta(hours=6)),
        ]

        for check_in, check_out in overlap_cases:
            with self.assertRaises(
                ValidationError,
                msg=f"Failed to detect overlap: {check_in} - {check_out}",
            ):
                WorkLog.objects.create(
                    employee=self.employee,
                    check_in=check_in,
                    check_out=check_out,
                )

    def test_no_false_positives_for_adjacent_sessions(self):
        """Verify adjacent sessions are not flagged as overlapping"""
        base_time = timezone.now()

        # Create initial session: 08:00 - 16:00
        WorkLog.objects.create(
            employee=self.employee,
            check_in=base_time,
            check_out=base_time + timedelta(hours=8),
        )

        # Adjacent session starting right after: 16:00 - 20:00
        # Should NOT raise ValidationError
        adjacent_log = WorkLog.objects.create(
            employee=self.employee,
            check_in=base_time + timedelta(hours=8),
            check_out=base_time + timedelta(hours=12),
        )

        self.assertIsNotNone(adjacent_log.pk)


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
