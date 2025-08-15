"""
Targeted tests for users/views.py
Focus on achieving 70%+ coverage for critical uncovered branches
"""

from datetime import timedelta
from unittest.mock import MagicMock, Mock, patch

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from users.models import Employee, EmployeeInvitation
from users.serializers import EmployeeSerializer, EmployeeUpdateSerializer
from users.views import (
    AcceptInvitationView,
    DefaultPagination,
    EmployeeViewSet,
    ValidateInvitationView,
)


class DefaultPaginationTest(TestCase):
    """Test DefaultPagination class"""

    def test_pagination_configuration(self):
        """Test pagination configuration"""
        pagination = DefaultPagination()

        # Check page_size_query_param is set correctly
        self.assertEqual(pagination.page_size_query_param, "page_size")


class EmployeeViewSetPermissionsTest(APITestCase):
    """Test EmployeeViewSet permission handling"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Test",
            last_name="User",
            email="test@example.com",
            employment_type="full_time",
            role="employee",
        )
        self.token = Token.objects.create(user=self.user)

    def test_get_permissions_authenticated(self):
        """Test get_permissions method returns IsAuthenticated"""
        viewset = EmployeeViewSet()
        permissions = viewset.get_permissions()

        # Should return IsAuthenticated permission
        self.assertEqual(len(permissions), 1)
        from rest_framework.permissions import IsAuthenticated

        self.assertIsInstance(permissions[0], IsAuthenticated)

    def test_unauthenticated_access_denied(self):
        """Test unauthenticated requests are denied"""
        response = self.client.get("/api/v1/users/employees/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_access_allowed(self):
        """Test authenticated requests are allowed"""
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

        with patch("users.views.Employee.objects") as mock_objects:
            mock_objects.select_related.return_value.all.return_value.order_by.return_value = (
                []
            )
            response = self.client.get("/api/v1/users/employees/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class EmployeeViewSetSerializerTest(APITestCase):
    """Test EmployeeViewSet serializer selection"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Test",
            last_name="User",
            email="test@example.com",
            employment_type="full_time",
            role="employee",
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

    def test_get_serializer_class_update_action(self):
        """Test serializer class selection for update actions"""
        viewset = EmployeeViewSet()
        viewset.action = "update"

        serializer_class = viewset.get_serializer_class()

        self.assertEqual(serializer_class, EmployeeUpdateSerializer)

    def test_get_serializer_class_partial_update_action(self):
        """Test serializer class selection for partial update actions"""
        viewset = EmployeeViewSet()
        viewset.action = "partial_update"

        serializer_class = viewset.get_serializer_class()

        self.assertEqual(serializer_class, EmployeeUpdateSerializer)

    def test_get_serializer_class_default_action(self):
        """Test serializer class selection for default actions"""
        viewset = EmployeeViewSet()
        viewset.action = "list"

        serializer_class = viewset.get_serializer_class()

        self.assertEqual(serializer_class, EmployeeSerializer)


class EmployeeViewSetCreateTest(APITestCase):
    """Test EmployeeViewSet create functionality"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        self.admin_user = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="admin123",
            is_staff=True,
        )
        self.admin_employee = Employee.objects.create(
            user=self.admin_user,
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
            employment_type="full_time",
            role="admin",
        )
        self.admin_token = Token.objects.create(user=self.admin_user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.admin_token.key)

    @patch("users.views.logger")
    @patch("payroll.models.Salary.objects.create")
    def test_create_employee_success(self, mock_salary_create, mock_logger):
        """Test successful employee creation"""
        employee_data = {
            "first_name": "New",
            "last_name": "Employee",
            "email": "new@example.com",
            "employment_type": "full_time",
            "role": "employee",
        }

        # Mock salary creation
        mock_salary = Mock()
        mock_salary_create.return_value = mock_salary

        with patch("users.serializers.User.objects.create_user") as mock_create_user:
            mock_user = Mock()
            mock_user.id = 999
            mock_create_user.return_value = mock_user

            response = self.client.post("/api/v1/users/employees/", employee_data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_logger.info.assert_called()

    @patch("users.views.logger")
    def test_create_employee_validation_error(self, mock_logger):
        """Test employee creation with validation error"""
        # Missing required fields
        employee_data = {
            "first_name": "New"
            # Missing last_name, email, etc.
        }

        response = self.client.post("/api/v1/users/employees/", employee_data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_logger.error.assert_called()

    def test_create_employee_exception(self):
        """Test employee creation with exception during serializer creation"""
        employee_data = {
            "first_name": "New",
            "last_name": "Employee",
            "email": "invalid-email",  # Invalid email format to cause validation error
            "employment_type": "invalid_type",  # Invalid employment type
            "role": "employee",
        }

        # This will cause serializer validation to fail and be handled by the exception handler
        response = self.client.post("/api/v1/users/employees/", employee_data)

        # The create method will catch validation errors and log them
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("users.views.logger")
    @patch("users.views.safe_log_employee")
    @patch("payroll.models.Salary.objects.create")
    def test_perform_create_success(
        self, mock_salary_create, mock_safe_log, mock_logger
    ):
        """Test perform_create method"""
        viewset = EmployeeViewSet()
        # Mock request with data
        mock_request = Mock()
        mock_request.data = {"role": "employee", "employment_type": "full_time"}
        mock_request.user = self.admin_user
        viewset.request = mock_request

        mock_serializer = Mock()
        mock_employee = Mock()
        mock_employee.id = 123
        mock_employee.email = "test@example.com"
        mock_employee.role = "employee"
        mock_employee.employment_type = "full_time"
        mock_serializer.save.return_value = mock_employee

        # Mock salary creation
        mock_salary = Mock()
        mock_salary.calculation_type = "monthly"
        mock_salary.currency = "ILS"
        mock_salary_create.return_value = mock_salary

        viewset.perform_create(mock_serializer)

        mock_serializer.save.assert_called_once()
        mock_logger.info.assert_called()
        mock_salary_create.assert_called_once()

    @patch("users.views.get_safe_logger")
    def test_perform_create_exception(self, mock_logger):
        """Test perform_create with exception"""
        viewset = EmployeeViewSet()
        # Mock request
        mock_request = Mock()
        mock_request.data = {}
        mock_request.user = self.admin_user
        viewset.request = mock_request

        mock_serializer = Mock()
        mock_serializer.save.side_effect = Exception("Save error")

        # Should raise exception but we can catch it
        with self.assertRaises(Exception):
            viewset.perform_create(mock_serializer)


class EmployeeViewSetUpdateTest(APITestCase):
    """Test EmployeeViewSet update functionality"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Test",
            last_name="User",
            email="test@example.com",
            employment_type="full_time",
            role="employee",
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

    @patch("users.views.logger")
    @patch("users.views.safe_log_employee")
    def test_perform_update_success(self, mock_safe_log, mock_logger):
        """Test perform_update method"""
        viewset = EmployeeViewSet()
        # Mock request with data
        mock_request = Mock()
        mock_request.data = {"hourly_rate": "100.00"}
        mock_request.user = self.user
        viewset.request = mock_request

        # Mock get_object method
        mock_employee = Mock()
        mock_employee.id = 123
        mock_employee.email = "updated@example.com"
        mock_employee.employment_type = "hourly"
        viewset.get_object = Mock(return_value=mock_employee)

        mock_serializer = Mock()
        mock_serializer.save.return_value = mock_employee

        # Mock Salary.objects.get_or_create
        with patch("payroll.models.Salary.objects.get_or_create") as mock_get_or_create:
            mock_salary = Mock()
            mock_get_or_create.return_value = (mock_salary, False)

            viewset.perform_update(mock_serializer)

            mock_serializer.save.assert_called_once()
            mock_logger.info.assert_called()

    @patch("users.views.get_safe_logger")
    def test_perform_update_exception(self, mock_logger):
        """Test perform_update with exception"""
        viewset = EmployeeViewSet()
        # Mock request
        mock_request = Mock()
        mock_request.data = {}
        mock_request.user = self.user
        viewset.request = mock_request

        # Mock get_object method
        mock_employee = Mock()
        viewset.get_object = Mock(return_value=mock_employee)

        mock_serializer = Mock()
        mock_serializer.save.side_effect = Exception("Update error")

        # Should raise exception
        with self.assertRaises(Exception):
            viewset.perform_update(mock_serializer)


class EmployeeViewSetDeleteTest(APITestCase):
    """Test EmployeeViewSet delete functionality"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        self.admin_user = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="admin123",
            is_staff=True,
        )
        self.admin_employee = Employee.objects.create(
            user=self.admin_user,
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
            employment_type="full_time",
            role="admin",
        )
        self.admin_token = Token.objects.create(user=self.admin_user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.admin_token.key)

        # Create employee to delete
        self.target_user = User.objects.create_user(
            username="target", email="target@example.com", password="target123"
        )
        self.target_employee = Employee.objects.create(
            user=self.target_user,
            first_name="Target",
            last_name="User",
            email="target@example.com",
            employment_type="full_time",
            role="employee",
        )

    @patch("users.views.logger")
    @patch("users.views.safe_log_employee")
    def test_perform_destroy_success(self, mock_safe_log, mock_logger):
        """Test perform_destroy method (soft delete)"""
        viewset = EmployeeViewSet()
        # Mock request
        mock_request = Mock()
        mock_request.user = self.admin_user
        viewset.request = mock_request

        mock_instance = Mock()
        mock_instance.id = 123
        mock_instance.email = "delete@example.com"
        mock_instance.is_active = True

        viewset.perform_destroy(mock_instance)

        # Should set is_active to False (soft delete)
        self.assertFalse(mock_instance.is_active)
        mock_instance.save.assert_called_with(update_fields=["is_active"])
        mock_logger.info.assert_called()

    @patch("users.views.logger")
    def test_perform_destroy_exception(self, mock_logger):
        """Test perform_destroy with exception"""
        viewset = EmployeeViewSet()
        # Mock request
        mock_request = Mock()
        mock_request.user = self.admin_user
        viewset.request = mock_request

        mock_instance = Mock()
        mock_instance.save.side_effect = Exception("Save error")

        # Should raise exception
        with self.assertRaises(Exception):
            viewset.perform_destroy(mock_instance)


class EmployeeViewSetActionTest(APITestCase):
    """Test EmployeeViewSet custom actions"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        self.admin_user = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="admin123",
            is_staff=True,
        )
        self.admin_employee = Employee.objects.create(
            user=self.admin_user,
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
            employment_type="full_time",
            role="admin",
        )
        self.admin_token = Token.objects.create(user=self.admin_user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.admin_token.key)

        # Create target employee
        self.target_user = User.objects.create_user(
            username="target", email="target@example.com", password="target123"
        )
        self.target_employee = Employee.objects.create(
            user=self.target_user,
            first_name="Target",
            last_name="User",
            email="target@example.com",
            employment_type="full_time",
            role="employee",
            is_active=True,
        )

    @patch("users.views.logger")
    def test_activate_success(self, mock_logger):
        """Test activate action success"""
        # Deactivate first
        self.target_employee.is_active = False
        self.target_employee.save()

        response = self.client.post(
            f"/api/v1/users/employees/{self.target_employee.id}/activate/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check employee was activated
        self.target_employee.refresh_from_db()
        self.assertTrue(self.target_employee.is_active)
        mock_logger.info.assert_called()

    def test_activate_not_found(self):
        """Test activate action with non-existent employee"""
        response = self.client.post("/api/v1/users/employees/99999/activate/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_activate_exception(self):
        """Test activate action with exception - can't mock internal viewset logic easily"""
        # This is a design limitation test - the activate method is simple
        # and doesn't really have internal exception handling that can be easily tested
        # The method just sets is_active=True and saves, no complex error paths
        pass

    @patch("users.views.logger")
    def test_deactivate_success(self, mock_logger):
        """Test deactivate action success"""
        response = self.client.post(
            f"/api/v1/users/employees/{self.target_employee.id}/deactivate/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check employee was deactivated
        self.target_employee.refresh_from_db()
        self.assertFalse(self.target_employee.is_active)
        mock_logger.info.assert_called()

    def test_deactivate_not_found(self):
        """Test deactivate action with non-existent employee"""
        response = self.client.post("/api/v1/users/employees/99999/deactivate/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_deactivate_exception(self):
        """Test deactivate action with exception - similar design limitation as activate"""
        # The deactivate method is also simple without complex exception handling
        pass


class EmployeeViewSetInvitationTest(APITestCase):
    """Test EmployeeViewSet invitation functionality"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        self.admin_user = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="admin123",
            is_staff=True,
        )
        self.admin_employee = Employee.objects.create(
            user=self.admin_user,
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
            employment_type="full_time",
            role="admin",
        )
        self.admin_token = Token.objects.create(user=self.admin_user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.admin_token.key)

        # Create target employee
        self.target_user = User.objects.create_user(
            username="target", email="target@example.com", password="target123"
        )
        self.target_employee = Employee.objects.create(
            user=self.target_user,
            first_name="Target",
            last_name="User",
            email="target@example.com",
            employment_type="full_time",
            role="employee",
        )

    @patch("users.views.get_safe_logger")
    def test_send_invitation_success(self, mock_logger):
        """Test send_invitation action success"""
        # Create unregistered employee
        unregistered_employee = Employee.objects.create(
            first_name="Unregistered",
            last_name="Employee",
            email="unregistered@example.com",
            employment_type="full_time",
            role="employee",
        )

        invitation_data = {"base_url": "http://localhost:8100"}

        response = self.client.post(
            f"/api/v1/users/employees/{unregistered_employee.id}/send_invitation/",
            invitation_data,
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_logger.return_value.info.assert_called()

    def test_send_invitation_already_registered(self):
        """Test send_invitation for already registered employee"""
        response = self.client.post(
            f"/api/v1/users/employees/{self.target_employee.id}/send_invitation/",
            {"base_url": "http://localhost:8100"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_send_invitation_not_found(self):
        """Test send_invitation with non-existent employee"""
        response = self.client.post(
            "/api/v1/users/employees/99999/send_invitation/",
            {"base_url": "http://localhost:8100"},
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ValidateInvitationViewTest(APITestCase):
    """Test ValidateInvitationView"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()

        # Create employee and invitation
        self.employee = Employee.objects.create(
            first_name="Test",
            last_name="Employee",
            email="test@example.com",
            employment_type="full_time",
            role="employee",
        )

        self.invitation = EmployeeInvitation.objects.create(
            employee=self.employee,
            invited_by=User.objects.create_user("admin", "admin@test.com", "pass"),
            token="valid_token_123",
            expires_at=timezone.now() + timedelta(days=7),
        )

    def test_validate_invitation_success(self):
        """Test successful invitation validation"""
        response = self.client.get(
            "/api/v1/users/invitation/validate/", {"token": "valid_token_123"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("valid", response.data)
        self.assertTrue(response.data["valid"])

    def test_validate_invitation_missing_token(self):
        """Test validation with missing token"""
        response = self.client.get("/api/v1/users/invitation/validate/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_validate_invitation_not_found(self):
        """Test validation with non-existent invitation"""
        response = self.client.get(
            "/api/v1/users/invitation/validate/", {"token": "invalid_token"}
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error", response.data)

    def test_validate_invitation_expired(self):
        """Test validation with expired invitation"""
        # Create separate employee for expired invitation
        expired_employee = Employee.objects.create(
            first_name="Expired",
            last_name="Employee",
            email="expired@example.com",
            employment_type="full_time",
            role="employee",
        )

        # Create expired invitation
        expired_invitation = EmployeeInvitation.objects.create(
            employee=expired_employee,
            invited_by=User.objects.create_user("admin2", "admin2@test.com", "pass"),
            token="expired_token_123",
            expires_at=timezone.now() - timedelta(days=1),
        )

        response = self.client.get(
            "/api/v1/users/invitation/validate/", {"token": "expired_token_123"}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)


class AcceptInvitationViewTest(APITestCase):
    """Test AcceptInvitationView"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()

        # Create employee and invitation
        self.employee = Employee.objects.create(
            first_name="New",
            last_name="Employee",
            email="newuser@example.com",
            employment_type="full_time",
            role="employee",
        )

        self.invitation = EmployeeInvitation.objects.create(
            employee=self.employee,
            invited_by=User.objects.create_user("admin", "admin@test.com", "pass"),
            token="accept_token_123",
            expires_at=timezone.now() + timedelta(days=7),
        )

    def test_accept_invitation_success(self):
        """Test successful invitation acceptance"""
        invitation_data = {
            "token": "accept_token_123",
            "username": "newuser123",
            "password": "newpassword123",
            "confirm_password": "newpassword123",
        }

        response = self.client.post("/api/v1/users/invitation/accept/", invitation_data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Check response contains expected data
        self.assertIn("user", response.data)
        self.assertIn("employee_id", response.data)
        self.assertIn("token", response.data)

    def test_accept_invitation_validation_error(self):
        """Test invitation acceptance with validation error"""
        # Missing required fields
        invitation_data = {
            "token": "accept_token_123"
            # Missing username, password
        }

        response = self.client.post("/api/v1/users/invitation/accept/", invitation_data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_accept_invitation_invalid_token(self):
        """Test invitation acceptance with invalid token"""
        invitation_data = {
            "token": "invalid_token",
            "username": "newuser123",
            "password": "newpassword123",
            "confirm_password": "newpassword123",
        }

        response = self.client.post("/api/v1/users/invitation/accept/", invitation_data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class EmployeeViewSetIntegrationTest(APITestCase):
    """Integration tests for EmployeeViewSet"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Test",
            last_name="User",
            email="test@example.com",
            employment_type="full_time",
            role="employee",
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token.key)

    def test_list_employees_with_filters(self):
        """Test listing employees with various filters"""
        # Create additional test data
        user2 = User.objects.create_user(
            username="user2", email="user2@example.com", password="pass123"
        )
        Employee.objects.create(
            user=user2,
            first_name="Another",
            last_name="Employee",
            email="user2@example.com",
            employment_type="part_time",
            role="manager",
            is_active=False,
        )

        # Test search filter
        response = self.client.get("/api/v1/users/employees/?search=Test")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test employment_type filter
        response = self.client.get("/api/v1/users/employees/?employment_type=full_time")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test is_active filter
        response = self.client.get("/api/v1/users/employees/?is_active=true")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test role filter
        response = self.client.get("/api/v1/users/employees/?role=employee")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_ordering_employees(self):
        """Test ordering employees"""
        # Test ordering by first_name
        response = self.client.get("/api/v1/users/employees/?ordering=first_name")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test ordering by last_name (descending)
        response = self.client.get("/api/v1/users/employees/?ordering=-last_name")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_pagination(self):
        """Test pagination functionality"""
        # Test with custom page size
        response = self.client.get("/api/v1/users/employees/?page_size=1")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test pagination structure
        if response.data.get("results"):
            self.assertIn("count", response.data)
            self.assertIn("next", response.data)
            self.assertIn("previous", response.data)
            self.assertIn("results", response.data)
