"""
Integration tests for Bulk Payroll API endpoints.
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytz
from rest_framework import status
from rest_framework.test import APIClient

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from payroll.models import Salary
from payroll.services.bulk.types import BulkCalculationResult
from payroll.services.contracts import PayrollResult
from users.models import Employee
from worktime.models import WorkLog


class BulkPayrollAPITestCase(TestCase):
    """Integration tests for bulk payroll API endpoints."""

    def setUp(self):
        """Set up test data."""
        # Create admin user
        self.admin_user = User.objects.create_user(
            username="admin", email="admin@example.com", password="admin123"
        )

        self.admin_employee = Employee.objects.create(
            user=self.admin_user,
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
            role="admin",
            is_active=True,
        )

        # Create accountant user
        self.accountant_user = User.objects.create_user(
            username="accountant", email="accountant@example.com", password="acc123"
        )

        self.accountant_employee = Employee.objects.create(
            user=self.accountant_user,
            first_name="Accountant",
            last_name="User",
            email="accountant@example.com",
            role="accountant",
            is_active=True,
        )

        # Create regular user (non-admin, non-accountant)
        self.regular_user = User.objects.create_user(
            username="regular", email="regular@example.com", password="reg123"
        )

        self.regular_employee = Employee.objects.create(
            user=self.regular_user,
            first_name="Regular",
            last_name="User",
            email="regular@example.com",
            role="employee",
            is_active=True,
        )

        # Create test employees with salaries
        self.test_employees = []
        for i in range(5):
            user = User.objects.create_user(
                username=f"testuser{i}",
                email=f"test{i}@example.com",
                password="testpass123",
            )

            employee = Employee.objects.create(
                user=user,
                first_name=f"Test{i}",
                last_name="Employee",
                email=f"test{i}@example.com",
                employment_type="full_time",
                is_active=True,
            )

            Salary.objects.create(
                employee=employee,
                calculation_type="hourly",
                hourly_rate=Decimal("50.00"),
                is_active=True,
            )

            self.test_employees.append(employee)

        # Create work logs
        tz = pytz.timezone("Asia/Jerusalem")
        for employee in self.test_employees:
            WorkLog.objects.create(
                employee=employee,
                check_in=datetime(2025, 10, 9, 9, 0, 0, tzinfo=tz),
                check_out=datetime(2025, 10, 9, 17, 0, 0, tzinfo=tz),
            )

        # Create API client
        self.client = APIClient()

    def test_bulk_calculate_requires_authentication(self):
        """Test that bulk calculate endpoint requires authentication."""
        url = reverse("bulk-calculate-payroll")

        response = self.client.post(url, {"year": 2025, "month": 10}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_bulk_calculate_requires_admin_or_accountant_role(self):
        """Test that bulk calculate requires admin or accountant role."""
        url = reverse("bulk-calculate-payroll")

        # Try with regular employee
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.post(url, {"year": 2025, "month": 10}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Permission denied", response.data.get("error", ""))

    def test_bulk_calculate_admin_access(self):
        """Test that admin can access bulk calculate endpoint."""
        url = reverse("bulk-calculate-payroll")

        self.client.force_authenticate(user=self.admin_user)

        with patch(
            "payroll.services.payroll_service.PayrollService.calculate_bulk_optimized"
        ) as mock_calc:
            # Mock successful calculation
            mock_calc.return_value = {
                self.test_employees[0].id: {
                    "total_salary": Decimal("400.00"),
                    "total_hours": Decimal("8.0"),
                    "regular_hours": Decimal("8.0"),
                    "overtime_hours": Decimal("0.0"),
                    "holiday_hours": Decimal("0.0"),
                    "shabbat_hours": Decimal("0.0"),
                    "worked_days": 1,
                    "metadata": {"status": "calculated"},
                }
            }

            response = self.client.post(
                url,
                {
                    "year": 2025,
                    "month": 10,
                    "employee_ids": [self.test_employees[0].id],
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIn("summary", response.data)

    def test_bulk_calculate_accountant_access(self):
        """Test that accountant can access bulk calculate endpoint."""
        url = reverse("bulk-calculate-payroll")

        self.client.force_authenticate(user=self.accountant_user)

        with patch(
            "payroll.services.payroll_service.PayrollService.calculate_bulk_optimized"
        ) as mock_calc:
            mock_calc.return_value = {}

            response = self.client.post(url, {"year": 2025, "month": 10}, format="json")

            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_bulk_calculate_missing_required_fields(self):
        """Test validation for missing required fields."""
        url = reverse("bulk-calculate-payroll")

        self.client.force_authenticate(user=self.admin_user)

        # Missing year
        response = self.client.post(url, {"month": 10}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("year", response.data.get("error", "").lower())

        # Missing month
        response = self.client.post(url, {"year": 2025}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("month", response.data.get("error", "").lower())

    def test_bulk_calculate_invalid_month(self):
        """Test validation for invalid month values."""
        url = reverse("bulk-calculate-payroll")

        self.client.force_authenticate(user=self.admin_user)

        # Month too low
        response = self.client.post(url, {"year": 2025, "month": 0}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Month too high
        response = self.client.post(url, {"year": 2025, "month": 13}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bulk_calculate_invalid_employee_ids_format(self):
        """Test validation for invalid employee_ids format."""
        url = reverse("bulk-calculate-payroll")

        self.client.force_authenticate(user=self.admin_user)

        # Not a list
        response = self.client.post(
            url,
            {"year": 2025, "month": 10, "employee_ids": "not_a_list"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("must be a list", response.data.get("error", ""))

    def test_bulk_calculate_invalid_employee_ids(self):
        """Test validation for non-existent employee IDs."""
        url = reverse("bulk-calculate-payroll")

        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            url,
            {
                "year": 2025,
                "month": 10,
                "employee_ids": [99999, 99998],  # Non-existent IDs
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(
            "Invalid or inactive employee IDs", response.data.get("error", "")
        )

    def test_bulk_calculate_with_specific_employees(self):
        """Test bulk calculation for specific employees."""
        url = reverse("bulk-calculate-payroll")

        self.client.force_authenticate(user=self.admin_user)

        employee_ids = [emp.id for emp in self.test_employees[:3]]

        with patch(
            "payroll.services.payroll_service.PayrollService.calculate_bulk_optimized"
        ) as mock_calc:
            mock_results = {}
            for emp_id in employee_ids:
                mock_results[emp_id] = {
                    "total_salary": Decimal("400.00"),
                    "total_hours": Decimal("8.0"),
                    "regular_hours": Decimal("8.0"),
                    "overtime_hours": Decimal("0.0"),
                    "holiday_hours": Decimal("0.0"),
                    "shabbat_hours": Decimal("0.0"),
                    "worked_days": 1,
                    "metadata": {"status": "calculated"},
                }

            mock_calc.return_value = mock_results

            response = self.client.post(
                url,
                {"year": 2025, "month": 10, "employee_ids": employee_ids},
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["summary"]["total_employees"], 3)
            self.assertEqual(len(response.data["results"]), 3)

    def test_bulk_calculate_all_active_employees(self):
        """Test bulk calculation for all active employees."""
        url = reverse("bulk-calculate-payroll")

        self.client.force_authenticate(user=self.admin_user)

        with patch(
            "payroll.services.payroll_service.PayrollService.calculate_bulk_optimized"
        ) as mock_calc:
            mock_calc.return_value = {}

            response = self.client.post(
                url,
                {
                    "year": 2025,
                    "month": 10,
                    # No employee_ids - should process all active employees
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)

            # Should include test employees
            self.assertGreaterEqual(response.data["summary"]["total_employees"], 5)

    def test_bulk_calculate_with_strategy(self):
        """Test bulk calculation with specific strategy."""
        url = reverse("bulk-calculate-payroll")

        self.client.force_authenticate(user=self.admin_user)

        with patch(
            "payroll.services.payroll_service.PayrollService.calculate_bulk_optimized"
        ) as mock_calc:
            mock_calc.return_value = {}

            response = self.client.post(
                url,
                {"year": 2025, "month": 10, "strategy": "critical_points"},
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)

            # Verify strategy was passed correctly
            call_kwargs = mock_calc.call_args[1]
            self.assertEqual(call_kwargs["strategy"].value, "critical_points")

    def test_bulk_calculate_invalid_strategy(self):
        """Test validation for invalid strategy."""
        url = reverse("bulk-calculate-payroll")

        self.client.force_authenticate(user=self.admin_user)

        response = self.client.post(
            url,
            {"year": 2025, "month": 10, "strategy": "invalid_strategy"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid strategy", response.data.get("error", ""))

    def test_bulk_calculate_with_flags(self):
        """Test bulk calculation with optional flags."""
        url = reverse("bulk-calculate-payroll")

        self.client.force_authenticate(user=self.admin_user)

        with patch(
            "payroll.services.payroll_service.PayrollService.calculate_bulk_optimized"
        ) as mock_calc:
            mock_calc.return_value = {}

            response = self.client.post(
                url,
                {
                    "year": 2025,
                    "month": 10,
                    "use_parallel": False,
                    "use_cache": False,
                    "save_to_db": False,
                },
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)

            # Verify flags were passed
            call_kwargs = mock_calc.call_args[1]
            self.assertFalse(call_kwargs["use_parallel"])
            self.assertFalse(call_kwargs["use_cache"])
            self.assertFalse(call_kwargs["save_to_db"])

    def test_bulk_calculate_response_structure(self):
        """Test that response has correct structure."""
        url = reverse("bulk-calculate-payroll")

        self.client.force_authenticate(user=self.admin_user)

        employee_id = self.test_employees[0].id

        with patch(
            "payroll.services.payroll_service.PayrollService.calculate_bulk_optimized"
        ) as mock_calc:
            mock_calc.return_value = {
                employee_id: {
                    "total_salary": Decimal("400.00"),
                    "total_hours": Decimal("8.0"),
                    "regular_hours": Decimal("8.0"),
                    "overtime_hours": Decimal("0.0"),
                    "holiday_hours": Decimal("0.0"),
                    "shabbat_hours": Decimal("0.0"),
                    "worked_days": 1,
                    "metadata": {"status": "calculated"},
                }
            }

            response = self.client.post(
                url,
                {"year": 2025, "month": 10, "employee_ids": [employee_id]},
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)

            # Verify response structure
            self.assertIn("status", response.data)
            self.assertEqual(response.data["status"], "success")

            self.assertIn("summary", response.data)
            summary = response.data["summary"]
            self.assertIn("total_employees", summary)
            self.assertIn("successful", summary)
            self.assertIn("failed", summary)
            self.assertIn("year", summary)
            self.assertIn("month", summary)

            self.assertIn("results", response.data)
            results = response.data["results"]
            self.assertIn(str(employee_id), results)

            # Verify result fields
            result = results[str(employee_id)]
            self.assertIn("total_salary", result)
            self.assertIn("total_hours", result)
            self.assertIn("worked_days", result)

    def test_bulk_calculate_with_errors(self):
        """Test bulk calculation when some employees fail."""
        url = reverse("bulk-calculate-payroll")

        self.client.force_authenticate(user=self.admin_user)

        employee_ids = [emp.id for emp in self.test_employees[:2]]

        with patch(
            "payroll.services.payroll_service.PayrollService.calculate_bulk_optimized"
        ) as mock_calc:
            mock_calc.return_value = {
                employee_ids[0]: {
                    "total_salary": Decimal("400.00"),
                    "total_hours": Decimal("8.0"),
                    "regular_hours": Decimal("8.0"),
                    "overtime_hours": Decimal("0.0"),
                    "holiday_hours": Decimal("0.0"),
                    "shabbat_hours": Decimal("0.0"),
                    "worked_days": 1,
                    "metadata": {"status": "calculated"},
                },
                employee_ids[1]: {
                    "total_salary": Decimal("0.0"),
                    "total_hours": Decimal("0.0"),
                    "regular_hours": Decimal("0.0"),
                    "overtime_hours": Decimal("0.0"),
                    "holiday_hours": Decimal("0.0"),
                    "shabbat_hours": Decimal("0.0"),
                    "worked_days": 0,
                    "metadata": {"status": "failed", "error": "Calculation error"},
                },
            }

            response = self.client.post(
                url,
                {"year": 2025, "month": 10, "employee_ids": employee_ids},
                format="json",
            )

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["summary"]["successful"], 1)
            self.assertEqual(response.data["summary"]["failed"], 1)

            # Verify errors are included
            self.assertIn("errors", response.data)
            self.assertEqual(len(response.data["errors"]), 1)

    def test_bulk_calculation_status_endpoint(self):
        """Test bulk calculation status endpoint."""
        url = reverse("bulk-calculation-status")

        self.client.force_authenticate(user=self.admin_user)

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify response structure
        self.assertIn("service_available", response.data)
        self.assertIn("configuration", response.data)
        self.assertIn("recommendations", response.data)

        # Verify recommendations
        recommendations = response.data["recommendations"]
        self.assertIn("min_batch_size", recommendations)
        self.assertIn("optimal_batch_size", recommendations)
        self.assertIn("max_batch_size", recommendations)

    def test_bulk_status_requires_authentication(self):
        """Test that status endpoint requires authentication."""
        url = reverse("bulk-calculation-status")

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_bulk_status_requires_admin_or_accountant(self):
        """Test that status endpoint requires admin or accountant role."""
        url = reverse("bulk-calculation-status")

        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_bulk_calculate_exception_handling(self):
        """Test that exceptions are handled gracefully."""
        url = reverse("bulk-calculate-payroll")

        self.client.force_authenticate(user=self.admin_user)

        with patch(
            "payroll.services.payroll_service.PayrollService.calculate_bulk_optimized"
        ) as mock_calc:
            mock_calc.side_effect = Exception("Service error")

            response = self.client.post(url, {"year": 2025, "month": 10}, format="json")

            self.assertEqual(
                response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            self.assertEqual(response.data["status"], "error")
            self.assertIn("error", response.data)
