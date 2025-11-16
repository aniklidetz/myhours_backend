"""
Tests for payroll data contracts.

These tests ensure that all payroll calculation strategies return data
that conforms to the standardized contracts.
"""

from decimal import Decimal

import pytest

from payroll.services.contracts import (
    CalculationContext,
    PayrollBreakdown,
    PayrollMetadata,
    PayrollResult,
    ValidationError,
    create_empty_payroll_result,
    validate_payroll_result,
)
from payroll.tests.helpers import (
    ISRAELI_DAILY_NORM_HOURS,
    MONTHLY_NORM_HOURS,
    NIGHT_NORM_HOURS,
)


class TestPayrollResultValidation:
    """Test payroll result contract validation"""

    def test_valid_payroll_result_passes_validation(self):
        """Test that a valid payroll result passes validation"""
        valid_result = {
            "total_salary": Decimal("5000.00"),
            "total_hours": Decimal("160.0"),
            "regular_hours": Decimal("144.0"),
            "overtime_hours": Decimal("16.0"),
            "holiday_hours": Decimal("0.0"),
            "shabbat_hours": Decimal("0.0"),
            "breakdown": {
                "regular_hours": 144.0,
                "regular_rate": 30.0,
                "base_regular_pay": 4320.0,
            },
            "metadata": {
                "calculation_strategy": "enhanced",
                "employee_type": "hourly",
                "currency": "ILS",
            },
        }

        # Should not raise exception
        validated = validate_payroll_result(valid_result)
        assert isinstance(validated["total_salary"], Decimal)
        assert validated["total_salary"] == Decimal("5000.00")

    def test_missing_required_fields_raises_validation_error(self):
        """Test that missing required fields raise ValidationError"""
        invalid_result = {
            "total_salary": Decimal("5000.00"),
            # Missing other required fields
        }

        with pytest.raises(ValidationError) as exc_info:
            validate_payroll_result(invalid_result)

        assert "Missing required fields" in str(exc_info.value)

    def test_invalid_types_raise_validation_error(self):
        """Test that invalid field types raise ValidationError"""
        invalid_result = {
            "total_salary": "not-a-number",  # Invalid type
            "total_hours": Decimal("160.0"),
            "regular_hours": Decimal("144.0"),
            "overtime_hours": Decimal("16.0"),
            "holiday_hours": Decimal("0.0"),
            "shabbat_hours": Decimal("0.0"),
            "breakdown": {},
            "metadata": {},
        }

        with pytest.raises(ValidationError) as exc_info:
            validate_payroll_result(invalid_result)

        assert "Cannot convert total_salary to Decimal" in str(exc_info.value)

    def test_non_decimal_numbers_converted_to_decimal(self):
        """Test that numeric values are converted to Decimal"""
        result_with_floats = {
            "total_salary": 5000.50,  # float
            "total_hours": "160.0",  # string
            "regular_hours": 144,  # int
            "overtime_hours": Decimal("16.0"),  # already Decimal
            "holiday_hours": Decimal("0.0"),
            "shabbat_hours": Decimal("0.0"),
            "breakdown": {},
            "metadata": {},
        }

        validated = validate_payroll_result(result_with_floats)

        # All should be Decimal now
        assert isinstance(validated["total_salary"], Decimal)
        assert isinstance(validated["total_hours"], Decimal)
        assert isinstance(validated["regular_hours"], Decimal)
        assert validated["total_salary"] == Decimal("5000.50")

    def test_invalid_breakdown_type_raises_error(self):
        """Test that non-dict breakdown raises ValidationError"""
        invalid_result = {
            "total_salary": Decimal("5000.00"),
            "total_hours": Decimal("160.0"),
            "regular_hours": Decimal("144.0"),
            "overtime_hours": Decimal("16.0"),
            "holiday_hours": Decimal("0.0"),
            "shabbat_hours": Decimal("0.0"),
            "breakdown": "not-a-dict",  # Invalid type
            "metadata": {},
        }

        with pytest.raises(ValidationError) as exc_info:
            validate_payroll_result(invalid_result)

        assert "breakdown must be a dictionary" in str(exc_info.value)


class TestEmptyPayrollResult:
    """Test creation of empty payroll results"""

    def test_create_empty_payroll_result(self):
        """Test creating empty payroll result"""
        empty_result = create_empty_payroll_result(
            employee_id=123, strategy="test_strategy", currency="USD"
        )

        # Should be valid PayrollResult
        validated = validate_payroll_result(empty_result)

        # All monetary/hour values should be zero
        assert validated["total_salary"] == Decimal("0")
        assert validated["total_hours"] == Decimal("0")
        assert validated["regular_hours"] == Decimal("0")

        # Metadata should be populated
        assert validated["metadata"]["calculation_strategy"] == "test_strategy"
        assert validated["metadata"]["currency"] == "USD"
        assert "No calculation data available" in validated["metadata"]["warnings"]


class TestCalculationContext:
    """Test calculation context creation and validation"""

    def test_minimal_calculation_context(self):
        """Test creating minimal calculation context"""
        context = CalculationContext(
            employee_id=123,
            year=2025,
            month=1,
            user_id=456,
            strategy_hint=None,
            force_recalculate=False,
            fast_mode=False,
            include_breakdown=True,
            include_daily_details=False,
        )

        assert context["employee_id"] == 123
        assert context["year"] == 2025
        assert context["month"] == 1
        assert context["user_id"] == 456

    def test_context_with_all_options(self):
        """Test creating context with all optional fields"""
        context = CalculationContext(
            employee_id=123,
            year=2025,
            month=1,
            user_id=456,
            strategy_hint="enhanced",
            force_recalculate=True,
            fast_mode=True,
            include_breakdown=True,
            include_daily_details=True,
        )

        assert context["strategy_hint"] == "enhanced"
        assert context["force_recalculate"] is True
        assert context["fast_mode"] is True


class TestContractCompliance:
    """Test that example results from different strategies comply with contracts"""

    def test_legacy_style_result_compliance(self):
        """Test that legacy-style results can be made compliant"""
        # Simulate what legacy service might return
        legacy_style_result = {
            "total_salary": 4500.00,
            "total_hours": 144.0,
            "regular_hours": 144.0,
            "overtime_hours": 0.0,
            "holiday_hours": 0.0,
            "shabbat_hours": 0.0,
            "breakdown": {
                "proportional_monthly": 4500.00,
                "total_bonuses_monthly": 0.0,
            },
            "metadata": {
                "calculation_strategy": "legacy",
                "employee_type": "monthly",
                "currency": "ILS",
            },
        }

        # Should pass validation (with type conversion)
        validated = validate_payroll_result(legacy_style_result)
        assert isinstance(validated["total_salary"], Decimal)

    def test_enhanced_style_result_compliance(self):
        """Test that enhanced-style results comply with contract"""
        enhanced_result = {
            "total_salary": Decimal("6240.50"),
            "total_hours": Decimal("176.0"),
            "regular_hours": Decimal("144.0"),
            "overtime_hours": Decimal("32.0"),
            "holiday_hours": ISRAELI_DAILY_NORM_HOURS,
            "shabbat_hours": Decimal("16.0"),
            "breakdown": {
                "base_regular_pay": 4320.0,
                "overtime_125_pay": 1080.0,
                "overtime_150_pay": 720.0,
                "holiday_pay": 360.0,
                "sabbath_pay": 720.0,
            },
            "metadata": {
                "calculation_strategy": "enhanced",
                "employee_type": "hourly",
                "currency": "ILS",
                "has_cache": True,
                "cache_source": "monthly_summary",
            },
        }

        # Should pass validation
        validated = validate_payroll_result(enhanced_result)
        assert validated["metadata"]["has_cache"] is True
