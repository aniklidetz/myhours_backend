"""
Tests for payroll/serializers.py to improve coverage from 41% to 70%+

Tests the SalarySerializer and CompensatoryDaySerializer covering:
- Field validations (validate_base_salary, validate_hourly_rate, etc.)
- Cross-field validation (validate method)
- Feature flag validation for project payroll
- SerializerMethodField calculations
- Error handling scenarios
"""

from datetime import date, timedelta
from decimal import Decimal
from payroll.tests.helpers import MONTHLY_NORM_HOURS, ISRAELI_DAILY_NORM_HOURS, NIGHT_NORM_HOURS, MONTHLY_NORM_HOURS
from unittest.mock import Mock, patch

from rest_framework import serializers

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from payroll.models import CompensatoryDay, Salary
from payroll.serializers import CompensatoryDaySerializer, SalarySerializer
from users.models import Employee


class SalarySerializerTest(TestCase):
    """Test cases for SalarySerializer"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@test.com", password="pass123"
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Test",
            last_name="Employee",
            email="test@test.com",
            employment_type="full_time",
            role="employee",
        )

        self.valid_salary_data = {
            "employee": self.employee.id,
            "calculation_type": "monthly",
            "base_salary": Decimal("10000.00"),
            "currency": "ILS",
        }


class SalarySerializerFieldValidationTest(SalarySerializerTest):
    """Test individual field validations"""

    def test_validate_base_salary_valid(self):
        """Test valid base salary validation"""
        serializer = SalarySerializer()

        # Test valid salaries
        self.assertEqual(
            serializer.validate_base_salary(Decimal("5300")), Decimal("5300")
        )  # Minimum wage
        self.assertEqual(
            serializer.validate_base_salary(Decimal("10000")), Decimal("10000")
        )  # Above minimum
        self.assertEqual(
            serializer.validate_base_salary(Decimal("0")), Decimal("0")
        )  # Zero is valid

    def test_validate_base_salary_negative(self):
        """Test negative base salary validation"""
        serializer = SalarySerializer()

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate_base_salary(Decimal("-1000"))

        self.assertIn("Base salary cannot be negative", str(cm.exception))

    def test_validate_base_salary_below_minimum(self):
        """Test base salary below minimum wage"""
        serializer = SalarySerializer()

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate_base_salary(Decimal("5000"))  # Below 5300 minimum

        error_message = str(cm.exception)
        self.assertIn("Base salary cannot be less than minimum wage", error_message)
        self.assertIn("5300 ILS", error_message)

    def test_validate_hourly_rate_valid(self):
        """Test valid hourly rate validation"""
        serializer = SalarySerializer()

        # Test valid rates
        self.assertEqual(
            serializer.validate_hourly_rate(Decimal("28.49")), Decimal("28.49")
        )  # Minimum
        self.assertEqual(
            serializer.validate_hourly_rate(Decimal("50.00")), Decimal("50.00")
        )  # Above minimum
        self.assertEqual(
            serializer.validate_hourly_rate(Decimal("0")), Decimal("0")
        )  # Zero is valid

    def test_validate_hourly_rate_negative(self):
        """Test negative hourly rate validation"""
        serializer = SalarySerializer()

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate_hourly_rate(Decimal("-10"))

        self.assertIn("Hourly rate cannot be negative", str(cm.exception))

    def test_validate_hourly_rate_below_minimum(self):
        """Test hourly rate below minimum wage"""
        serializer = SalarySerializer()

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate_hourly_rate(Decimal("20.00"))  # Below 28.49 minimum

        error_message = str(cm.exception)
        self.assertIn("Hourly rate cannot be less than minimum wage", error_message)
        self.assertIn("28.49 ILS/hour", error_message)

    @override_settings(FEATURE_FLAGS={"ENABLE_PROJECT_PAYROLL": True})
    def test_validate_calculation_type_project_enabled(self):
        """Test project calculation type when feature is enabled"""
        serializer = SalarySerializer()

        # Should accept project type when enabled
        self.assertEqual(serializer.validate_calculation_type("project"), "project")
        self.assertEqual(serializer.validate_calculation_type("hourly"), "hourly")
        self.assertEqual(serializer.validate_calculation_type("monthly"), "monthly")

    @override_settings(FEATURE_FLAGS={"ENABLE_PROJECT_PAYROLL": False})
    def test_validate_calculation_type_project_disabled(self):
        """Test project calculation type when feature is disabled"""
        serializer = SalarySerializer()

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate_calculation_type("project")

        error_message = str(cm.exception)
        self.assertIn(
            "Project payroll calculation is currently disabled", error_message
        )
        self.assertIn("Contact administrator", error_message)

    @override_settings(FEATURE_FLAGS={})  # No project payroll flag
    def test_validate_calculation_type_project_not_configured(self):
        """Test project calculation type when feature flag not configured"""
        serializer = SalarySerializer()

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate_calculation_type("project")

        self.assertIn(
            "Project payroll calculation is currently disabled", str(cm.exception)
        )


class SalarySerializerCrossFieldValidationTest(SalarySerializerTest):
    """Test cross-field validation (validate method)"""

    @override_settings(FEATURE_FLAGS={"ENABLE_PROJECT_PAYROLL": True})
    def test_validate_project_with_valid_dates(self):
        """Test project validation with valid start/end dates"""
        serializer = SalarySerializer()

        attrs = {
            "calculation_type": "project",
            "project_start_date": date.today(),
            "project_end_date": date.today() + timedelta(days=30),
        }

        # Should not raise exception
        result = serializer.validate(attrs)
        self.assertEqual(result, attrs)

    @override_settings(FEATURE_FLAGS={"ENABLE_PROJECT_PAYROLL": True})
    def test_validate_project_missing_start_date(self):
        """Test project validation with missing start date"""
        serializer = SalarySerializer()

        attrs = {
            "calculation_type": "project",
            "project_start_date": None,
            "project_end_date": date.today() + timedelta(days=30),
        }

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate(attrs)

        self.assertIn("Project start and end dates are required", str(cm.exception))

    @override_settings(FEATURE_FLAGS={"ENABLE_PROJECT_PAYROLL": True})
    def test_validate_project_missing_end_date(self):
        """Test project validation with missing end date"""
        serializer = SalarySerializer()

        attrs = {
            "calculation_type": "project",
            "project_start_date": date.today(),
            "project_end_date": None,
        }

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate(attrs)

        self.assertIn("Project start and end dates are required", str(cm.exception))

    @override_settings(FEATURE_FLAGS={"ENABLE_PROJECT_PAYROLL": True})
    def test_validate_project_end_before_start(self):
        """Test project validation when end date is before start date"""
        serializer = SalarySerializer()

        start_date = date.today()
        attrs = {
            "calculation_type": "project",
            "project_start_date": start_date,
            "project_end_date": start_date - timedelta(days=1),  # End before start
        }

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate(attrs)

        error_dict = cm.exception.detail
        self.assertIn("project_end_date", error_dict)
        self.assertIn(
            "Project end date must be after start date",
            str(error_dict["project_end_date"]),
        )

    @override_settings(FEATURE_FLAGS={"ENABLE_PROJECT_PAYROLL": True})
    def test_validate_project_same_start_end_date(self):
        """Test project validation when start and end dates are the same"""
        serializer = SalarySerializer()

        same_date = date.today()
        attrs = {
            "calculation_type": "project",
            "project_start_date": same_date,
            "project_end_date": same_date,  # Same as start
        }

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate(attrs)

        error_dict = cm.exception.detail
        self.assertIn("project_end_date", error_dict)
        self.assertIn(
            "Project end date must be after start date",
            str(error_dict["project_end_date"]),
        )

    @override_settings(FEATURE_FLAGS={"ENABLE_PROJECT_PAYROLL": False})
    def test_validate_project_disabled_in_validate_method(self):
        """Test project validation when feature is disabled (via validate method)"""
        serializer = SalarySerializer()

        attrs = {
            "calculation_type": "project",
            "project_start_date": date.today(),
            "project_end_date": date.today() + timedelta(days=30),
        }

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate(attrs)

        error_dict = cm.exception.detail
        self.assertIn("calculation_type", error_dict)
        self.assertIn(
            "Project payroll calculation is currently disabled",
            str(error_dict["calculation_type"]),
        )

    def test_validate_non_project_types(self):
        """Test validation for non-project calculation types"""
        serializer = SalarySerializer()

        # Monthly should pass without project dates
        attrs = {"calculation_type": "monthly"}
        result = serializer.validate(attrs)
        self.assertEqual(result, attrs)

        # Hourly should pass without project dates
        attrs = {"calculation_type": "hourly"}
        result = serializer.validate(attrs)
        self.assertEqual(result, attrs)


class SalarySerializerMethodFieldTest(SalarySerializerTest):
    """Test SerializerMethodField calculations"""

    # NOTE: Removed test_get_calculated_salary_success and test_get_calculated_salary_exception
    # These tests were checking the old calculate_monthly_salary method which has been removed.
    # Payroll calculation functionality is now thoroughly tested in PayrollService tests.
    pass


class SalarySerializerIntegrationTest(SalarySerializerTest):
    """Integration tests for SalarySerializer"""

    def test_serializer_with_valid_monthly_data(self):
        """Test serializer with valid monthly salary data"""
        serializer = SalarySerializer(data=self.valid_salary_data)

        self.assertTrue(serializer.is_valid())

        salary = serializer.save()
        self.assertEqual(salary.employee, self.employee)
        self.assertEqual(salary.calculation_type, "monthly")
        self.assertEqual(salary.base_salary, Decimal("10000.00"))

    def test_serializer_with_valid_hourly_data(self):
        """Test serializer with valid hourly salary data"""
        hourly_data = {
            "employee": self.employee.id,
            "calculation_type": "hourly",
            "hourly_rate": Decimal("50.00"),
            "currency": "ILS",
        }

        serializer = SalarySerializer(data=hourly_data)

        self.assertTrue(serializer.is_valid())

        salary = serializer.save()
        self.assertEqual(salary.calculation_type, "hourly")
        self.assertEqual(salary.monthly_hourly, Decimal("50.00"))

    @override_settings(FEATURE_FLAGS={"ENABLE_PROJECT_PAYROLL": True})
    def test_serializer_with_valid_project_data(self):
        """Test serializer with valid project salary data"""
        project_data = {
            "employee": self.employee.id,
            "calculation_type": "project",
            "base_salary": Decimal("50000.00"),
            "project_start_date": date.today().isoformat(),
            "project_end_date": (date.today() + timedelta(days=90)).isoformat(),
            "currency": "ILS",
        }

        serializer = SalarySerializer(data=project_data)

        self.assertTrue(serializer.is_valid())

        salary = serializer.save()
        self.assertEqual(salary.calculation_type, "project")
        self.assertEqual(salary.base_salary, Decimal("50000.00"))
        self.assertIsNotNone(salary.project_start_date)
        self.assertIsNotNone(salary.project_end_date)

    def test_serializer_with_invalid_base_salary(self):
        """Test serializer with invalid base salary"""
        invalid_data = self.valid_salary_data.copy()
        invalid_data["base_salary"] = Decimal("1000.00")  # Below minimum

        serializer = SalarySerializer(data=invalid_data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("base_salary", serializer.errors)
        self.assertIn("minimum wage", str(serializer.errors["base_salary"]))

    def test_serializer_read_only_fields(self):
        """Test that read-only fields are properly handled"""
        data_with_readonly = self.valid_salary_data.copy()
        data_with_readonly.update(
            {
                "id": 999,  # Should be ignored
                "created_at": "2023-01-01T00:00:00Z",  # Should be ignored
                "updated_at": "2023-01-01T00:00:00Z",  # Should be ignored
            }
        )

        serializer = SalarySerializer(data=data_with_readonly)

        self.assertTrue(serializer.is_valid())

        salary = serializer.save()
        # ID should be auto-generated, not 999
        self.assertNotEqual(salary.id, 999)


class CompensatoryDaySerializerTest(TestCase):
    """Test cases for CompensatoryDaySerializer"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@test.com", password="pass123"
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Test",
            last_name="Employee",
            email="test@test.com",
            employment_type="full_time",
            role="employee",
        )

        self.comp_day = CompensatoryDay.objects.create(
            employee=self.employee,
            date_earned=date.today() - timedelta(days=7),
            reason="shabbat",
        )


class CompensatoryDaySerializerMethodFieldTest(CompensatoryDaySerializerTest):
    """Test SerializerMethodField for CompensatoryDaySerializer"""

    def test_get_is_used_false(self):
        """Test get_is_used when compensatory day is not used"""
        serializer = CompensatoryDaySerializer()

        # date_used is None (not used)
        result = serializer.get_is_used(self.comp_day)

        self.assertFalse(result)

    def test_get_is_used_true(self):
        """Test get_is_used when compensatory day is used"""
        # Set date_used to mark as used
        self.comp_day.date_used = date.today()
        self.comp_day.save()

        serializer = CompensatoryDaySerializer()

        result = serializer.get_is_used(self.comp_day)

        self.assertTrue(result)


class CompensatoryDaySerializerValidationTest(CompensatoryDaySerializerTest):
    """Test validation for CompensatoryDaySerializer"""

    def test_validate_date_used_past_date(self):
        """Test validation of date_used with past date (valid)"""
        serializer = CompensatoryDaySerializer()

        past_date = date.today() - timedelta(days=1)
        result = serializer.validate_date_used(past_date)

        self.assertEqual(result, past_date)

    def test_validate_date_used_today(self):
        """Test validation of date_used with today's date (valid)"""
        serializer = CompensatoryDaySerializer()

        today = date.today()
        result = serializer.validate_date_used(today)

        self.assertEqual(result, today)

    def test_validate_date_used_future_date(self):
        """Test validation of date_used with future date (invalid)"""
        serializer = CompensatoryDaySerializer()

        future_date = date.today() + timedelta(days=1)

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate_date_used(future_date)

        self.assertIn("Used date cannot be in the future", str(cm.exception))

    def test_validate_date_used_none(self):
        """Test validation of date_used with None value (valid)"""
        serializer = CompensatoryDaySerializer()

        # None should pass validation (not used yet)
        result = serializer.validate_date_used(None)

        self.assertIsNone(result)


class CompensatoryDaySerializerIntegrationTest(CompensatoryDaySerializerTest):
    """Integration tests for CompensatoryDaySerializer"""

    def test_serializer_with_valid_data(self):
        """Test serializer with valid compensatory day data"""
        data = {
            "employee": self.employee.id,
            "date_earned": date.today().isoformat(),
            "reason": "shabbat",
        }

        serializer = CompensatoryDaySerializer(data=data)

        self.assertTrue(serializer.is_valid())

        comp_day = serializer.save()
        self.assertEqual(comp_day.employee, self.employee)
        self.assertEqual(comp_day.reason, "shabbat")
        self.assertIsNone(comp_day.date_used)  # Not used yet

    def test_serializer_with_date_used(self):
        """Test serializer with used compensatory day"""
        data = {
            "employee": self.employee.id,
            "date_earned": (date.today() - timedelta(days=7)).isoformat(),
            "reason": "holiday",
            "date_used": (
                date.today() - timedelta(days=1)
            ).isoformat(),  # Used yesterday
        }

        serializer = CompensatoryDaySerializer(data=data)

        self.assertTrue(serializer.is_valid())

        comp_day = serializer.save()
        self.assertEqual(comp_day.reason, "holiday")
        self.assertIsNotNone(comp_day.date_used)

    def test_serializer_with_future_date_used(self):
        """Test serializer with invalid future date_used"""
        data = {
            "employee": self.employee.id,
            "date_earned": date.today().isoformat(),
            "reason": "shabbat",
            "date_used": (date.today() + timedelta(days=1)).isoformat(),  # Future date
        }

        serializer = CompensatoryDaySerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("date_used", serializer.errors)
        self.assertIn(
            "Used date cannot be in the future", str(serializer.errors["date_used"])
        )

    def test_serializer_read_only_fields(self):
        """Test that read-only fields are properly handled"""
        data = {
            "employee": self.employee.id,
            "date_earned": date.today().isoformat(),
            "reason": "shabbat",
            "id": 999,  # Should be ignored
            "created_at": "2023-01-01T00:00:00Z",  # Should be ignored
        }

        serializer = CompensatoryDaySerializer(data=data)

        self.assertTrue(serializer.is_valid())

        comp_day = serializer.save()
        # ID should be auto-generated, not 999
        self.assertNotEqual(comp_day.id, 999)

    def test_serialized_output_includes_calculated_fields(self):
        """Test that serialized output includes calculated fields"""
        # Use existing comp_day that's not used
        serializer = CompensatoryDaySerializer(self.comp_day)
        data = serializer.data

        # Should include employee_name (ReadOnlyField)
        self.assertIn("employee_name", data)
        self.assertEqual(data["employee_name"], self.employee.get_full_name())

        # Should include is_used (SerializerMethodField)
        self.assertIn("is_used", data)
        self.assertFalse(data["is_used"])  # Not used yet

    def test_serialized_output_used_compensatory_day(self):
        """Test serialized output for used compensatory day"""
        # Mark as used
        self.comp_day.date_used = date.today() - timedelta(days=1)
        self.comp_day.save()

        serializer = CompensatoryDaySerializer(self.comp_day)
        data = serializer.data

        # Should show as used
        self.assertTrue(data["is_used"])
        self.assertIsNotNone(data["date_used"])

