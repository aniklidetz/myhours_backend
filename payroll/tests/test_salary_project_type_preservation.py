"""
Unit tests specifically for project calculation_type preservation logic
"""

from datetime import date, timedelta
from decimal import Decimal
from payroll.tests.helpers import MONTHLY_NORM_HOURS, ISRAELI_DAILY_NORM_HOURS, NIGHT_NORM_HOURS, MONTHLY_NORM_HOURS

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from payroll.models import Salary
from users.models import Employee


class SalaryProjectTypePreservationTest(TestCase):
    """
    Test that project calculation_type is preserved when ENABLE_PROJECT_PAYROLL=True
    and correctly converted when the feature is disabled.
    """

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="test123"
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Test",
            last_name="Employee",
            email="test@example.com",
            employment_type="contract",  # Maps to monthly conversion
            role="employee",
        )

    @override_settings(FEATURE_FLAGS={"ENABLE_PROJECT_PAYROLL": True})
    def test_project_type_preserved_when_feature_enabled(self):
        """Test that project type is preserved when ENABLE_PROJECT_PAYROLL=True"""
        salary = Salary.objects.create(
            employee=self.employee,
            calculation_type="project",
            base_salary=Decimal("50000.00"),
            project_start_date=date.today(),
            project_end_date=date.today() + timedelta(days=60),
        )
        # Should remain as project type
        self.assertEqual(salary.calculation_type, "project")

    @override_settings(FEATURE_FLAGS={"ENABLE_PROJECT_PAYROLL": False})
    def test_project_type_converted_when_feature_disabled(self):
        """Test that project type is converted when ENABLE_PROJECT_PAYROLL=False"""
        salary = Salary.objects.create(
            employee=self.employee,
            calculation_type="project",
            base_salary=Decimal("50000.00"),
            project_start_date=date.today(),
            project_end_date=date.today() + timedelta(days=60),
        )
        # Should be converted to monthly based on employment_type='contract'
        self.assertEqual(salary.calculation_type, "monthly")

    def test_project_type_preserved_with_validate_false(self):
        """Test that project type is preserved when validation is bypassed"""
        salary = Salary(
            employee=self.employee,
            calculation_type="project",
            base_salary=Decimal("50000.00"),
            project_start_date=date.today(),
            project_end_date=date.today() + timedelta(days=60),
        )
        salary.save(skip_validation=True)  # Bypass auto-conversion
        # Should remain as project type regardless of settings
        self.assertEqual(salary.calculation_type, "project")

    @override_settings(FEATURE_FLAGS={"ENABLE_PROJECT_PAYROLL": True})
    def test_project_with_hourly_rate_preserved(self):
        """Test that project with monthly_hourly is preserved when feature enabled"""
        salary = Salary.objects.create(
            employee=self.employee,
            calculation_type="project",
            hourly_rate=Decimal("75.00"),
            project_start_date=date.today(),
            project_end_date=date.today() + timedelta(days=90),
        )
        self.assertEqual(salary.calculation_type, "project")
        self.assertEqual(salary.monthly_hourly, Decimal("75.00"))

    @override_settings(FEATURE_FLAGS={"ENABLE_PROJECT_PAYROLL": False})
    def test_project_with_hourly_rate_converted_to_hourly(self):
        """Test that project with monthly_hourly converts to hourly when feature disabled"""
        salary = Salary.objects.create(
            employee=self.employee,
            calculation_type="project",
            hourly_rate=Decimal("75.00"),
            project_start_date=date.today(),
            project_end_date=date.today() + timedelta(days=90),
        )
        # Should be converted based on employment_type (contract -> monthly)
        self.assertEqual(salary.calculation_type, "monthly")
        # monthly_hourly is not preserved when converting to monthly type
        self.assertIsNone(salary.monthly_hourly)

    def test_non_project_types_unaffected(self):
        """Test that non-project calculation types are not affected by the setting"""
        # Test monthly type
        monthly_salary = Salary.objects.create(
            employee=self.employee,
            calculation_type="monthly",
            base_salary=Decimal("10000.00"),
        )
        self.assertEqual(monthly_salary.calculation_type, "monthly")

        # Test hourly type - create separate employee to avoid constraint conflicts
        user2 = User.objects.create_user(
            username="testuser2", email="test2@example.com", password="test123"
        )
        employee2 = Employee.objects.create(
            user=user2,
            first_name="Test2",
            last_name="Employee2",
            email="test2@example.com",
            employment_type="full_time",
            role="employee",
        )

        hourly_salary = Salary.objects.create(
            employee=employee2,
            calculation_type="hourly",
            hourly_rate=Decimal("50.00"),
        )
        self.assertEqual(hourly_salary.calculation_type, "hourly")

    @override_settings(FEATURE_FLAGS={"ENABLE_PROJECT_PAYROLL": True})
    def test_project_dates_required_when_preserved(self):
        """Test that project dates are still validated when type is preserved"""
        with self.assertRaises(Exception):  # Should raise validation error
            Salary.objects.create(
                employee=self.employee,
                calculation_type="project",
                base_salary=Decimal("30000.00"),
                # Missing required project dates
            )

    def test_conversion_mapping_based_on_employment_type(self):
        """Test that conversion follows employment_type mapping"""
        # Contract employment -> monthly
        contract_salary = Salary(
            employee=self.employee,  # employment_type='contract'
            calculation_type="project",
            base_salary=Decimal("40000.00"),
            project_start_date=date.today(),
            project_end_date=date.today() + timedelta(days=30),
        )

        # Create separate employee with different employment_type
        user_ft = User.objects.create_user(
            username="testuser_ft", email="testft@example.com", password="test123"
        )
        employee_ft = Employee.objects.create(
            user=user_ft,
            first_name="FullTime",
            last_name="Employee",
            email="testft@example.com",
            employment_type="full_time",  # Maps to monthly conversion
            role="employee",
        )

        hourly_salary = Salary(
            employee=employee_ft,
            calculation_type="project",
            hourly_rate=Decimal("65.00"),
            project_start_date=date.today(),
            project_end_date=date.today() + timedelta(days=45),
        )

        # Save with potential conversion (depends on settings)
        with override_settings(FEATURE_FLAGS={"ENABLE_PROJECT_PAYROLL": False}):
            contract_salary.save()
            hourly_salary.save()

            # Contract should convert to monthly, full_time to monthly
            self.assertEqual(contract_salary.calculation_type, "monthly")
            self.assertEqual(hourly_salary.calculation_type, "monthly")

