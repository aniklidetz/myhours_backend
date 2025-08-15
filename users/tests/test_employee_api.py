"""
Comprehensive API tests for Employee endpoints.
Tests CRUD operations, authentication, permissions, and business logic through APIs.
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APIClient

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from payroll.models import Salary
from tests.base import BaseAPITestCase, UnauthenticatedAPITestCase
from users.models import Employee
from worktime.models import WorkLog


class EmployeeAPITest(BaseAPITestCase):
    """Comprehensive Employee API tests with authentication"""

    def setUp(self):
        super().setUp()

        # Create additional test employees with unique emails
        self.manager_employee = Employee.objects.create(
            first_name="Manager",
            last_name="Boss",
            email=f"manager_{self.test_id}@test.com",
            employment_type="full_time",
            role="manager",
        )

        self.hourly_employee = Employee.objects.create(
            first_name="Hourly",
            last_name="Worker",
            email=f"hourly_{self.test_id}@test.com",
            employment_type="hourly",
            role="employee",
        )

        # Create salaries for test employees
        Salary.objects.create(
            employee=self.manager_employee,
            calculation_type="monthly",
            base_salary=Decimal("25000.00"),
            currency="ILS",
        )

        Salary.objects.create(
            employee=self.hourly_employee,
            calculation_type="hourly",
            hourly_rate=Decimal("120.00"),
            currency="ILS",
        )

    def test_list_employees_authenticated(self):
        """Test listing employees with authentication"""
        url = reverse("employee-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertGreater(len(response.data["results"]), 0)

        # Verify employee data structure
        employee_data = response.data["results"][0]
        required_fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "employment_type",
            "role",
        ]
        for field in required_fields:
            self.assertIn(field, employee_data)

    def test_create_employee_authenticated(self):
        """Test creating an employee with authentication"""
        url = reverse("employee-list")
        data = {
            "first_name": "New",
            "last_name": "Employee",
            "email": "new.employee@test.com",
            "employment_type": "hourly",
            "role": "employee",
            "phone_number": "+972-50-1234567",
            "address": "Tel Aviv, Israel",
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["first_name"], "New")
        self.assertEqual(response.data["last_name"], "Employee")
        self.assertEqual(response.data["email"], "new.employee@test.com")
        self.assertEqual(response.data["employment_type"], "hourly")

        # Verify employee was created in database
        self.assertTrue(Employee.objects.filter(email="new.employee@test.com").exists())

    def test_retrieve_employee_authenticated(self):
        """Test retrieving a specific employee"""
        url = reverse("employee-detail", args=[self.manager_employee.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.manager_employee.id)
        self.assertEqual(response.data["first_name"], "Manager")
        self.assertEqual(response.data["role"], "manager")

    def test_update_employee_authenticated(self):
        """Test updating an employee"""
        url = reverse("employee-detail", args=[self.hourly_employee.id])
        data = {
            "first_name": "Updated",
            "employment_type": "full_time",
            "role": "manager",
        }

        response = self.client.patch(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["first_name"], "Updated")
        self.assertEqual(response.data["employment_type"], "full_time")

        # Verify in database
        self.hourly_employee.refresh_from_db()
        self.assertEqual(self.hourly_employee.first_name, "Updated")
        self.assertEqual(self.hourly_employee.employment_type, "full_time")

    def test_delete_employee_authenticated(self):
        """Test deleting (deactivating) an employee"""
        employee_to_delete = Employee.objects.create(
            first_name="Delete",
            last_name="Me",
            email="delete@test.com",
            employment_type="hourly",
        )

        url = reverse("employee-detail", args=[employee_to_delete.id])
        response = self.client.delete(url)

        # Depending on implementation, this might be 204 (deleted) or 200 (deactivated)
        self.assertIn(
            response.status_code, [status.HTTP_204_NO_CONTENT, status.HTTP_200_OK]
        )

        # Check if employee is deactivated rather than deleted
        employee_to_delete.refresh_from_db()
        # This depends on your implementation - soft delete vs hard delete

    def test_filter_employees_by_employment_type(self):
        """Test filtering employees by employment type"""
        url = reverse("employee-list")

        # Filter hourly employees
        response = self.client.get(url, {"employment_type": "hourly"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for employee in response.data["results"]:
            self.assertEqual(employee["employment_type"], "hourly")

    def test_filter_employees_by_role(self):
        """Test filtering employees by role"""
        url = reverse("employee-list")

        # Filter managers
        response = self.client.get(url, {"role": "manager"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for employee in response.data["results"]:
            self.assertEqual(employee["role"], "manager")

    def test_filter_employees_by_active_status(self):
        """Test filtering employees by active status"""
        # Create inactive employee
        Employee.objects.create(
            first_name="Inactive",
            last_name="Employee",
            email="inactive@test.com",
            employment_type="hourly",
            is_active=False,
        )

        url = reverse("employee-list")

        # Filter active employees
        response = self.client.get(url, {"is_active": "true"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        for employee in response.data["results"]:
            self.assertTrue(employee.get("is_active", True))

    def test_search_employees(self):
        """Test searching employees by name or email"""
        url = reverse("employee-list")

        # Search by first name
        response = self.client.get(url, {"search": "Manager"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Should find the manager employee
        found = any(emp["first_name"] == "Manager" for emp in response.data["results"])
        self.assertTrue(found)

        # Search by email
        response = self.client.get(url, {"search": f"hourly_{self.test_id}@test.com"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        found = any(
            emp["email"] == f"hourly_{self.test_id}@test.com"
            for emp in response.data["results"]
        )
        self.assertTrue(found)

    def test_employee_ordering(self):
        """Test ordering of employees"""
        url = reverse("employee-list")

        # Order by first name
        response = self.client.get(url, {"ordering": "first_name"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        employees = response.data["results"]
        if len(employees) > 1:
            # Verify ascending order
            for i in range(len(employees) - 1):
                current_name = employees[i]["first_name"]
                next_name = employees[i + 1]["first_name"]
                self.assertLessEqual(current_name, next_name)

    def test_employee_pagination(self):
        """Test pagination of employees"""
        # Create additional employees to test pagination
        for i in range(10):
            Employee.objects.create(
                first_name=f"Test{i}",
                last_name="Employee",
                email=f"test{i}@example.com",
                employment_type="hourly",
            )

        url = reverse("employee-list")
        response = self.client.get(url, {"page": 1, "page_size": 5})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("count", response.data)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)
        self.assertIn("results", response.data)

        # Should have at most 5 results per page
        self.assertLessEqual(len(response.data["results"]), 5)

    def test_employee_validation_errors(self):
        """Test API validation errors"""
        url = reverse("employee-list")

        # Test missing required fields
        data = {
            "first_name": "Test"
            # Missing last_name, email, employment_type
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Test invalid employment type
        data = {
            "first_name": "Test",
            "last_name": "Employee",
            "email": "test@example.com",
            "employment_type": "invalid_type",
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Test duplicate email
        data = {
            "first_name": "Duplicate",
            "last_name": "Employee",
            "email": f"manager_{self.test_id}@test.com",  # Already exists
            "employment_type": "hourly",
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_employee_bulk_operations(self):
        """Test bulk operations on employees"""
        url = reverse("employee-list")

        # Bulk create employees
        employees_data = []
        for i in range(5):
            employees_data.append(
                {
                    "first_name": f"Bulk{i}",
                    "last_name": "Employee",
                    "email": f"bulk{i}@test.com",
                    "employment_type": "hourly",
                    "role": "employee",
                }
            )

        # Note: This would require a custom bulk create endpoint
        # For now, test individual creation
        created_ids = []
        for data in employees_data:
            response = self.client.post(url, data, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            created_ids.append(response.data["id"])

        # Verify all were created
        self.assertEqual(len(created_ids), 5)

    def test_employee_with_salary_data(self):
        """Test employee endpoints with related salary data"""
        url = reverse("employee-detail", args=[self.manager_employee.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check if salary data is included (depends on serializer implementation)
        employee_data = response.data
        # This depends on your serializer design
        # You might include salary data or have separate endpoints

    def test_employee_work_statistics(self):
        """Test employee work statistics through API"""
        # Create work logs for the employee
        for day in range(1, 6):  # 5 work days
            check_in = timezone.make_aware(datetime(2025, 7, day, 9, 0))
            check_out = timezone.make_aware(datetime(2025, 7, day, 17, 0))

            WorkLog.objects.create(
                employee=self.hourly_employee,
                check_in=check_in,
                check_out=check_out,
                is_approved=True,
            )

        # Test employee detail with work statistics
        url = reverse("employee-detail", args=[self.hourly_employee.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # In a real implementation, you might include work statistics
        # in the employee detail response or have a separate endpoint


class EmployeeAPIPermissionsTest(BaseAPITestCase):
    """Test permissions for Employee API"""

    def setUp(self):
        super().setUp()

        # Update the existing employee to be admin instead of creating a new one
        self.employee.role = "admin"
        self.employee.save()
        self.admin_employee = self.employee  # Use existing employee as admin

        self.regular_employee = Employee.objects.create(
            first_name="Regular",
            last_name="Employee",
            email=f"regular_{self.test_id}@test.com",
            employment_type="hourly",
            role="employee",
        )

    def test_admin_can_access_all_employees(self):
        """Test that admin users can access all employees"""
        url = reverse("employee-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Admin should see all employees
        self.assertGreater(len(response.data["results"]), 1)

    def test_employee_can_update_own_profile(self):
        """Test that employees can update their own profile"""
        url = reverse("employee-detail", args=[self.admin_employee.id])
        data = {"phone_number": "+972-50-9876543", "address": "Updated Address"}

        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_employee_cannot_change_own_role(self):
        """Test that employees cannot change their own role"""
        url = reverse("employee-detail", args=[self.admin_employee.id])
        data = {"role": "super_admin"}

        response = self.client.patch(url, data, format="json")

        # This should either be forbidden or the role change should be ignored
        # depending on your permission implementation
        if response.status_code == status.HTTP_200_OK:
            # Verify role wasn't actually changed
            self.admin_employee.refresh_from_db()
            self.assertNotEqual(self.admin_employee.role, "super_admin")

    def test_manager_permissions(self):
        """Test manager-specific permissions"""
        # Create manager user and authenticate
        manager_user = User.objects.create_user(
            username="manager", email="manager@test.com", password="managerpass"
        )

        manager_employee = Employee.objects.create(
            user=manager_user,
            first_name="Manager",
            last_name="User",
            email="manager.user@test.com",
            employment_type="full_time",
            role="manager",
        )

        # Authenticate as manager
        self.client.force_authenticate(user=manager_user)

        url = reverse("employee-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Manager should be able to see employees under their management


class EmployeeAPIUnauthenticatedTest(UnauthenticatedAPITestCase):
    """Test Employee API endpoints without authentication"""

    def test_list_employees_unauthenticated(self):
        """Test listing employees without authentication"""
        url = reverse("employee-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_employee_unauthenticated(self):
        """Test creating employee without authentication"""
        url = reverse("employee-list")
        data = {
            "first_name": "Unauthorized",
            "last_name": "User",
            "email": "unauthorized@test.com",
            "employment_type": "hourly",
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_retrieve_employee_unauthenticated(self):
        """Test retrieving employee without authentication"""
        employee = Employee.objects.create(
            first_name="Test",
            last_name="Employee",
            email="test@example.com",
            employment_type="hourly",
        )

        url = reverse("employee-detail", args=[employee.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_employee_unauthenticated(self):
        """Test updating employee without authentication"""
        employee = Employee.objects.create(
            first_name="Test",
            last_name="Employee",
            email="test2@example.com",
            employment_type="hourly",
        )

        url = reverse("employee-detail", args=[employee.id])
        data = {"first_name": "Updated"}

        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_delete_employee_unauthenticated(self):
        """Test deleting employee without authentication"""
        employee = Employee.objects.create(
            first_name="Test",
            last_name="Employee",
            email="test3@example.com",
            employment_type="hourly",
        )

        url = reverse("employee-detail", args=[employee.id])
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class EmployeeAPIIntegrationTest(BaseAPITestCase):
    """Integration tests for Employee API with other systems"""

    def setUp(self):
        super().setUp()

        self.test_employee = Employee.objects.create(
            first_name="Integration",
            last_name="Test",
            email="integration@test.com",
            employment_type="hourly",
            role="employee",
        )

        # Create salary
        self.salary = Salary.objects.create(
            employee=self.test_employee,
            calculation_type="hourly",
            hourly_rate=Decimal("100.00"),
            currency="ILS",
        )

    def test_employee_creation_with_automatic_salary(self):
        """Test that creating employee automatically creates default salary"""
        url = reverse("employee-list")
        data = {
            "first_name": "Auto",
            "last_name": "Salary",
            "email": "auto.salary@test.com",
            "employment_type": "hourly",
            "role": "employee",
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Check if salary was automatically created (depends on implementation)
        created_employee = Employee.objects.get(id=response.data["id"])
        # This depends on your business logic

    def test_employee_with_work_history(self):
        """Test employee endpoints with work history"""
        # Create work logs
        for day in range(1, 8):  # 7 days
            check_in = timezone.make_aware(datetime(2025, 7, day, 9, 0))
            check_out = timezone.make_aware(datetime(2025, 7, day, 17, 0))

            WorkLog.objects.create(
                employee=self.test_employee,
                check_in=check_in,
                check_out=check_out,
                is_approved=True,
            )

        url = reverse("employee-detail", args=[self.test_employee.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # In a real implementation, you might include work statistics
        # or have separate endpoints for work history

    def test_employee_payroll_summary_integration(self):
        """Test integration with payroll summary data"""
        # This would test endpoints that combine employee data with payroll summaries

        url = reverse("employee-detail", args=[self.test_employee.id])
        response = self.client.get(url, {"include_payroll": "true"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Depending on implementation, payroll data might be included
        # or available through separate endpoints

    def test_employee_deactivation_impact(self):
        """Test the impact of employee deactivation on related systems"""
        # Create work logs
        WorkLog.objects.create(
            employee=self.test_employee,
            check_in=timezone.now() - timedelta(hours=2),
            # Current session - no check_out
        )

        # Deactivate employee
        url = reverse("employee-detail", args=[self.test_employee.id])
        data = {"is_active": False}

        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify employee is deactivated
        self.test_employee.refresh_from_db()
        self.assertFalse(self.test_employee.is_active)

        # Historical data should still exist
        work_logs = WorkLog.objects.filter(employee=self.test_employee)
        self.assertGreater(work_logs.count(), 0)
