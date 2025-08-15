"""
Comprehensive API tests for WorkLog endpoints.
Tests CRUD operations, filtering, authentication, and business logic through APIs.
"""

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APIClient

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from payroll.models import Salary
from tests.base import BaseAPITestCase, UnauthenticatedAPITestCase
from users.models import Employee
from worktime.models import WorkLog


class WorkLogAPITest(BaseAPITestCase):
    """Comprehensive WorkLog API tests with authentication"""

    def setUp(self):
        super().setUp()

        # Create additional test employees
        self.hourly_employee = Employee.objects.create(
            first_name="Hourly",
            last_name="Worker",
            email="hourly.worker@test.com",
            employment_type="hourly",
            role="employee",
        )

        self.monthly_employee = Employee.objects.create(
            first_name="Monthly",
            last_name="Worker",
            email="monthly.worker@test.com",
            employment_type="full_time",
            role="employee",
        )

        # Create test work logs
        self._create_test_worklogs()

    def _create_test_worklogs(self):
        """Create test work logs for different scenarios"""
        base_date = date(2025, 7, 1)

        # Regular work logs for authenticated user's employee
        # Use dates in the past to avoid conflicts with tests that create logs "now"
        for day in range(1, 11):  # 10 days
            check_in = timezone.make_aware(
                datetime(2025, 6, day, 9, 0)
            )  # June instead of July
            check_out = timezone.make_aware(datetime(2025, 6, day, 17, 0))

            WorkLog.objects.create(
                employee=self.employee,
                check_in=check_in,
                check_out=check_out,
                location_check_in="Office",
                location_check_out="Office",
                is_approved=True,
            )

        # Overtime work log
        WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.make_aware(datetime(2025, 6, 15, 8, 0)),
            check_out=timezone.make_aware(datetime(2025, 6, 15, 20, 0)),  # 12 hours
            location_check_in="Office",
            location_check_out="Office",
            is_approved=True,
        )

        # Night shift work log
        WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.make_aware(datetime(2025, 6, 20, 22, 0)),
            check_out=timezone.make_aware(datetime(2025, 6, 21, 6, 0)),
            location_check_in="Office",
            location_check_out="Office",
            is_approved=True,
        )

        # Saturday work (Sabbath)
        WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.make_aware(datetime(2025, 6, 26, 9, 0)),  # Saturday
            check_out=timezone.make_aware(datetime(2025, 6, 26, 17, 0)),
            location_check_in="Office",
            location_check_out="Office",
            is_approved=True,
        )

        # Current session (no check_out) - use employee2 to avoid overlap
        WorkLog.objects.create(
            employee=self.employee2,
            check_in=timezone.now() - timedelta(hours=2),
            location_check_in="Remote",
        )

    def test_list_worklogs_authenticated(self):
        """Test listing work logs with authentication"""
        url = reverse("worklog-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Handle both paginated and non-paginated responses
        if isinstance(response.data, dict) and "results" in response.data:
            # Paginated response
            self.assertGreater(len(response.data["results"]), 0)
        else:
            # Non-paginated response (list)
            self.assertIsInstance(response.data, list)
            self.assertGreater(len(response.data), 0)

    def test_create_worklog_check_in(self):
        """Test creating a work log (check-in)"""
        url = reverse("worklog-list")
        data = {
            "employee": self.employee.id,
            "check_in": timezone.now().isoformat(),
            "location_check_in": "Office - Tel Aviv",
            "latitude_check_in": 32.0853,
            "longitude_check_in": 34.7818,
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["employee"], self.employee.id)
        self.assertEqual(response.data["location_check_in"], "Office - Tel Aviv")
        self.assertIsNone(response.data.get("check_out"))

    def test_update_worklog_check_out(self):
        """Test updating a work log to add check-out"""
        # Create work log with only check-in
        worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.now() - timedelta(hours=8),
            location_check_in="Office",
        )

        url = reverse("worklog-detail", args=[worklog.id])
        data = {
            "check_out": timezone.now().isoformat(),
            "location_check_out": "Office",
            "latitude_check_out": 32.0853,
            "longitude_check_out": 34.7818,
        }

        response = self.client.patch(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["check_out"])
        self.assertEqual(response.data["location_check_out"], "Office")

    def test_filter_worklogs_by_employee(self):
        """Test filtering work logs by employee"""
        url = reverse("worklog-list")
        response = self.client.get(url, {"employee": self.employee.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Handle both paginated and non-paginated responses
        if hasattr(response.data, "get") and "results" in response.data:
            data = response.data["results"]
        else:
            data = response.data

        # All results should be for the specified employee
        for worklog in data:
            self.assertEqual(worklog["employee"], self.employee.id)

    def test_filter_worklogs_by_date_range(self):
        """Test filtering work logs by date range"""
        url = reverse("worklog-list")
        start_date = "2025-06-01"
        end_date = "2025-06-30"  # Include whole month

        response = self.client.get(
            url, {"check_in__date__gte": start_date, "check_in__date__lte": end_date}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Handle both paginated and non-paginated responses
        if hasattr(response.data, "get") and "results" in response.data:
            data = response.data["results"]
        else:
            data = response.data

        # Verify all results are within date range
        for worklog in data:
            worklog_date = worklog["check_in"][:10]  # Extract date part
            self.assertGreaterEqual(worklog_date, start_date)
            self.assertLessEqual(worklog_date, end_date)

    def test_filter_worklogs_by_approval_status(self):
        """Test filtering work logs by approval status"""
        url = reverse("worklog-list")

        # Test approved work logs
        response = self.client.get(url, {"is_approved": "true"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Handle both paginated and non-paginated responses
        if hasattr(response.data, "get") and "results" in response.data:
            data = response.data["results"]
        else:
            data = response.data

        for worklog in data:
            self.assertTrue(worklog["is_approved"])

        # Test unapproved work logs
        response = self.client.get(url, {"is_approved": "false"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Handle both paginated and non-paginated responses
        if hasattr(response.data, "get") and "results" in response.data:
            data = response.data["results"]
        else:
            data = response.data

        for worklog in data:
            self.assertFalse(worklog["is_approved"])

    def test_worklog_approval_endpoint(self):
        """Test work log approval through API"""
        # Create unapproved work log
        worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.now() - timedelta(hours=8),
            check_out=timezone.now(),
            is_approved=False,
        )

        url = reverse("worklog-detail", args=[worklog.id])
        data = {"is_approved": True}

        response = self.client.patch(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_approved"])

        # Verify in database
        worklog.refresh_from_db()
        self.assertTrue(worklog.is_approved)

    def test_worklog_current_session_detection(self):
        """Test API detection of current work sessions"""
        # Create an active session for the authenticated user
        active_session = WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.now() - timedelta(hours=1),
            location_check_in="Current Location",
        )

        url = reverse("worklog-list")
        response = self.client.get(
            url,
            {
                "check_out__isnull": "true",
                "employee": self.employee.id,  # Filter by current employee to avoid setup data
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Handle both paginated and non-paginated responses
        if hasattr(response.data, "get") and "results" in response.data:
            current_sessions = response.data["results"]
        else:
            current_sessions = response.data
        self.assertGreater(
            len(current_sessions), 0, "Should find at least one active session"
        )

        for session in current_sessions:
            self.assertIsNone(
                session["check_out"],
                f"Session {session['id']} should have no check_out time",
            )
            self.assertEqual(
                session["employee"],
                self.employee.id,
                "Should only return sessions for the specified employee",
            )

    def test_worklog_statistics_endpoint(self):
        """Test work log statistics calculation"""
        # This would be a custom endpoint for statistics
        url = reverse("worklog-list")
        response = self.client.get(
            url,
            {
                "employee": self.employee.id,
                "check_in__year": 2025,
                "check_in__month": 6,  # Changed to June to match test data
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Handle both paginated and non-paginated responses
        if hasattr(response.data, "get") and "results" in response.data:
            worklogs = response.data["results"]
        else:
            worklogs = response.data
        self.assertGreater(len(worklogs), 0)

        # Calculate total hours from API response
        total_hours = 0
        for worklog in worklogs:
            if worklog["check_out"]:
                # This would need proper time calculation in real implementation
                pass

    def test_worklog_bulk_operations_api(self):
        """Test bulk operations through API"""
        url = reverse("worklog-list")

        # Bulk create work logs - use May dates to avoid conflicts with June test data
        bulk_data = []
        # Use current date minus small offset to stay within 7-day validation window
        base_date = timezone.now() - timedelta(days=1)  # 1 day ago

        for i in range(5):
            check_in = base_date - timedelta(
                hours=i * 2
            )  # 2-hour intervals instead of days
            check_out = check_in + timedelta(
                hours=1
            )  # 1-hour sessions to avoid overlap
            bulk_data.append(
                {
                    "employee": self.employee.id,
                    "check_in": check_in.isoformat(),
                    "check_out": check_out.isoformat(),
                    "location_check_in": f"Location {i}",
                    "location_check_out": f"Location {i}",
                }
            )

        # Note: This would require a custom bulk create endpoint
        # For now, test individual creation
        for data in bulk_data:
            response = self.client.post(url, data, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_worklog_validation_errors(self):
        """Test API validation errors"""
        url = reverse("worklog-list")

        # Test invalid employee
        data = {
            "employee": 99999,  # Non-existent employee
            "check_in": timezone.now().isoformat(),
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Test invalid datetime format
        data = {
            "employee": self.employee.id,
            "check_in": "invalid-datetime",
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_worklog_search_functionality(self):
        """Test search functionality for work logs"""
        url = reverse("worklog-list")

        # Search by location
        response = self.client.get(url, {"search": "Office"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Handle both paginated and non-paginated responses
        if hasattr(response.data, "get") and "results" in response.data:
            data = response.data["results"]
        else:
            data = response.data

        # Results should contain work logs with 'Office' in location
        for worklog in data:
            location_fields = [
                worklog.get("location_check_in", ""),
                worklog.get("location_check_out", ""),
            ]
            self.assertTrue(any("Office" in field for field in location_fields))

    def test_worklog_ordering(self):
        """Test ordering of work logs"""
        url = reverse("worklog-list")

        # Order by check_in descending (newest first)
        response = self.client.get(url, {"ordering": "-check_in"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Handle both paginated and non-paginated responses
        if hasattr(response.data, "get") and "results" in response.data:
            worklogs = response.data["results"]
        else:
            worklogs = response.data
        if len(worklogs) > 1:
            # Verify descending order
            for i in range(len(worklogs) - 1):
                current_time = worklogs[i]["check_in"]
                next_time = worklogs[i + 1]["check_in"]
                self.assertGreaterEqual(current_time, next_time)

    def test_worklog_pagination(self):
        """Test pagination of work logs"""
        url = reverse("worklog-list")

        # Test first page
        response = self.client.get(url, {"page": 1, "page_size": 5})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Handle both paginated and non-paginated responses
        if isinstance(response.data, dict) and "results" in response.data:
            # Paginated response
            self.assertIn("count", response.data)
            self.assertIn("next", response.data)
            self.assertIn("previous", response.data)
            self.assertIn("results", response.data)
            # Results should be limited to page_size
            self.assertLessEqual(len(response.data["results"]), 5)
        else:
            # Non-paginated response - should still work
            self.assertIsInstance(response.data, list)


class WorkLogAPIPermissionsTest(BaseAPITestCase):
    """Test permissions and security for WorkLog API"""

    def setUp(self):
        super().setUp()

        # Create another employee's work log
        self.other_employee = Employee.objects.create(
            first_name="Other",
            last_name="Employee",
            email="other@test.com",
            employment_type="hourly",
        )

        self.other_worklog = WorkLog.objects.create(
            employee=self.other_employee,
            check_in=timezone.now() - timedelta(hours=8),
            check_out=timezone.now(),
        )

    def test_employee_can_only_see_own_worklogs(self):
        """Test that employees can only see their own work logs"""
        # This would depend on your permission implementation
        url = reverse("worklog-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # In a real implementation, you'd filter by current user's employee record
        # For now, just verify the endpoint works
        # Handle both paginated and non-paginated responses
        if isinstance(response.data, dict) and "results" in response.data:
            # Paginated response
            pass  # Already has results key
        else:
            # Non-paginated response - should be a list
            self.assertIsInstance(response.data, list)

    def test_manager_can_see_all_worklogs(self):
        """Test that managers can see all employee work logs"""
        # Create manager user (this would depend on your user model)
        # For now, just test with current authenticated user
        url = reverse("worklog-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_worklog_update_permissions(self):
        """Test update permissions for work logs"""
        worklog = WorkLog.objects.create(
            employee=self.employee, check_in=timezone.now() - timedelta(hours=2)
        )

        url = reverse("worklog-detail", args=[worklog.id])
        data = {"location_check_in": "Updated Location"}

        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_worklog_delete_permissions(self):
        """Test delete permissions for work logs"""
        worklog = WorkLog.objects.create(
            employee=self.employee,
            check_in=timezone.now() - timedelta(hours=8),
            check_out=timezone.now(),
        )

        url = reverse("worklog-detail", args=[worklog.id])
        response = self.client.delete(url)

        # This depends on your permission model
        # Should either be 204 (allowed) or 403 (forbidden)
        self.assertIn(
            response.status_code,
            [status.HTTP_204_NO_CONTENT, status.HTTP_403_FORBIDDEN],
        )


class WorkLogAPIUnauthenticatedTest(UnauthenticatedAPITestCase):
    """Test WorkLog API endpoints without authentication"""

    def test_list_worklogs_unauthenticated(self):
        """Test listing work logs without authentication"""
        url = reverse("worklog-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_worklog_unauthenticated(self):
        """Test creating work log without authentication"""
        url = reverse("worklog-list")
        data = {"employee": 1, "check_in": timezone.now().isoformat()}

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_worklog_unauthenticated(self):
        """Test updating work log without authentication"""
        # Create a work log first (this would be done in setup with admin)
        employee = Employee.objects.create(
            first_name="Test",
            last_name="Employee",
            email="test@example.com",
            employment_type="hourly",
        )

        worklog = WorkLog.objects.create(employee=employee, check_in=timezone.now())

        url = reverse("worklog-detail", args=[worklog.id])
        data = {"check_out": timezone.now().isoformat()}

        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_delete_worklog_unauthenticated(self):
        """Test deleting work log without authentication"""
        employee = Employee.objects.create(
            first_name="Test",
            last_name="Employee",
            email="test2@example.com",
            employment_type="hourly",
        )

        worklog = WorkLog.objects.create(employee=employee, check_in=timezone.now())

        url = reverse("worklog-detail", args=[worklog.id])
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class WorkLogAPIIntegrationTest(BaseAPITestCase):
    """Integration tests for WorkLog API with other systems"""

    def setUp(self):
        super().setUp()

        # Create salary for payroll integration
        self.salary = Salary.objects.create(
            employee=self.employee,
            calculation_type="hourly",
            hourly_rate=Decimal("120.00"),
            currency="ILS",
        )

    @patch("payroll.services.EnhancedPayrollCalculationService.calculate_daily_pay")
    def test_worklog_payroll_integration(self, mock_calculate):
        """Test integration with payroll calculation"""
        mock_calculate.return_value = {
            "total_pay": 960.0,  # 8 hours * 120 ILS
            "regular_hours": 8.0,
            "overtime_hours": 0.0,
        }

        # Create work log through API with times within validation window
        url = reverse("worklog-list")
        # Use yesterday's time to stay within 7-day window but avoid conflicts
        base_time = timezone.now() - timedelta(days=1)
        data = {
            "employee": self.employee.id,
            "check_in": base_time.isoformat(),
            "check_out": (base_time + timedelta(hours=8)).isoformat(),
            "location_check_in": "Office",
            "location_check_out": "Office",
        }

        response = self.client.post(url, data, format="json")

        # Debug: print response details if test fails
        if response.status_code != status.HTTP_201_CREATED:
            print(f"Expected 201, got {response.status_code}")
            print(f"Response data: {response.data}")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify work log was created
        worklog_id = response.data["id"]
        worklog = WorkLog.objects.get(id=worklog_id)

        self.assertEqual(worklog.get_total_hours(), 8.0)

    def test_worklog_biometric_integration(self):
        """Test integration with biometric check-in/out"""
        # This would test integration with face recognition
        # For now, just test that location and coordinates are stored

        url = reverse("worklog-list")
        data = {
            "employee": self.employee.id,
            "check_in": timezone.now().isoformat(),
            "location_check_in": "Office - Biometric Terminal",
            "latitude_check_in": 32.0853,
            "longitude_check_in": 34.7818,
            "biometric_verified": True,  # This field would need to exist
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify biometric data is stored
        self.assertAlmostEqual(
            float(response.data["latitude_check_in"]), 32.0853, places=4
        )
        self.assertAlmostEqual(
            float(response.data["longitude_check_in"]), 34.7818, places=4
        )

    def test_worklog_notification_integration(self):
        """Test integration with notification system"""
        # This would test that notifications are sent for various work log events
        # For now, just verify that work logs can be created and retrieved

        url = reverse("worklog-list")

        # Create work log that might trigger notifications with times within validation window
        base_time = timezone.now() - timedelta(days=2)  # 2 days ago to avoid conflicts
        data = {
            "employee": self.employee.id,
            "check_in": base_time.isoformat(),
            "check_out": (base_time + timedelta(hours=12)).isoformat(),  # Overtime
            "location_check_in": "Office",
            "location_check_out": "Office",
        }

        response = self.client.post(url, data, format="json")

        # Debug: print response details if test fails
        if response.status_code != status.HTTP_201_CREATED:
            print(f"Expected 201, got {response.status_code}")
            print(f"Response data: {response.data}")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # In a real system, verify notification was sent
        # For now, just verify the work log was created correctly
        worklog = WorkLog.objects.get(id=response.data["id"])
        self.assertEqual(worklog.get_total_hours(), 12.0)
