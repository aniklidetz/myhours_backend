"""
Integration tests for Payroll API with authentication.

Tests the full authentication flow and payroll endpoints access.
"""

from datetime import date, datetime
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from users.models import Employee


class PayrollAPIAuthenticationTest(APITestCase):
    """Test Payroll API endpoints with proper authentication"""

    def setUp(self):
        """Set up test data"""
        # Create admin user
        self.admin_user = User.objects.create_superuser(
            username="admin", email="admin@test.com", password="testpass123"
        )

        # Create Employee profile for admin with admin role
        self.admin_employee = Employee.objects.create(
            user=self.admin_user,
            first_name="Admin",
            last_name="User",
            email="admin@test.com",
            employment_type="full_time",
            role="admin",  # This is crucial for payroll access
            is_active=True,
        )

        # Create regular user
        self.regular_user = User.objects.create_user(
            username="regular", email="regular@test.com", password="testpass123"
        )

        # Create test employees
        self.monthly_employee = Employee.objects.create(
            user=self.regular_user,
            first_name="Test",
            last_name="Monthly",
            email="monthly@test.com",
            employment_type="full_time",
            monthly_salary=Decimal(
                "10000.00"
            ),  # Changed from base_salary to monthly_salary
            hourly_rate=None,  # Testing null hourly_rate case
        )

        self.hourly_employee = Employee.objects.create(
            first_name="Test",
            last_name="Hourly",
            email="hourly@test.com",
            employment_type="hourly",
            hourly_rate=Decimal("50.00"),
        )

        # Import and create Salary records for proper calculation_type
        from payroll.models import Salary

        # Create monthly salary record
        Salary.objects.create(
            employee=self.monthly_employee,
            base_salary=Decimal("10000.00"),
            calculation_type="monthly",
            currency="ILS",
        )

        # Create hourly salary record
        Salary.objects.create(
            employee=self.hourly_employee,
            hourly_rate=Decimal("50.00"),
            calculation_type="hourly",
            currency="ILS",
        )

    def test_unauthenticated_access_denied(self):
        """Test that unauthenticated requests are denied"""
        url = reverse("current-earnings")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_can_access_all_employees(self):
        """Test admin can access payroll data for all employees"""
        self.client.force_authenticate(user=self.admin_user)

        # Test accessing monthly employee data
        url = reverse("current-earnings")
        response = self.client.get(
            url,
            {
                "employee_id": self.monthly_employee.id,
                "year": datetime.now().year,
                "month": datetime.now().month,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("total_salary", response.data)
        self.assertIn("calculation_type", response.data)
        self.assertEqual(response.data["calculation_type"], "monthly")

    def test_regular_user_can_access_own_data(self):
        """Test regular user can only access their own payroll data"""
        self.client.force_authenticate(user=self.regular_user)

        # Test accessing own data (without employee_id - this allows access to own data)
        url = reverse("current-earnings")
        response = self.client.get(
            url,
            {
                # No employee_id - user accesses their own data
                "year": datetime.now().year,
                "month": datetime.now().month,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test accessing other employee's data - should be denied
        response = self.client.get(
            url,
            {
                "employee_id": self.hourly_employee.id,
                "year": datetime.now().year,
                "month": datetime.now().month,
            },
        )

        self.assertIn(
            response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]
        )

    def test_monthly_employee_with_null_hourly_rate(self):
        """Test that monthly employees with null hourly_rate don't cause errors"""
        self.client.force_authenticate(user=self.admin_user)

        # Ensure monthly employee has null hourly_rate
        self.assertIsNone(self.monthly_employee.hourly_rate)

        url = reverse("current-earnings")
        response = self.client.get(
            url,
            {
                "employee_id": self.monthly_employee.id,
                "year": datetime.now().year,
                "month": datetime.now().month,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should not have division by zero or null reference errors
        self.assertIsInstance(response.data.get("total_salary"), (int, float, Decimal))

    def test_csrf_token_flow(self):
        """Test session-based authentication works (simplified)"""
        # Use Django's built-in test client with force_login
        # to simulate session authentication
        from django.test import Client

        client = Client()
        client.force_login(self.admin_user)

        # Test API access with session auth
        api_url = reverse("current-earnings")
        response = client.get(
            api_url,
            {
                "year": datetime.now().year,
                "month": datetime.now().month,
            },
        )

        # Should work with session auth
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("total_salary", response.json())


class PayrollAPIErrorHandlingTest(TestCase):
    """Test error handling in Payroll API"""

    def setUp(self):
        """Set up test data"""
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username="admin", email="admin@test.com", password="testpass123"
        )

        # Create Employee profile for admin with admin role (needed for payroll access)
        self.admin_employee = Employee.objects.create(
            user=self.admin_user,
            first_name="Admin",
            last_name="User",
            email="admin@test.com",
            employment_type="full_time",
            role="admin",
            is_active=True,
        )

        self.client.force_login(self.admin_user)

    def test_invalid_employee_id(self):
        """Test handling of invalid employee ID"""
        url = reverse("current-earnings")
        response = self.client.get(
            url,
            {
                "employee_id": 99999,  # Non-existent ID
                "year": datetime.now().year,
                "month": datetime.now().month,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_required_parameters(self):
        """Test handling of missing parameters - API should use defaults"""
        url = reverse("current-earnings")

        # Missing year - API should use current year
        response = self.client.get(url, {"month": 7})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("total_salary", response.json())

        # Missing month - API should use current month
        response = self.client.get(url, {"year": 2025})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("total_salary", response.json())
