"""
Tests for user permissions - role-based access control and biometric verification.
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from django.conf import settings
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.utils import timezone

from users.models import DeviceToken, Employee
from users.permissions import (
    AccountantWithBiometric,
    BiometricVerificationRequired,
    EmployeeWithBiometric,
    IsAccountantOrAdmin,
    IsAdminOnly,
    IsEmployeeOrAbove,
    IsSelfOrAbove,
    LocationBasedPermission,
    PayrollAccessPermission,
    WorkTimeOperationPermission,
)


class BasePermissionTestCase(TestCase):
    """Base test case for permission tests"""

    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()

        # Create users
        self.employee_user = User.objects.create_user(
            username="employee", email="employee@test.com", password="test123"
        )

        self.accountant_user = User.objects.create_user(
            username="accountant", email="accountant@test.com", password="test123"
        )

        self.admin_user = User.objects.create_user(
            username="admin", email="admin@test.com", password="test123"
        )

        self.unauthorized_user = User.objects.create_user(
            username="unauthorized", email="unauthorized@test.com", password="test123"
        )

        # Create employees
        self.employee = Employee.objects.create(
            user=self.employee_user,
            first_name="Test",
            last_name="Employee",
            email="employee@test.com",
            employment_type="full_time",
            role="employee",
        )

        self.accountant = Employee.objects.create(
            user=self.accountant_user,
            first_name="Test",
            last_name="Accountant",
            email="accountant@test.com",
            employment_type="full_time",
            role="accountant",
        )

        self.admin = Employee.objects.create(
            user=self.admin_user,
            first_name="Test",
            last_name="Admin",
            email="admin@test.com",
            employment_type="full_time",
            role="admin",
        )

        # Create device tokens
        self.employee_token = DeviceToken.objects.create(
            user=self.employee_user,
            token="employee_token_123",
            device_id="employee_device",
            expires_at=timezone.now() + timedelta(hours=1),
            is_active=True,
            biometric_verified=True,
            biometric_verified_at=timezone.now(),
        )

        self.accountant_token = DeviceToken.objects.create(
            user=self.accountant_user,
            device_id="accountant_device",
            token="accountant_token_123",
            biometric_verified=True,
            biometric_verified_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=1),
        )


class IsEmployeeOrAboveTest(BasePermissionTestCase):
    """Tests for IsEmployeeOrAbove permission"""

    def setUp(self):
        super().setUp()
        self.permission = IsEmployeeOrAbove()

    def test_employee_access_granted(self):
        """Test that employee role gets access"""
        request = self.factory.get("/")
        request.user = self.employee_user

        self.assertTrue(self.permission.has_permission(request, None))

    def test_accountant_access_granted(self):
        """Test that accountant role gets access"""
        request = self.factory.get("/")
        request.user = self.accountant_user

        self.assertTrue(self.permission.has_permission(request, None))

    def test_admin_access_granted(self):
        """Test that admin role gets access"""
        request = self.factory.get("/")
        request.user = self.admin_user

        self.assertTrue(self.permission.has_permission(request, None))

    def test_unauthorized_user_access_denied(self):
        """Test that user without employee record gets denied"""
        request = self.factory.get("/")
        request.user = self.unauthorized_user

        self.assertFalse(self.permission.has_permission(request, None))

    def test_anonymous_user_access_denied(self):
        """Test that anonymous user gets denied"""
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.get("/")
        request.user = AnonymousUser()

        self.assertFalse(self.permission.has_permission(request, None))

    def test_permission_message(self):
        """Test permission error message"""
        self.assertEqual(self.permission.message, "Employee access required")


class IsAccountantOrAdminTest(BasePermissionTestCase):
    """Tests for IsAccountantOrAdmin permission"""

    def setUp(self):
        super().setUp()
        self.permission = IsAccountantOrAdmin()

    def test_employee_access_denied(self):
        """Test that employee role gets denied"""
        request = self.factory.get("/")
        request.user = self.employee_user

        self.assertFalse(self.permission.has_permission(request, None))

    def test_accountant_access_granted(self):
        """Test that accountant role gets access"""
        request = self.factory.get("/")
        request.user = self.accountant_user

        self.assertTrue(self.permission.has_permission(request, None))

    def test_admin_access_granted(self):
        """Test that admin role gets access"""
        request = self.factory.get("/")
        request.user = self.admin_user

        self.assertTrue(self.permission.has_permission(request, None))

    def test_permission_message(self):
        """Test permission error message"""
        self.assertEqual(self.permission.message, "Accountant or Admin access required")


class IsAdminOnlyTest(BasePermissionTestCase):
    """Tests for IsAdminOnly permission"""

    def setUp(self):
        super().setUp()
        self.permission = IsAdminOnly()

    def test_employee_access_denied(self):
        """Test that employee role gets denied"""
        request = self.factory.get("/")
        request.user = self.employee_user

        self.assertFalse(self.permission.has_permission(request, None))

    def test_accountant_access_denied(self):
        """Test that accountant role gets denied"""
        request = self.factory.get("/")
        request.user = self.accountant_user

        self.assertFalse(self.permission.has_permission(request, None))

    def test_admin_access_granted(self):
        """Test that admin role gets access"""
        request = self.factory.get("/")
        request.user = self.admin_user

        self.assertTrue(self.permission.has_permission(request, None))

    def test_permission_message(self):
        """Test permission error message"""
        self.assertEqual(self.permission.message, "Admin access required")


class IsSelfOrAboveTest(BasePermissionTestCase):
    """Tests for IsSelfOrAbove permission"""

    def setUp(self):
        super().setUp()
        self.permission = IsSelfOrAbove()

    def test_has_permission_authenticated_user(self):
        """Test that authenticated users have basic permission"""
        request = self.factory.get("/")
        request.user = self.employee_user

        self.assertTrue(self.permission.has_permission(request, None))

    def test_has_permission_anonymous_user(self):
        """Test that anonymous users don't have permission"""
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.get("/")
        request.user = AnonymousUser()

        self.assertFalse(self.permission.has_permission(request, None))

    def test_admin_can_access_any_object(self):
        """Test that admin can access any object"""
        request = self.factory.get("/")
        request.user = self.admin_user

        # Test with employee object
        self.assertTrue(
            self.permission.has_object_permission(request, None, self.employee)
        )

    def test_accountant_can_access_employee_data(self):
        """Test that accountant can access employee data"""
        request = self.factory.get("/")
        request.user = self.accountant_user

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.employee)
        )

    def test_accountant_cannot_access_admin_data(self):
        """Test that accountant cannot access admin data"""
        request = self.factory.get("/")
        request.user = self.accountant_user

        self.assertFalse(
            self.permission.has_object_permission(request, None, self.admin)
        )

    def test_user_can_access_own_data_via_user_attribute(self):
        """Test that users can access their own data"""
        request = self.factory.get("/")
        request.user = self.employee_user

        # Mock object with user attribute
        obj = MagicMock()
        obj.user = self.employee_user

        self.assertTrue(self.permission.has_object_permission(request, None, obj))

    def test_user_can_access_own_data_via_employee_attribute(self):
        """Test that users can access their own data via employee"""
        request = self.factory.get("/")
        request.user = self.employee_user

        # Create a simple namespace object instead of MagicMock
        from types import SimpleNamespace

        obj = SimpleNamespace()
        obj.employee = self.employee

        self.assertTrue(self.permission.has_object_permission(request, None, obj))

    def test_user_cannot_access_others_data(self):
        """Test that users cannot access other users' data"""
        request = self.factory.get("/")
        request.user = self.employee_user

        # Mock object belonging to different user
        obj = MagicMock()
        obj.user = self.accountant_user

        self.assertFalse(self.permission.has_object_permission(request, None, obj))


class BiometricVerificationRequiredTest(BasePermissionTestCase):
    """Tests for BiometricVerificationRequired permission"""

    def setUp(self):
        super().setUp()
        self.permission = BiometricVerificationRequired(max_age_hours=1)

    def test_permission_with_recent_verification(self):
        """Test permission granted with recent biometric verification"""
        request = self.factory.get("/")
        request.user = self.employee_user
        request.device_token = self.employee_token

        self.assertTrue(self.permission.has_permission(request, None))

    def test_permission_with_expired_verification(self):
        """Test permission denied with expired verification"""
        request = self.factory.get("/")
        request.user = self.employee_user

        # Create expired token
        expired_token = DeviceToken.objects.create(
            user=self.employee_user,
            device_id="expired_device",
            token="expired_token_123",
            biometric_verified=True,
            biometric_verified_at=timezone.now() - timedelta(hours=2),
            expires_at=timezone.now() + timedelta(days=1),
        )
        request.device_token = expired_token

        self.assertFalse(self.permission.has_permission(request, None))

    def test_permission_without_device_token(self):
        """Test permission denied without device token"""
        request = self.factory.get("/")
        request.user = self.employee_user
        # No device_token attribute

        self.assertFalse(self.permission.has_permission(request, None))

    def test_permission_without_biometric_verification(self):
        """Test permission denied without biometric verification"""
        request = self.factory.get("/")
        request.user = self.employee_user

        # Token without biometric verification
        unverified_token = DeviceToken.objects.create(
            user=self.employee_user,
            device_id="unverified_device",
            token="unverified_token_123",
            biometric_verified=False,
            expires_at=timezone.now() + timedelta(days=1),
        )
        request.device_token = unverified_token

        self.assertFalse(self.permission.has_permission(request, None))

    def test_anonymous_user_denied(self):
        """Test that anonymous user is denied"""
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.get("/")
        request.user = AnonymousUser()

        self.assertFalse(self.permission.has_permission(request, None))

    def test_custom_max_age_hours(self):
        """Test custom max_age_hours parameter"""
        permission_2h = BiometricVerificationRequired(max_age_hours=2)

        request = self.factory.get("/")
        request.user = self.employee_user

        # Create token verified 1.5 hours ago
        token_1_5h = DeviceToken.objects.create(
            user=self.employee_user,
            device_id="1_5h_device",
            token="1_5h_token_123",
            biometric_verified=True,
            biometric_verified_at=timezone.now() - timedelta(hours=1.5),
            expires_at=timezone.now() + timedelta(days=1),
        )
        request.device_token = token_1_5h

        # Should be allowed with 2-hour limit
        self.assertTrue(permission_2h.has_permission(request, None))

        # Should be denied with 1-hour limit
        permission_1h = BiometricVerificationRequired(max_age_hours=1)
        self.assertFalse(permission_1h.has_permission(request, None))


class WorkTimeOperationPermissionTest(BasePermissionTestCase):
    """Tests for WorkTimeOperationPermission"""

    def setUp(self):
        super().setUp()
        self.permission = WorkTimeOperationPermission()

    @patch.object(settings, "BIOMETRIC_VERIFICATION_REQUIRED_FOR", [])
    def test_permission_when_biometric_not_required(self):
        """Test permission granted when biometric not required for time tracking"""
        request = self.factory.get("/")
        request.user = self.employee_user

        self.assertTrue(self.permission.has_permission(request, None))

    @patch.object(settings, "BIOMETRIC_VERIFICATION_REQUIRED_FOR", ["time_tracking"])
    def test_permission_when_biometric_required_and_verified(self):
        """Test permission granted when biometric required and user is verified"""
        request = self.factory.get("/")
        request.user = self.employee_user
        request.device_token = self.employee_token

        self.assertTrue(self.permission.has_permission(request, None))

    @patch.object(settings, "BIOMETRIC_VERIFICATION_REQUIRED_FOR", ["time_tracking"])
    def test_permission_when_biometric_required_and_not_verified(self):
        """Test permission denied when biometric required but not verified"""
        request = self.factory.get("/")
        request.user = self.employee_user
        # No device token

        self.assertFalse(self.permission.has_permission(request, None))

    @patch.object(settings, "BIOMETRIC_VERIFICATION_REQUIRED_FOR", ["time_tracking"])
    def test_admin_override(self):
        """Test admin can override biometric requirement"""
        request = self.factory.get("/")
        request.user = self.admin_user
        request.META = {"HTTP_X_ADMIN_OVERRIDE": "true"}

        self.assertTrue(self.permission.has_permission(request, None))

    @patch.object(settings, "BIOMETRIC_VERIFICATION_REQUIRED_FOR", ["time_tracking"])
    def test_admin_without_override_header(self):
        """Test admin without override header still needs biometric"""
        request = self.factory.get("/")
        request.user = self.admin_user
        request.META = {}
        # No device token

        self.assertFalse(self.permission.has_permission(request, None))

    @patch.object(settings, "BIOMETRIC_VERIFICATION_REQUIRED_FOR", ["time_tracking"])
    def test_expired_biometric_verification(self):
        """Test expired biometric verification is denied"""
        request = self.factory.get("/")
        request.user = self.employee_user

        # Create token verified 9 hours ago (limit is 8 hours)
        expired_token = DeviceToken.objects.create(
            user=self.employee_user,
            device_id="expired_device",
            token="expired_token_123",
            biometric_verified=True,
            biometric_verified_at=timezone.now() - timedelta(hours=9),
            expires_at=timezone.now() + timedelta(days=1),
        )
        request.device_token = expired_token

        self.assertFalse(self.permission.has_permission(request, None))


class LocationBasedPermissionTest(BasePermissionTestCase):
    """Tests for LocationBasedPermission"""

    def setUp(self):
        super().setUp()
        self.permission = LocationBasedPermission()

    def test_permission_without_location_data(self):
        """Test permission granted when no location data present"""
        request = self.factory.get("/")
        request.user = self.employee_user

        self.assertTrue(self.permission.has_permission(request, None))

    def test_permission_with_location_data(self):
        """Test permission with location data (currently allows all)"""
        request = self.factory.post(
            "/", {"location": {"latitude": 32.0853, "longitude": 34.7818}}
        )
        request.user = self.employee_user

        # Currently implemented to allow all locations
        self.assertTrue(self.permission.has_permission(request, None))

    def test_anonymous_user_denied(self):
        """Test that anonymous user is denied"""
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.get("/")
        request.user = AnonymousUser()

        self.assertFalse(self.permission.has_permission(request, None))


class PayrollAccessPermissionTest(BasePermissionTestCase):
    """Tests for PayrollAccessPermission"""

    def setUp(self):
        super().setUp()
        self.permission = PayrollAccessPermission()

        # Update accountant token verification time to be recent
        self.accountant_token.biometric_verified_at = timezone.now()
        self.accountant_token.save()

    def test_accountant_with_recent_biometric_granted(self):
        """Test accountant with recent biometric verification gets access"""
        request = self.factory.get("/")
        request.user = self.accountant_user
        request.device_token = self.accountant_token

        self.assertTrue(self.permission.has_permission(request, None))

    def test_admin_with_recent_biometric_granted(self):
        """Test admin with recent biometric verification gets access"""
        request = self.factory.get("/")
        request.user = self.admin_user

        # Create admin token
        admin_token = DeviceToken.objects.create(
            user=self.admin_user,
            device_id="admin_device",
            token="admin_token_123",
            biometric_verified=True,
            biometric_verified_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        request.device_token = admin_token

        self.assertTrue(self.permission.has_permission(request, None))

    def test_employee_access_denied(self):
        """Test that regular employee is denied access"""
        request = self.factory.get("/")
        request.user = self.employee_user
        request.device_token = self.employee_token

        self.assertFalse(self.permission.has_permission(request, None))

    def test_accountant_without_biometric_denied(self):
        """Test accountant without biometric verification is denied"""
        request = self.factory.get("/")
        request.user = self.accountant_user
        # No device token

        self.assertFalse(self.permission.has_permission(request, None))

    def test_expired_biometric_verification_denied(self):
        """Test expired biometric verification is denied"""
        request = self.factory.get("/")
        request.user = self.accountant_user

        # Update token to be expired (more than 30 minutes old)
        self.accountant_token.biometric_verified_at = timezone.now() - timedelta(
            minutes=31
        )
        self.accountant_token.save()
        request.device_token = self.accountant_token

        self.assertFalse(self.permission.has_permission(request, None))


class ComboPermissionTest(BasePermissionTestCase):
    """Tests for combination permissions"""

    def setUp(self):
        super().setUp()
        self.employee_with_biometric = EmployeeWithBiometric()
        self.accountant_with_biometric = AccountantWithBiometric()

    def test_employee_with_biometric_success(self):
        """Test EmployeeWithBiometric allows verified employee"""
        request = self.factory.get("/")
        request.user = self.employee_user
        request.device_token = self.employee_token

        self.assertTrue(self.employee_with_biometric.has_permission(request, None))

    def test_employee_with_biometric_no_verification(self):
        """Test EmployeeWithBiometric denies employee without biometric"""
        request = self.factory.get("/")
        request.user = self.employee_user
        # No device token

        self.assertFalse(self.employee_with_biometric.has_permission(request, None))

    def test_accountant_with_biometric_success(self):
        """Test AccountantWithBiometric allows verified accountant"""
        request = self.factory.get("/")
        request.user = self.accountant_user
        request.device_token = self.accountant_token

        self.assertTrue(self.accountant_with_biometric.has_permission(request, None))

    def test_accountant_with_biometric_employee_denied(self):
        """Test AccountantWithBiometric denies regular employee even with biometric"""
        request = self.factory.get("/")
        request.user = self.employee_user
        request.device_token = self.employee_token

        self.assertFalse(self.accountant_with_biometric.has_permission(request, None))

    def test_accountant_with_biometric_no_verification(self):
        """Test AccountantWithBiometric denies accountant without biometric"""
        request = self.factory.get("/")
        request.user = self.accountant_user
        # No device token

        self.assertFalse(self.accountant_with_biometric.has_permission(request, None))


class PermissionErrorMessageTest(BasePermissionTestCase):
    """Tests for permission error messages"""

    def test_biometric_verification_required_message(self):
        """Test BiometricVerificationRequired error message"""
        permission = BiometricVerificationRequired()
        self.assertEqual(
            permission.message, "Biometric verification required for this operation"
        )

    def test_work_time_operation_permission_message(self):
        """Test WorkTimeOperationPermission error message"""
        permission = WorkTimeOperationPermission()
        self.assertEqual(
            permission.message,
            "Biometric verification required for time tracking operations",
        )

    def test_location_based_permission_message(self):
        """Test LocationBasedPermission error message"""
        permission = LocationBasedPermission()
        self.assertEqual(
            permission.message, "Operation not allowed from current location"
        )

    def test_payroll_access_permission_message(self):
        """Test PayrollAccessPermission error message"""
        permission = PayrollAccessPermission()
        self.assertEqual(
            permission.message,
            "Payroll access requires accountant privileges and biometric verification",
        )

    def test_is_self_or_above_message(self):
        """Test IsSelfOrAbove error message"""
        permission = IsSelfOrAbove()
        self.assertEqual(
            permission.message,
            "Access denied: can only access own data or need higher privileges",
        )


class PermissionIntegrationTest(BasePermissionTestCase):
    """Integration tests for permissions with actual views"""

    def setUp(self):
        super().setUp()
        self.api_factory = APIRequestFactory()

    def test_permission_integration_with_view(self):
        """Test that permissions work correctly with actual view"""

        class TestView(APIView):
            permission_classes = [IsEmployeeOrAbove]

            def get(self, request):
                return Response({"message": "success"})

        view = TestView.as_view()

        # Test with employee user
        request = self.api_factory.get("/")
        request.user = self.employee_user

        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test with unauthorized user
        request = self.api_factory.get("/")
        request.user = self.unauthorized_user

        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_multiple_permissions_integration(self):
        """Test that multiple permissions work together"""

        class TestView(APIView):
            permission_classes = [IsAccountantOrAdmin, BiometricVerificationRequired]

            def get(self, request):
                return Response({"message": "success"})

        view = TestView.as_view()

        # Test with accountant and biometric verification
        request = self.api_factory.get("/")
        request.user = self.accountant_user
        request.device_token = self.accountant_token

        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test with accountant but no biometric verification
        request = self.api_factory.get("/")
        request.user = self.accountant_user
        # No device token

        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
