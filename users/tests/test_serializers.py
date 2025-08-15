"""
Tests for users serializers - EmployeeSerializer, EmployeeInvitationSerializer, SendInvitationSerializer,
EmployeeUpdateSerializer, AcceptInvitationSerializer validation branches and edge cases.
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from rest_framework import serializers

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from payroll.models import Salary
from users.models import Employee, EmployeeInvitation
from users.serializers import (
    AcceptInvitationSerializer,
    EmployeeInvitationSerializer,
    EmployeeSerializer,
    EmployeeUpdateSerializer,
    SendInvitationSerializer,
)


class EmployeeSerializerTest(TestCase):
    """Tests for EmployeeSerializer"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="test123"
        )

        self.employee = Employee.objects.create(
            user=self.user,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            employment_type="full_time",
            role="employee",
        )

    def test_read_only_fields(self):
        """Test that read-only fields are properly configured"""
        serializer = EmployeeSerializer()
        expected_read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "is_registered",
            "has_biometric",
        ]
        self.assertEqual(serializer.Meta.read_only_fields, expected_read_only_fields)

    def test_serialization_basic_fields(self):
        """Test basic field serialization"""
        serializer = EmployeeSerializer(self.employee)
        data = serializer.data

        self.assertEqual(data["first_name"], "John")
        self.assertEqual(data["last_name"], "Doe")
        self.assertEqual(data["email"], "john@example.com")
        self.assertEqual(data["employment_type"], "full_time")
        self.assertEqual(data["role"], "employee")
        self.assertTrue(data["is_active"])

        # Test computed read-only fields
        self.assertEqual(data["full_name"], "John Doe")
        self.assertEqual(data["display_name"], "John Doe (john@example.com)")

    def test_get_has_biometric_with_prefetched_objects(self):
        """Test get_has_biometric with prefetched objects cache"""
        # Mock employee with prefetched objects cache
        mock_employee = MagicMock()
        mock_employee._prefetched_objects_cache = {"biometric_profile": []}
        mock_employee.biometric_profile = MagicMock()

        serializer = EmployeeSerializer()
        result = serializer.get_has_biometric(mock_employee)
        self.assertTrue(result)

    def test_get_has_biometric_no_prefetch_with_profile(self):
        """Test get_has_biometric without prefetch but with profile"""
        mock_employee = MagicMock()
        mock_employee._prefetched_objects_cache = None
        # Remove prefetch cache attribute to test hasattr branch
        del mock_employee._prefetched_objects_cache
        mock_employee.biometric_profile = MagicMock()

        serializer = EmployeeSerializer()
        result = serializer.get_has_biometric(mock_employee)
        self.assertTrue(result)

    def test_get_has_biometric_no_profile(self):
        """Test get_has_biometric with RelatedObjectDoesNotExist"""
        mock_employee = MagicMock()
        del mock_employee._prefetched_objects_cache

        # Mock biometric_profile to raise RelatedObjectDoesNotExist
        mock_profile = MagicMock()
        mock_profile.RelatedObjectDoesNotExist = Exception
        mock_employee.biometric_profile = mock_profile
        mock_employee.biometric_profile.RelatedObjectDoesNotExist = Exception

        # Make accessing the profile raise the exception
        def side_effect():
            raise mock_employee.biometric_profile.RelatedObjectDoesNotExist()

        type(mock_employee).biometric_profile = property(lambda x: side_effect())

        serializer = EmployeeSerializer()
        result = serializer.get_has_biometric(mock_employee)
        self.assertFalse(result)

    def test_get_has_biometric_fallback_to_property(self):
        """Test get_has_biometric fallback to has_biometric property"""
        mock_employee = MagicMock()
        del mock_employee._prefetched_objects_cache
        del mock_employee.biometric_profile
        mock_employee.has_biometric = True

        serializer = EmployeeSerializer()
        result = serializer.get_has_biometric(mock_employee)
        self.assertTrue(result)

    def test_get_has_biometric_exception_handling(self):
        """Test get_has_biometric exception handling"""

        # Create an object that raises exception when accessed
        class ErrorEmployee:
            def __getattribute__(self, name):
                raise Exception("Generic error")

        error_employee = ErrorEmployee()

        serializer = EmployeeSerializer()
        result = serializer.get_has_biometric(error_employee)
        self.assertFalse(result)

    def test_get_hourly_rate_with_prefetch(self):
        """Test get_hourly_rate with prefetched salary info"""
        mock_employee = MagicMock()
        mock_employee._prefetched_objects_cache = {"salary_info": []}

        mock_salary = MagicMock()
        mock_salary.hourly_rate = Decimal("50.00")
        mock_employee.salary_info = mock_salary

        serializer = EmployeeSerializer()
        result = serializer.get_hourly_rate(mock_employee)
        self.assertEqual(result, 50.0)

    def test_get_hourly_rate_no_salary_info(self):
        """Test get_hourly_rate when salary_info is None"""
        mock_employee = MagicMock()
        mock_employee._prefetched_objects_cache = {"salary_info": []}
        mock_employee.salary_info = None

        serializer = EmployeeSerializer()
        result = serializer.get_hourly_rate(mock_employee)
        self.assertIsNone(result)

    def test_get_hourly_rate_no_hourly_rate_field(self):
        """Test get_hourly_rate when hourly_rate is None"""
        mock_employee = MagicMock()
        mock_employee._prefetched_objects_cache = {"salary_info": []}

        mock_salary = MagicMock()
        mock_salary.hourly_rate = None
        mock_employee.salary_info = mock_salary

        serializer = EmployeeSerializer()
        result = serializer.get_hourly_rate(mock_employee)
        self.assertIsNone(result)

    def test_get_hourly_rate_fallback_no_prefetch(self):
        """Test get_hourly_rate fallback without prefetch"""
        mock_employee = MagicMock()
        del mock_employee._prefetched_objects_cache

        mock_salary = MagicMock()
        mock_salary.hourly_rate = Decimal("25.00")
        mock_employee.salary_info = mock_salary

        serializer = EmployeeSerializer()
        result = serializer.get_hourly_rate(mock_employee)
        self.assertEqual(result, 25.0)

    def test_get_hourly_rate_no_salary_info_fallback(self):
        """Test get_hourly_rate fallback when no salary_info"""
        mock_employee = MagicMock()
        del mock_employee._prefetched_objects_cache
        mock_employee.salary_info = None

        serializer = EmployeeSerializer()
        result = serializer.get_hourly_rate(mock_employee)
        self.assertIsNone(result)

    def test_get_hourly_rate_exception_handling(self):
        """Test get_hourly_rate exception handling"""

        # Create an object that raises exception when accessed
        class ErrorEmployee:
            def __getattribute__(self, name):
                raise Exception("Generic error")

        error_employee = ErrorEmployee()

        serializer = EmployeeSerializer()
        result = serializer.get_hourly_rate(error_employee)
        self.assertIsNone(result)

    def test_get_monthly_salary_with_prefetch(self):
        """Test get_monthly_salary with prefetched salary info"""
        mock_employee = MagicMock()
        mock_employee._prefetched_objects_cache = {"salary_info": []}

        mock_salary = MagicMock()
        mock_salary.base_salary = Decimal("5000.00")
        mock_employee.salary_info = mock_salary

        serializer = EmployeeSerializer()
        result = serializer.get_monthly_salary(mock_employee)
        self.assertEqual(result, 5000.0)

    def test_get_monthly_salary_no_base_salary(self):
        """Test get_monthly_salary when base_salary is None"""
        mock_employee = MagicMock()
        mock_employee._prefetched_objects_cache = {"salary_info": []}

        mock_salary = MagicMock()
        mock_salary.base_salary = None
        mock_employee.salary_info = mock_salary

        serializer = EmployeeSerializer()
        result = serializer.get_monthly_salary(mock_employee)
        self.assertIsNone(result)

    def test_get_has_pending_invitation_with_prefetch(self):
        """Test get_has_pending_invitation with prefetched invitation"""
        mock_employee = MagicMock()
        mock_employee._prefetched_objects_cache = {"invitation": []}

        mock_invitation = MagicMock()
        mock_invitation.is_valid = True
        mock_employee.invitation = mock_invitation

        serializer = EmployeeSerializer()
        result = serializer.get_has_pending_invitation(mock_employee)
        self.assertTrue(result)

    def test_get_has_pending_invitation_no_invitation(self):
        """Test get_has_pending_invitation when no invitation"""
        mock_employee = MagicMock()
        mock_employee._prefetched_objects_cache = {"invitation": []}
        mock_employee.invitation = None

        serializer = EmployeeSerializer()
        result = serializer.get_has_pending_invitation(mock_employee)
        self.assertFalse(result)

    def test_get_has_pending_invitation_invalid_invitation(self):
        """Test get_has_pending_invitation with invalid invitation"""
        mock_employee = MagicMock()
        mock_employee._prefetched_objects_cache = {"invitation": []}

        mock_invitation = MagicMock()
        mock_invitation.is_valid = False
        mock_employee.invitation = mock_invitation

        serializer = EmployeeSerializer()
        result = serializer.get_has_pending_invitation(mock_employee)
        self.assertFalse(result)

    def test_get_has_pending_invitation_fallback(self):
        """Test get_has_pending_invitation fallback without prefetch"""
        mock_employee = MagicMock()
        del mock_employee._prefetched_objects_cache

        mock_invitation = MagicMock()
        mock_invitation.is_valid = True
        mock_employee.invitation = mock_invitation

        serializer = EmployeeSerializer()
        result = serializer.get_has_pending_invitation(mock_employee)
        self.assertTrue(result)

    def test_get_has_pending_invitation_exception_handling(self):
        """Test get_has_pending_invitation exception handling"""

        # Create an object that raises exception when accessed
        class ErrorEmployee:
            def __getattribute__(self, name):
                raise Exception("Generic error")

        error_employee = ErrorEmployee()

        serializer = EmployeeSerializer()
        result = serializer.get_has_pending_invitation(error_employee)
        self.assertFalse(result)

    def test_validate_email_new_employee_valid(self):
        """Test email validation for new employee with valid email"""
        serializer = EmployeeSerializer()

        valid_email = "new@example.com"
        result = serializer.validate_email(valid_email)
        self.assertEqual(result, valid_email)

    def test_validate_email_new_employee_duplicate(self):
        """Test email validation for new employee with duplicate email"""
        serializer = EmployeeSerializer()

        # Use existing employee's email
        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate_email(self.employee.email)

        self.assertIn("Employee with this email already exists", str(cm.exception))

    def test_validate_email_existing_employee_same_email(self):
        """Test email validation for existing employee keeping same email"""
        serializer = EmployeeSerializer(instance=self.employee)

        # Using same email should be valid
        result = serializer.validate_email(self.employee.email)
        self.assertEqual(result, self.employee.email)

    def test_validate_email_existing_employee_duplicate_email(self):
        """Test email validation for existing employee with duplicate email"""
        # Create another employee
        other_user = User.objects.create_user(
            username="other", email="other@example.com"
        )
        other_employee = Employee.objects.create(
            user=other_user,
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            employment_type="full_time",
            role="employee",
        )

        serializer = EmployeeSerializer(instance=self.employee)

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate_email(other_employee.email)

        self.assertIn("Employee with this email already exists", str(cm.exception))

    def test_validate_email_empty_value(self):
        """Test email validation with empty value"""
        serializer = EmployeeSerializer()

        result = serializer.validate_email("")
        self.assertEqual(result, "")

        result = serializer.validate_email(None)
        self.assertIsNone(result)

    def test_validate_phone_valid_format(self):
        """Test phone validation with valid international format"""
        serializer = EmployeeSerializer()

        valid_phones = ["+972501234567", "+1234567890123", "+44123456789"]

        for phone in valid_phones:
            with self.subTest(phone=phone):
                result = serializer.validate_phone(phone)
                self.assertEqual(result, phone)

    def test_validate_phone_valid_format_with_spaces_dashes(self):
        """Test phone validation with spaces and dashes"""
        serializer = EmployeeSerializer()

        phone_with_spaces = "+972 50 123 4567"
        phone_with_dashes = "+972-50-123-4567"

        result = serializer.validate_phone(phone_with_spaces)
        self.assertEqual(result, phone_with_spaces)

        result = serializer.validate_phone(phone_with_dashes)
        self.assertEqual(result, phone_with_dashes)

    def test_validate_phone_invalid_format(self):
        """Test phone validation with invalid format"""
        serializer = EmployeeSerializer()

        invalid_phones = [
            "123456789",  # No country code
            "+123",  # Too short (less than 8 digits after country code)
            "+1234567890123456789",  # Too long (more than 15 digits after country code)
            "abc123456789",  # Contains letters
            "+123-abc-456",  # Contains letters after cleaning
        ]

        for phone in invalid_phones:
            with self.subTest(phone=phone):
                with self.assertRaises(serializers.ValidationError) as cm:
                    serializer.validate_phone(phone)
                self.assertIn("international format", str(cm.exception))

    def test_validate_phone_empty_value(self):
        """Test phone validation with empty value"""
        serializer = EmployeeSerializer()

        result = serializer.validate_phone("")
        self.assertEqual(result, "")

        result = serializer.validate_phone(None)
        self.assertIsNone(result)

    def test_validate_cross_field_same_names(self):
        """Test cross-field validation when first and last name are identical"""
        serializer = EmployeeSerializer()

        attrs = {"first_name": "John", "last_name": "John"}

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate(attrs)

        self.assertIn("identical", str(cm.exception))

    def test_validate_cross_field_different_names(self):
        """Test cross-field validation with different names"""
        serializer = EmployeeSerializer()

        attrs = {"first_name": "John", "last_name": "Doe"}

        result = serializer.validate(attrs)
        self.assertEqual(result, attrs)


class EmployeeInvitationSerializerTest(TestCase):
    """Tests for EmployeeInvitationSerializer"""

    def setUp(self):
        """Set up test data"""
        # Create users
        self.user = User.objects.create_user(
            username="employee", email="employee@example.com"
        )
        self.admin_user = User.objects.create_user(
            username="admin", email="admin@example.com"
        )

        # Create employees
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            employment_type="full_time",
            role="employee",
        )

        self.admin_employee = Employee.objects.create(
            user=self.admin_user,
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
            employment_type="full_time",
            role="admin",
        )

        # Create invitation
        self.invitation = EmployeeInvitation.objects.create(
            employee=self.employee,
            invited_by=self.admin_user,  # Use User, not Employee
            token="test_token_123",
            expires_at=timezone.now() + timedelta(days=7),
        )

    def test_serialization_all_fields(self):
        """Test serialization includes all expected fields"""
        serializer = EmployeeInvitationSerializer(self.invitation)
        data = serializer.data

        expected_fields = [
            "id",
            "employee",
            "employee_name",
            "employee_email",
            "token",
            "invited_by",
            "invited_by_name",
            "created_at",
            "expires_at",
            "accepted_at",
            "email_sent",
            "email_sent_at",
            "is_valid",
            "is_accepted",
            "is_expired",
        ]

        for field in expected_fields:
            self.assertIn(field, data)

        # Test computed read-only fields
        self.assertEqual(data["employee_name"], "John Doe")
        self.assertEqual(data["employee_email"], "john@example.com")
        # invited_by_name comes from User, not Employee, so it won't have get_full_name method
        self.assertIsNotNone(data["invited_by_name"])

    def test_read_only_fields(self):
        """Test read-only fields configuration"""
        serializer = EmployeeInvitationSerializer()
        expected_read_only_fields = [
            "id",
            "token",
            "created_at",
            "expires_at",
            "accepted_at",
            "is_valid",
            "is_accepted",
            "is_expired",
        ]
        self.assertEqual(serializer.Meta.read_only_fields, expected_read_only_fields)


class SendInvitationSerializerTest(TestCase):
    """Tests for SendInvitationSerializer"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="employee", email="employee@example.com"
        )
        self.registered_user = User.objects.create_user(
            username="registered", email="reg@example.com"
        )

        self.employee = Employee.objects.create(
            user=None,  # Unregistered employee
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            employment_type="full_time",
            role="employee",
        )

        self.registered_employee = Employee.objects.create(
            user=self.registered_user,  # Registered employee
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            employment_type="full_time",
            role="employee",
        )

    def test_validate_employee_id_valid_unregistered(self):
        """Test validation with valid unregistered employee"""
        serializer = SendInvitationSerializer()

        result = serializer.validate_employee_id(self.employee.id)
        self.assertEqual(result, self.employee.id)

    def test_validate_employee_id_already_registered(self):
        """Test validation with already registered employee"""
        serializer = SendInvitationSerializer()

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate_employee_id(self.registered_employee.id)

        self.assertIn("already has an account", str(cm.exception))

    def test_validate_employee_id_has_pending_invitation(self):
        """Test validation with employee who has pending invitation"""
        # Create pending invitation
        EmployeeInvitation.objects.create(
            employee=self.employee,
            invited_by=self.registered_user,  # Use User, not Employee
            token="pending_token",
            expires_at=timezone.now() + timedelta(days=7),
        )

        serializer = SendInvitationSerializer()

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate_employee_id(self.employee.id)

        self.assertIn("pending invitation", str(cm.exception))

    def test_validate_employee_id_not_found(self):
        """Test validation with non-existent employee ID"""
        serializer = SendInvitationSerializer()

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate_employee_id(99999)

        self.assertIn("not found", str(cm.exception))

    def test_default_base_url(self):
        """Test default base_url field"""
        data = {"employee_id": self.employee.id}
        serializer = SendInvitationSerializer(data=data)

        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["base_url"], "http://localhost:8100")


class EmployeeUpdateSerializerTest(TestCase):
    """Tests for EmployeeUpdateSerializer"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="employee", email="employee@example.com"
        )

        self.employee = Employee.objects.create(
            user=self.user,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="+972501234567",
            employment_type="full_time",
            role="employee",
        )

    def test_phone_number_alias_field(self):
        """Test phone_number field alias for backward compatibility"""
        data = {"phone_number": "+972507654321", "first_name": "Updated John"}

        serializer = EmployeeUpdateSerializer(data=data)
        self.assertTrue(serializer.is_valid())

        # Verify phone_number maps to phone
        self.assertEqual(serializer.validated_data["phone"], "+972507654321")

    def test_validate_phone_valid_format(self):
        """Test phone validation with valid format"""
        serializer = EmployeeUpdateSerializer()

        valid_phone = "+972501234567"
        result = serializer.validate_phone(valid_phone)
        self.assertEqual(result, valid_phone)

    def test_validate_phone_invalid_format(self):
        """Test phone validation with invalid format"""
        serializer = EmployeeUpdateSerializer()

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate_phone("123456789")

        self.assertIn("international format", str(cm.exception))

    def test_validate_employment_type_valid(self):
        """Test employment type validation with valid choice"""
        serializer = EmployeeUpdateSerializer()

        valid_type = "full_time"
        result = serializer.validate_employment_type(valid_type)
        self.assertEqual(result, valid_type)

    def test_validate_employment_type_invalid(self):
        """Test employment type validation with invalid choice"""
        serializer = EmployeeUpdateSerializer()

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate_employment_type("invalid_type")

        self.assertIn("Invalid employment type", str(cm.exception))

    def test_validate_role_valid(self):
        """Test role validation with valid choice"""
        serializer = EmployeeUpdateSerializer()

        valid_role = "employee"
        result = serializer.validate_role(valid_role)
        self.assertEqual(result, valid_role)

    def test_validate_role_invalid(self):
        """Test role validation with invalid choice"""
        serializer = EmployeeUpdateSerializer()

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate_role("invalid_role")

        self.assertIn("Invalid role", str(cm.exception))

    def test_validate_cross_field_identical_names(self):
        """Test cross-field validation with identical names"""
        serializer = EmployeeUpdateSerializer()

        attrs = {"first_name": "John", "last_name": "John"}

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate(attrs)

        self.assertIn("identical", str(cm.exception))

    def test_validate_cross_field_names_with_whitespace(self):
        """Test cross-field validation handles whitespace properly"""
        serializer = EmployeeUpdateSerializer()

        # Should pass - different after stripping
        attrs1 = {"first_name": " John ", "last_name": "John"}

        result = serializer.validate(attrs1)
        self.assertNotIn("address", result)  # address should be removed

    def test_validate_cross_field_empty_names(self):
        """Test cross-field validation with empty/None names"""
        serializer = EmployeeUpdateSerializer()

        # These should not trigger validation error
        test_cases = [
            {"first_name": None, "last_name": "Doe"},
            {"first_name": "", "last_name": "Doe"},
            {"first_name": "   ", "last_name": "Doe"},
            {"first_name": "John", "last_name": None},
            {"first_name": "John", "last_name": ""},
            {"first_name": "John", "last_name": "   "},
        ]

        for attrs in test_cases:
            with self.subTest(attrs=attrs):
                result = serializer.validate(attrs)
                # Should not raise ValidationError
                self.assertIsInstance(result, dict)

    def test_address_field_removed(self):
        """Test that address field is removed from validated data"""
        serializer = EmployeeUpdateSerializer()

        attrs = {
            "first_name": "John",
            "address": "123 Main St",
            "phone": "+972501234567",
        }

        result = serializer.validate(attrs)

        # Address should be removed
        self.assertNotIn("address", result)
        self.assertIn("first_name", result)
        self.assertIn("phone", result)


class AcceptInvitationSerializerTest(TestCase):
    """Tests for AcceptInvitationSerializer"""

    def setUp(self):
        """Set up test data"""
        self.admin_user = User.objects.create_user(
            username="admin", email="admin@example.com"
        )
        self.existing_user = User.objects.create_user(
            username="existing", email="existing@example.com"
        )

        # Create multiple employees to avoid unique constraint issues
        self.employee = Employee.objects.create(
            user=None,  # Not registered yet
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            employment_type="full_time",
            role="employee",
        )

        self.employee2 = Employee.objects.create(
            user=None,  # Not registered yet
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            employment_type="full_time",
            role="employee",
        )

        self.employee3 = Employee.objects.create(
            user=None,  # Not registered yet
            first_name="Bob",
            last_name="Wilson",
            email="bob@example.com",
            employment_type="full_time",
            role="employee",
        )

        self.admin_employee = Employee.objects.create(
            user=self.admin_user,
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
            employment_type="full_time",
            role="admin",
        )

        # Create valid invitation
        self.valid_invitation = EmployeeInvitation.objects.create(
            employee=self.employee,
            invited_by=self.admin_user,  # Use User, not Employee
            token="valid_token_123",
            expires_at=timezone.now() + timedelta(days=7),
        )

        # Create expired invitation
        self.expired_invitation = EmployeeInvitation.objects.create(
            employee=self.employee2,
            invited_by=self.admin_user,  # Use User, not Employee
            token="expired_token_123",
            expires_at=timezone.now() - timedelta(days=1),
        )

        # Create accepted invitation
        self.accepted_invitation = EmployeeInvitation.objects.create(
            employee=self.employee3,
            invited_by=self.admin_user,  # Use User, not Employee
            token="accepted_token_123",
            expires_at=timezone.now() + timedelta(days=7),
            accepted_at=timezone.now(),
        )

    def test_validate_token_valid(self):
        """Test token validation with valid token"""
        serializer = AcceptInvitationSerializer()

        result = serializer.validate_token(self.valid_invitation.token)
        self.assertEqual(result, self.valid_invitation.token)

    def test_validate_token_already_accepted(self):
        """Test token validation with already accepted invitation"""
        serializer = AcceptInvitationSerializer()

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate_token(self.accepted_invitation.token)

        self.assertIn("already been accepted", str(cm.exception))

    def test_validate_token_expired(self):
        """Test token validation with expired invitation"""
        serializer = AcceptInvitationSerializer()

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate_token(self.expired_invitation.token)

        self.assertIn("expired", str(cm.exception))

    def test_validate_token_not_found(self):
        """Test token validation with non-existent token"""
        serializer = AcceptInvitationSerializer()

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate_token("non_existent_token")

        self.assertIn("Invalid invitation token", str(cm.exception))

    def test_validate_username_available(self):
        """Test username validation with available username"""
        serializer = AcceptInvitationSerializer()

        new_username = "newuser123"
        result = serializer.validate_username(new_username)
        self.assertEqual(result, new_username)

    def test_validate_username_taken(self):
        """Test username validation with taken username"""
        serializer = AcceptInvitationSerializer()

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate_username(self.existing_user.username)

        self.assertIn("already taken", str(cm.exception))

    def test_validate_passwords_match(self):
        """Test cross-field validation with matching passwords"""
        serializer = AcceptInvitationSerializer()

        attrs = {
            "token": "valid_token",
            "username": "newuser",
            "password": "SecurePass123",
            "confirm_password": "SecurePass123",
        }

        result = serializer.validate(attrs)
        self.assertEqual(result, attrs)

    def test_validate_passwords_dont_match(self):
        """Test cross-field validation with non-matching passwords"""
        serializer = AcceptInvitationSerializer()

        attrs = {
            "token": "valid_token",
            "username": "newuser",
            "password": "SecurePass123",
            "confirm_password": "DifferentPass456",
        }

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate(attrs)

        self.assertIn("do not match", str(cm.exception))

    def test_complete_serializer_validation(self):
        """Test complete serializer validation with valid data"""
        data = {
            "token": self.valid_invitation.token,
            "username": "newjohnuser",
            "password": "SecurePass123",
            "confirm_password": "SecurePass123",
        }

        serializer = AcceptInvitationSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

        validated_data = serializer.validated_data
        self.assertEqual(validated_data["token"], self.valid_invitation.token)
        self.assertEqual(validated_data["username"], "newjohnuser")
        self.assertEqual(validated_data["password"], "SecurePass123")

    def test_password_write_only(self):
        """Test that password fields are write-only"""
        data = {
            "token": self.valid_invitation.token,
            "username": "testuser",
            "password": "SecurePass123",
            "confirm_password": "SecurePass123",
        }

        serializer = AcceptInvitationSerializer(data=data)
        self.assertTrue(serializer.is_valid())

        # Passwords should not appear in serialized data
        serialized_data = serializer.data
        self.assertNotIn("password", serialized_data)
        self.assertNotIn("confirm_password", serialized_data)
