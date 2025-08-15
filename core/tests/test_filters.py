"""
Tests for core filters - Django filter classes for API filtering.
"""

from datetime import date, datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from core.filters import WorkLogFilter
from users.models import Employee
from worktime.models import WorkLog


class WorkLogFilterTest(TestCase):
    """Tests for WorkLogFilter"""

    def setUp(self):
        """Set up test data"""
        # Create test user and employee
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="test123"
        )

        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Test",
            last_name="User",
            email="test@example.com",
            employment_type="full_time",
            role="employee",
        )

        # Create test work logs with different dates
        self.today = timezone.now().date()
        self.yesterday = self.today - timezone.timedelta(days=1)
        self.tomorrow = self.today + timezone.timedelta(days=1)

        # Work log for today
        self.worklog_today = WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.make_aware(
                datetime.combine(self.today, datetime.min.time().replace(hour=9))
            ),
            check_out=timezone.make_aware(
                datetime.combine(self.today, datetime.min.time().replace(hour=17))
            ),
        )

        # Work log for yesterday
        self.worklog_yesterday = WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.make_aware(
                datetime.combine(self.yesterday, datetime.min.time().replace(hour=9))
            ),
            check_out=timezone.make_aware(
                datetime.combine(self.yesterday, datetime.min.time().replace(hour=17))
            ),
        )

        # Work log for tomorrow
        self.worklog_tomorrow = WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.make_aware(
                datetime.combine(self.tomorrow, datetime.min.time().replace(hour=9))
            ),
            check_out=timezone.make_aware(
                datetime.combine(self.tomorrow, datetime.min.time().replace(hour=17))
            ),
        )

    def test_filter_by_date_today(self):
        """Test filtering work logs by today's date"""
        filter_set = WorkLogFilter(
            data={"date": self.today}, queryset=WorkLog.objects.all()
        )

        self.assertTrue(filter_set.is_valid())
        filtered_queryset = filter_set.qs

        # Should only return today's work log
        self.assertEqual(filtered_queryset.count(), 1)
        self.assertEqual(filtered_queryset.first().id, self.worklog_today.id)

    def test_filter_by_date_yesterday(self):
        """Test filtering work logs by yesterday's date"""
        filter_set = WorkLogFilter(
            data={"date": self.yesterday}, queryset=WorkLog.objects.all()
        )

        self.assertTrue(filter_set.is_valid())
        filtered_queryset = filter_set.qs

        # Should only return yesterday's work log
        self.assertEqual(filtered_queryset.count(), 1)
        self.assertEqual(filtered_queryset.first().id, self.worklog_yesterday.id)

    def test_filter_by_date_tomorrow(self):
        """Test filtering work logs by tomorrow's date"""
        filter_set = WorkLogFilter(
            data={"date": self.tomorrow}, queryset=WorkLog.objects.all()
        )

        self.assertTrue(filter_set.is_valid())
        filtered_queryset = filter_set.qs

        # Should only return tomorrow's work log
        self.assertEqual(filtered_queryset.count(), 1)
        self.assertEqual(filtered_queryset.first().id, self.worklog_tomorrow.id)

    def test_filter_by_nonexistent_date(self):
        """Test filtering by a date with no work logs"""
        nonexistent_date = self.today + timezone.timedelta(days=10)

        filter_set = WorkLogFilter(
            data={"date": nonexistent_date}, queryset=WorkLog.objects.all()
        )

        self.assertTrue(filter_set.is_valid())
        filtered_queryset = filter_set.qs

        # Should return empty queryset
        self.assertEqual(filtered_queryset.count(), 0)

    def test_no_date_filter(self):
        """Test that without date filter, all work logs are returned"""
        filter_set = WorkLogFilter(data={}, queryset=WorkLog.objects.all())

        self.assertTrue(filter_set.is_valid())
        filtered_queryset = filter_set.qs

        # Should return all work logs
        self.assertEqual(filtered_queryset.count(), 3)

    def test_invalid_date_format(self):
        """Test handling of invalid date format"""
        filter_set = WorkLogFilter(
            data={"date": "invalid-date"}, queryset=WorkLog.objects.all()
        )

        # Filter should be invalid with wrong date format
        self.assertFalse(filter_set.is_valid())

    def test_date_filter_field_mapping(self):
        """Test that date filter correctly maps to check_in field"""
        # This test verifies the filter uses check_in field with date lookup
        filter_set = WorkLogFilter()

        # Check that the date filter exists and has correct configuration
        self.assertIn("date", filter_set.filters)
        date_filter = filter_set.filters["date"]

        self.assertEqual(date_filter.field_name, "check_in")
        self.assertEqual(date_filter.lookup_expr, "date")

    def test_filter_with_string_date(self):
        """Test filtering with date as string"""
        date_string = self.today.strftime("%Y-%m-%d")

        filter_set = WorkLogFilter(
            data={"date": date_string}, queryset=WorkLog.objects.all()
        )

        self.assertTrue(filter_set.is_valid())
        filtered_queryset = filter_set.qs

        # Should return today's work log
        self.assertEqual(filtered_queryset.count(), 1)
        self.assertEqual(filtered_queryset.first().id, self.worklog_today.id)

    def test_filter_meta_configuration(self):
        """Test filter meta configuration"""
        filter_set = WorkLogFilter()

        # Check meta configuration
        self.assertEqual(filter_set._meta.model, WorkLog)
        self.assertEqual(filter_set._meta.fields, [])

    def test_filter_inheritance(self):
        """Test that WorkLogFilter inherits from FilterSet"""
        import django_filters

        self.assertTrue(issubclass(WorkLogFilter, django_filters.FilterSet))

    def test_filter_queryset_preservation(self):
        """Test that filter preserves original queryset when no filters applied"""
        original_queryset = WorkLog.objects.all().order_by("id")

        filter_set = WorkLogFilter(data={}, queryset=original_queryset)

        filtered_queryset = filter_set.qs

        # Should preserve the original queryset
        self.assertEqual(list(filtered_queryset), list(original_queryset))

    def test_multiple_worklogs_same_date(self):
        """Test filtering when multiple work logs exist for the same date"""
        # Create another work log for today
        worklog_today_2 = WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.make_aware(
                datetime.combine(self.today, datetime.min.time().replace(hour=18))
            ),
            check_out=timezone.make_aware(
                datetime.combine(self.today, datetime.min.time().replace(hour=22))
            ),
        )

        filter_set = WorkLogFilter(
            data={"date": self.today}, queryset=WorkLog.objects.all()
        )

        filtered_queryset = filter_set.qs

        # Should return both work logs for today
        self.assertEqual(filtered_queryset.count(), 2)
        worklog_ids = set(worklog.id for worklog in filtered_queryset)
        expected_ids = {self.worklog_today.id, worklog_today_2.id}
        self.assertEqual(worklog_ids, expected_ids)

    def test_filter_with_datetime_object(self):
        """Test filtering with datetime object (should extract date part)"""
        today_datetime = timezone.make_aware(
            datetime.combine(self.today, datetime.min.time().replace(hour=12))
        )

        filter_set = WorkLogFilter(
            data={"date": today_datetime.date()}, queryset=WorkLog.objects.all()
        )

        self.assertTrue(filter_set.is_valid())
        filtered_queryset = filter_set.qs

        # Should return today's work log
        self.assertEqual(filtered_queryset.count(), 1)
        self.assertEqual(filtered_queryset.first().id, self.worklog_today.id)

    def test_filter_empty_queryset(self):
        """Test filter behavior with empty initial queryset"""
        empty_queryset = WorkLog.objects.none()

        filter_set = WorkLogFilter(data={"date": self.today}, queryset=empty_queryset)

        filtered_queryset = filter_set.qs

        # Should remain empty
        self.assertEqual(filtered_queryset.count(), 0)

    def test_filter_case_sensitivity(self):
        """Test that filter parameter names are case sensitive"""
        # Using wrong case should not apply the filter
        filter_set = WorkLogFilter(
            data={"DATE": self.today}, queryset=WorkLog.objects.all()  # Wrong case
        )

        filtered_queryset = filter_set.qs

        # Should return all work logs (filter not applied)
        self.assertEqual(filtered_queryset.count(), 3)

    def test_worklog_across_midnight_filter(self):
        """Test filtering work logs that span across midnight"""
        # Create work log that starts today and ends tomorrow
        worklog_midnight = WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.make_aware(
                datetime.combine(self.today, datetime.min.time().replace(hour=23))
            ),
            check_out=timezone.make_aware(
                datetime.combine(self.tomorrow, datetime.min.time().replace(hour=1))
            ),
        )

        # Filter by today's date
        filter_set = WorkLogFilter(
            data={"date": self.today}, queryset=WorkLog.objects.all()
        )

        filtered_queryset = filter_set.qs

        # Should include both today's regular work log and the midnight-spanning one
        # because the check_in date is what matters for filtering
        self.assertEqual(filtered_queryset.count(), 2)
        worklog_ids = set(worklog.id for worklog in filtered_queryset)
        expected_ids = {self.worklog_today.id, worklog_midnight.id}
        self.assertEqual(worklog_ids, expected_ids)

    def test_filter_boundary_conditions(self):
        """Test filter with edge cases and boundary conditions"""
        # Test with very old date
        very_old_date = date(1900, 1, 1)
        filter_set = WorkLogFilter(
            data={"date": very_old_date}, queryset=WorkLog.objects.all()
        )

        self.assertTrue(filter_set.is_valid())
        self.assertEqual(filter_set.qs.count(), 0)

        # Test with future date far in the future
        far_future_date = date(2100, 12, 31)
        filter_set = WorkLogFilter(
            data={"date": far_future_date}, queryset=WorkLog.objects.all()
        )

        self.assertTrue(filter_set.is_valid())
        self.assertEqual(filter_set.qs.count(), 0)
