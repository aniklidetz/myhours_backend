"""
Targeted tests for users/models.py
Focus on achieving 80%+ coverage for uncovered model methods and properties
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from users.models import Employee, EmployeeInvitation, EmployeeManager, EmployeeQuerySet


class EmployeeManagerTest(TestCase):
    """Test custom Employee manager functionality"""

    def test_employee_manager_get_queryset(self):
        """Test that custom manager returns EmployeeQuerySet"""
        manager = EmployeeManager()
        manager.model = Employee
        queryset = manager.get_queryset()

        self.assertIsInstance(queryset, EmployeeQuerySet)

    def test_employee_manager_with_optimized_annotations(self):
        """Test with_optimized_annotations method"""
        # Create test employees
        user = User.objects.create_user("testuser", "test@test.com", "pass123")
        employee = Employee.objects.create(
            user=user,
            first_name="Test",
            last_name="User",
            email="test@test.com",
            employment_type="full_time",
            role="employee",
        )

        # Test the optimized annotations method
        employees = Employee.objects.with_optimized_annotations()
        employee = employees.first()

        # Check that annotations are added
        self.assertTrue(hasattr(employee, "has_biometric_annotation"))
        self.assertTrue(hasattr(employee, "has_pending_invitation_annotation"))


class EmployeeQuerySetTest(TestCase):
    """Test custom Employee QuerySet functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user("testuser", "test@test.com", "pass123")
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Query",
            last_name="Test",
            email="query@test.com",
            employment_type="full_time",
            role="employee",
        )

    def test_queryset_with_optimized_annotations(self):
        """Test with_optimized_annotations method on queryset"""
        queryset = Employee.objects.all().with_optimized_annotations()
        employee = queryset.first()

        # Verify annotations exist
        self.assertTrue(hasattr(employee, "has_biometric_annotation"))
        self.assertTrue(hasattr(employee, "has_pending_invitation_annotation"))

        # The annotations should be boolean values (False since no biometric/invitation exists)
        self.assertFalse(employee.has_biometric_annotation)
        self.assertFalse(employee.has_pending_invitation_annotation)


class EmployeeModelTest(TestCase):
    """Test Employee model functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_employee_creation_basic(self):
        """Test basic employee creation"""
        employee = Employee.objects.create(
            user=self.user,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            employment_type="full_time",
            role="employee",
        )

        self.assertEqual(employee.first_name, "John")
        self.assertEqual(employee.last_name, "Doe")
        self.assertEqual(employee.email, "john@example.com")
        self.assertEqual(employee.employment_type, "full_time")
        self.assertEqual(employee.role, "employee")
        self.assertTrue(employee.is_active)

    def test_employee_clean_method_valid_phone(self):
        """Test clean method with valid phone number"""
        employee = Employee(
            user=self.user,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="+972501234567",  # Valid Israeli number
            employment_type="full_time",
            role="employee",
        )

        # Should not raise ValidationError
        try:
            employee.clean()
        except ValidationError:
            self.fail("clean() raised ValidationError with valid phone")

    def test_employee_clean_method_invalid_phone(self):
        """Test clean method with invalid phone number"""
        employee = Employee(
            user=self.user,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="123-456-7890",  # Invalid format (no country code)
            employment_type="full_time",
            role="employee",
        )

        with self.assertRaises(ValidationError) as cm:
            employee.clean()

        self.assertIn("phone", cm.exception.message_dict)
        self.assertIn("international format", str(cm.exception.message_dict["phone"]))

    def test_employee_clean_method_invalid_employment_type(self):
        """Test clean method with invalid employment type"""
        employee = Employee(
            user=self.user,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            employment_type="invalid_type",
            role="employee",
        )

        with self.assertRaises(ValidationError) as cm:
            employee.clean()

        self.assertIn("employment_type", cm.exception.message_dict)

    def test_employee_clean_method_invalid_role(self):
        """Test clean method with invalid role"""
        employee = Employee(
            user=self.user,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            employment_type="full_time",
            role="invalid_role",
        )

        with self.assertRaises(ValidationError) as cm:
            employee.clean()

        self.assertIn("role", cm.exception.message_dict)

    def test_is_valid_phone_method_valid_numbers(self):
        """Test _is_valid_phone method with valid phone numbers"""
        employee = Employee(
            first_name="Test", last_name="User", email="test@example.com"
        )

        valid_phones = [
            "+972501234567",
            "+1234567890",
            "+44 20 7123 4567",  # With spaces
            "+33-1-23-45-67-89",  # With dashes
            "+86 138 0013 8000",
        ]

        for phone in valid_phones:
            self.assertTrue(
                employee._is_valid_phone(phone), f"Phone {phone} should be valid"
            )

    def test_is_valid_phone_method_invalid_numbers(self):
        """Test _is_valid_phone method with invalid phone numbers"""
        employee = Employee(
            first_name="Test", last_name="User", email="test@example.com"
        )

        invalid_phones = [
            "123456789",  # No country code
            "+1",  # Too short
            "abc123",  # Non-numeric
            "+972-abc-def",  # Contains letters
            "",  # Empty string
        ]

        for phone in invalid_phones:
            self.assertFalse(
                employee._is_valid_phone(phone), f"Phone {phone} should be invalid"
            )

    def test_employee_save_method_admin_role(self):
        """Test save method updates user permissions for admin role"""
        employee = Employee.objects.create(
            user=self.user,
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
            role="admin",
        )

        # Refresh user from database
        self.user.refresh_from_db()

        # Check that user permissions were updated
        self.assertTrue(self.user.is_staff)
        self.assertTrue(self.user.is_superuser)
        self.assertEqual(self.user.first_name, "Admin")
        self.assertEqual(self.user.last_name, "User")
        self.assertEqual(self.user.email, "admin@example.com")

    def test_employee_save_method_manager_role(self):
        """Test save method updates user permissions for manager role"""
        employee = Employee.objects.create(
            user=self.user,
            first_name="Manager",
            last_name="User",
            email="manager@example.com",
            role="manager",
        )

        # Refresh user from database
        self.user.refresh_from_db()

        # Check permissions for manager
        self.assertTrue(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)

    def test_employee_save_method_employee_role(self):
        """Test save method updates user permissions for employee role"""
        employee = Employee.objects.create(
            user=self.user,
            first_name="Regular",
            last_name="Employee",
            email="employee@example.com",
            role="employee",
        )

        # Refresh user from database
        self.user.refresh_from_db()

        # Check permissions for regular employee
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)

    def test_employee_save_method_without_user(self):
        """Test save method when employee has no associated user"""
        employee = Employee.objects.create(
            user=None,  # No user associated
            first_name="No",
            last_name="User",
            email="nouser@example.com",
            role="employee",
        )

        # Should not raise any exceptions
        self.assertIsNone(employee.user)

    def test_get_full_name_method(self):
        """Test get_full_name method"""
        employee = Employee(first_name="John", last_name="Doe")
        self.assertEqual(employee.get_full_name(), "John Doe")

        # Test with spaces
        employee = Employee(first_name=" John ", last_name=" Doe ")
        self.assertEqual(
            employee.get_full_name(), "John   Doe"
        )  # strip() only removes leading/trailing

    def test_get_display_name_method(self):
        """Test get_display_name method"""
        employee = Employee(
            first_name="John", last_name="Doe", email="john@example.com"
        )
        self.assertEqual(employee.get_display_name(), "John Doe (john@example.com)")

    def test_str_method(self):
        """Test __str__ method"""
        employee = Employee(first_name="Jane", last_name="Smith")
        self.assertEqual(str(employee), "Jane Smith")

    def test_is_registered_property_with_user(self):
        """Test is_registered property when user exists"""
        employee = Employee(user=self.user, first_name="Test", last_name="User")
        self.assertTrue(employee.is_registered)

    def test_is_registered_property_without_user(self):
        """Test is_registered property when user is None"""
        employee = Employee(user=None, first_name="Test", last_name="User")
        self.assertFalse(employee.is_registered)

    def test_salary_info_property_exists(self):
        """Test salary_info property when salary exists"""
        # Create employee
        employee = Employee.objects.create(
            user=self.user,
            first_name="Salary",
            last_name="Test",
            email="salary@example.com",
            employment_type="full_time",
            role="employee",
        )

        # Create salary for employee
        from payroll.models import Salary

        salary = Salary.objects.create(
            employee=employee,
            base_salary=Decimal("5000.00"),
            calculation_type="monthly",
            currency="ILS",
        )

        # Test property
        self.assertEqual(employee.salary_info, salary)

    def test_salary_info_reverse_relation_not_exists(self):
        """Test salary_info reverse relationship when no salary exists"""
        employee = Employee.objects.create(
            user=self.user,
            first_name="No",
            last_name="Salary",
            email="nosalary@example.com",
            employment_type="full_time",
            role="employee",
        )

        # Django OneToOneField reverse relationship raises RelatedObjectDoesNotExist
        # when no related object exists (this overrides the @property method)
        from payroll.models import Salary

        with self.assertRaises(Salary.DoesNotExist):
            _ = employee.salary_info

    def test_salary_property_backward_compatibility(self):
        """Test salary property (backward compatibility alias)"""
        employee = Employee.objects.create(
            user=self.user,
            first_name="Backward",
            last_name="Compat",
            email="compat@example.com",
            employment_type="full_time",
            role="employee",
        )

        # Create salary for testing both paths
        from decimal import Decimal

        from payroll.models import Salary

        salary = Salary.objects.create(
            employee=employee,
            base_salary=Decimal("3000.00"),
            calculation_type="monthly",
            currency="ILS",
        )

        # Both should return the same salary object
        self.assertEqual(employee.salary, employee.salary_info)
        self.assertEqual(employee.salary, salary)

    def test_worklog_set_property(self):
        """Test worklog_set property (backward compatibility)"""
        employee = Employee.objects.create(
            user=self.user,
            first_name="Work",
            last_name="Log",
            email="worklog@example.com",
            employment_type="full_time",
            role="employee",
        )

        # Test that worklog_set returns a queryset
        worklog_set = employee.worklog_set
        self.assertTrue(hasattr(worklog_set, "filter"))  # Should be a manager/queryset

    def test_has_biometric_property_with_annotation(self):
        """Test has_biometric property when annotation exists"""
        employee = Employee.objects.create(
            user=self.user,
            first_name="Bio",
            last_name="Metric",
            email="bio@example.com",
            employment_type="full_time",
            role="employee",
        )

        # Mock annotation
        employee.has_biometric_annotation = True
        self.assertTrue(employee.has_biometric)

        employee.has_biometric_annotation = False
        self.assertFalse(employee.has_biometric)

    def test_has_biometric_property_without_user(self):
        """Test has_biometric property when employee has no user"""
        employee = Employee(
            user=None, first_name="No", last_name="User", email="nouser@example.com"
        )

        self.assertFalse(employee.has_biometric)

    def test_has_biometric_property_with_biometric_profile(self):
        """Test has_biometric property when biometric profile exists"""
        employee = Employee.objects.create(
            user=self.user,
            first_name="Has",
            last_name="Bio",
            email="hasbio@example.com",
            employment_type="full_time",
            role="employee",
        )

        # Create biometric profile
        from biometrics.models import BiometricProfile

        BiometricProfile.objects.create(employee=employee)

        self.assertTrue(employee.has_biometric)

    def test_has_biometric_property_exception_handling(self):
        """Test has_biometric property exception handling"""
        employee = Employee.objects.create(
            user=self.user,
            first_name="Exception",
            last_name="Test",
            email="exception@example.com",
            employment_type="full_time",
            role="employee",
        )

        # The property should handle exceptions gracefully - test normal behavior
        result = employee.has_biometric
        self.assertIsInstance(result, bool)  # Should return a boolean, not crash
        self.assertFalse(result)  # No biometric profile exists

    def test_send_notification_method(self):
        """Test send_notification method"""
        employee = Employee(
            first_name="Notification", last_name="Test", email="notify@example.com"
        )

        with self.assertLogs("users.models", level="INFO") as cm:
            result = employee.send_notification("Test message", "info")

        self.assertTrue(result)
        self.assertIn("Notification to notify@example.com", cm.output[0])
        self.assertIn("[info] Test message", cm.output[0])

    def test_send_notification_method_default_type(self):
        """Test send_notification method with default notification type"""
        employee = Employee(
            first_name="Default", last_name="Type", email="default@example.com"
        )

        with self.assertLogs("users.models", level="INFO") as cm:
            result = employee.send_notification("Default message")

        self.assertTrue(result)
        self.assertIn("[info]", cm.output[0])  # Should use default 'info' type


class EmployeeInvitationTest(TestCase):
    """Test EmployeeInvitation model functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="inviter", email="inviter@example.com", password="pass123"
        )

        self.employee = Employee.objects.create(
            first_name="Invited",
            last_name="Employee",
            email="invited@example.com",
            employment_type="full_time",
            role="employee",
        )

    def test_employee_invitation_creation(self):
        """Test basic EmployeeInvitation creation"""
        invitation = EmployeeInvitation.objects.create(
            employee=self.employee,
            invited_by=self.user,
            token="test_token_123",
            expires_at=timezone.now() + timedelta(days=2),
        )

        self.assertEqual(invitation.employee, self.employee)
        self.assertEqual(invitation.invited_by, self.user)
        self.assertEqual(invitation.token, "test_token_123")
        self.assertFalse(invitation.email_sent)
        self.assertIsNone(invitation.email_sent_at)
        self.assertIsNone(invitation.accepted_at)

    def test_create_invitation_classmethod(self):
        """Test create_invitation class method"""
        invitation = EmployeeInvitation.create_invitation(
            employee=self.employee, invited_by=self.user, days_valid=3
        )

        self.assertEqual(invitation.employee, self.employee)
        self.assertEqual(invitation.invited_by, self.user)
        self.assertIsNotNone(invitation.token)
        self.assertEqual(
            len(invitation.token), 43
        )  # token_urlsafe(32) produces ~43 chars

        # Check expiration time
        expected_expires = timezone.now() + timedelta(days=3)
        time_diff = abs((invitation.expires_at - expected_expires).total_seconds())
        self.assertLess(time_diff, 60)  # Within 1 minute tolerance

    def test_create_invitation_default_days(self):
        """Test create_invitation with default days_valid"""
        invitation = EmployeeInvitation.create_invitation(
            employee=self.employee, invited_by=self.user
        )

        # Should default to 2 days
        expected_expires = timezone.now() + timedelta(days=2)
        time_diff = abs((invitation.expires_at - expected_expires).total_seconds())
        self.assertLess(time_diff, 60)

    def test_is_valid_property_valid_invitation(self):
        """Test is_valid property for valid invitation"""
        invitation = EmployeeInvitation.objects.create(
            employee=self.employee,
            invited_by=self.user,
            token="valid_token",
            expires_at=timezone.now() + timedelta(days=1),  # Future expiration
        )

        self.assertTrue(invitation.is_valid)

    def test_is_valid_property_expired_invitation(self):
        """Test is_valid property for expired invitation"""
        invitation = EmployeeInvitation.objects.create(
            employee=self.employee,
            invited_by=self.user,
            token="expired_token",
            expires_at=timezone.now() - timedelta(days=1),  # Past expiration
        )

        self.assertFalse(invitation.is_valid)

    def test_is_valid_property_accepted_invitation(self):
        """Test is_valid property for accepted invitation"""
        invitation = EmployeeInvitation.objects.create(
            employee=self.employee,
            invited_by=self.user,
            token="accepted_token",
            expires_at=timezone.now() + timedelta(days=1),
            accepted_at=timezone.now(),  # Already accepted
        )

        self.assertFalse(invitation.is_valid)

    def test_is_accepted_property_not_accepted(self):
        """Test is_accepted property when not accepted"""
        invitation = EmployeeInvitation.objects.create(
            employee=self.employee,
            invited_by=self.user,
            token="pending_token",
            expires_at=timezone.now() + timedelta(days=1),
        )

        self.assertFalse(invitation.is_accepted)

    def test_is_accepted_property_accepted(self):
        """Test is_accepted property when accepted"""
        invitation = EmployeeInvitation.objects.create(
            employee=self.employee,
            invited_by=self.user,
            token="accepted_token",
            expires_at=timezone.now() + timedelta(days=1),
            accepted_at=timezone.now(),
        )

        self.assertTrue(invitation.is_accepted)

    def test_is_expired_property_not_expired(self):
        """Test is_expired property when not expired"""
        invitation = EmployeeInvitation.objects.create(
            employee=self.employee,
            invited_by=self.user,
            token="fresh_token",
            expires_at=timezone.now() + timedelta(days=1),
        )

        self.assertFalse(invitation.is_expired)

    def test_is_expired_property_expired(self):
        """Test is_expired property when expired"""
        invitation = EmployeeInvitation.objects.create(
            employee=self.employee,
            invited_by=self.user,
            token="old_token",
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        self.assertTrue(invitation.is_expired)

    def test_accept_method(self):
        """Test accept method"""
        new_user = User.objects.create_user(
            username="newemployee", email="newemployee@example.com", password="pass123"
        )

        invitation = EmployeeInvitation.objects.create(
            employee=self.employee,
            invited_by=self.user,
            token="accept_token",
            expires_at=timezone.now() + timedelta(days=1),
        )

        # Accept the invitation
        result_employee = invitation.accept(new_user)

        # Check that invitation is marked as accepted
        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.accepted_at)
        self.assertTrue(invitation.is_accepted)

        # Check that user is linked to employee
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.user, new_user)
        self.assertEqual(result_employee, self.employee)

    def test_get_invitation_url_method(self):
        """Test get_invitation_url method"""
        invitation = EmployeeInvitation.objects.create(
            employee=self.employee,
            invited_by=self.user,
            token="url_token_123",
            expires_at=timezone.now() + timedelta(days=1),
        )

        base_url = "https://myapp.com"
        url = invitation.get_invitation_url(base_url)

        self.assertEqual(url, "https://myapp.com/invite?token=url_token_123")

    def test_str_method_pending_invitation(self):
        """Test __str__ method for pending invitation"""
        invitation = EmployeeInvitation.objects.create(
            employee=self.employee,
            invited_by=self.user,
            token="pending_str",
            expires_at=timezone.now() + timedelta(days=1),
        )

        expected_str = f"Invitation for {self.employee.email} - Pending"
        self.assertEqual(str(invitation), expected_str)

    def test_str_method_accepted_invitation(self):
        """Test __str__ method for accepted invitation"""
        invitation = EmployeeInvitation.objects.create(
            employee=self.employee,
            invited_by=self.user,
            token="accepted_str",
            expires_at=timezone.now() + timedelta(days=1),
            accepted_at=timezone.now(),
        )

        expected_str = f"Invitation for {self.employee.email} - Accepted"
        self.assertEqual(str(invitation), expected_str)


class EmployeeInvitationIntegrationTest(TestCase):
    """Integration tests for Employee and EmployeeInvitation models"""

    def setUp(self):
        """Set up test data"""
        self.admin_user = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="admin123",
            is_staff=True,
        )

    def test_complete_invitation_workflow(self):
        """Test complete workflow from invitation to acceptance"""
        # Step 1: Create employee without user
        employee = Employee.objects.create(
            first_name="New",
            last_name="Hire",
            email="newhire@example.com",
            employment_type="full_time",
            role="employee",
        )

        self.assertFalse(employee.is_registered)
        self.assertIsNone(employee.user)

        # Step 2: Create invitation
        invitation = EmployeeInvitation.create_invitation(
            employee=employee, invited_by=self.admin_user, days_valid=7
        )

        self.assertTrue(invitation.is_valid)
        self.assertFalse(invitation.is_accepted)
        self.assertFalse(invitation.is_expired)

        # Step 3: Accept invitation
        new_user = User.objects.create_user(
            username="newhire", email="newhire@example.com", password="newpass123"
        )

        accepted_employee = invitation.accept(new_user)

        # Step 4: Verify final state
        employee.refresh_from_db()
        invitation.refresh_from_db()

        self.assertTrue(employee.is_registered)
        self.assertEqual(employee.user, new_user)
        self.assertTrue(invitation.is_accepted)
        self.assertFalse(invitation.is_valid)  # No longer valid because accepted
        self.assertEqual(accepted_employee, employee)

        # Step 5: Test relationships
        self.assertEqual(employee.invitation, invitation)
        self.assertIn(invitation, self.admin_user.sent_invitations.all())

    def test_employee_roles_and_permissions_integration(self):
        """Test employee roles affecting user permissions"""
        # Test different roles
        roles_permissions = [
            ("admin", True, True),  # is_staff, is_superuser
            ("manager", True, False),
            ("accountant", True, False),
            ("hr", True, False),
            ("project_manager", True, False),
            ("employee", False, False),
        ]

        for role, expected_staff, expected_superuser in roles_permissions:
            with self.subTest(role=role):
                user = User.objects.create_user(
                    username=f"user_{role}",
                    email=f"{role}@example.com",
                    password="pass123",
                )

                employee = Employee.objects.create(
                    user=user,
                    first_name="Test",
                    last_name=role.title(),
                    email=f"{role}@example.com",
                    role=role,
                )

                # Refresh user to get updated permissions
                user.refresh_from_db()

                self.assertEqual(
                    user.is_staff,
                    expected_staff,
                    f"Role {role} should have is_staff={expected_staff}",
                )
                self.assertEqual(
                    user.is_superuser,
                    expected_superuser,
                    f"Role {role} should have is_superuser={expected_superuser}",
                )

    def test_employee_meta_attributes(self):
        """Test Employee model meta attributes"""
        self.assertEqual(Employee._meta.ordering, ["last_name", "first_name"])
        self.assertEqual(Employee._meta.verbose_name, "Employee")
        self.assertEqual(Employee._meta.verbose_name_plural, "Employees")

        # Test indexes exist
        index_fields = [index.fields for index in Employee._meta.indexes]
        expected_indexes = [["email"], ["is_active"], ["role"], ["employment_type"]]

        for expected_index in expected_indexes:
            self.assertIn(expected_index, index_fields)

    def test_employee_invitation_meta_attributes(self):
        """Test EmployeeInvitation model meta attributes"""
        self.assertEqual(EmployeeInvitation._meta.ordering, ["-created_at"])

        # Test indexes exist
        index_fields = [index.fields for index in EmployeeInvitation._meta.indexes]
        expected_indexes = [["token"], ["expires_at"]]

        for expected_index in expected_indexes:
            self.assertIn(expected_index, index_fields)
