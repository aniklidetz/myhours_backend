"""
Test utilities for payroll module using unittest.TestCase approach.

Provides common utilities, mixins, and re-exports from conftest.py
to support migration from pytest fixtures to unittest setUp patterns.
"""

from decimal import Decimal
from typing import Optional, Dict, Any

# Re-export from conftest.py to maintain compatibility during migration
from payroll.tests.conftest import (
    make_context,
    ISRAELI_DAILY_NORM_HOURS,
    NIGHT_NORM_HOURS, 
    MONTHLY_NORM_HOURS,
    OVERTIME_RATES,
    assert_result_structure,
    legacy_to_new_result_mapping,
)


class PayrollTestMixin:
    """
    Mixin for Django TestCase classes to provide common payroll testing utilities.
    
    Provides:
    - self.payroll_service: Ready-to-use PayrollService instance
    - self.constants: Dictionary of Israeli labor law constants
    - Common assertion helpers for payroll calculations
    
    Usage:
        class MyPayrollTest(PayrollTestMixin, TestCase):
            def test_calculation(self):
                context = make_context(self.employee, 2024, 1)
                result = self.payroll_service.calculate(context)
                self.assert_salary_structure(result)
    """
    
    def setUp(self):
        super().setUp()
        # Lazy import to avoid Django configuration issues
        from payroll.services.payroll_service import PayrollService
        self.payroll_service = PayrollService()
        self.constants = {
            "daily_norm_hours": ISRAELI_DAILY_NORM_HOURS,
            "night_norm_hours": NIGHT_NORM_HOURS,
            "monthly_norm_hours": MONTHLY_NORM_HOURS,
            "overtime_rates": OVERTIME_RATES,
        }
    
    def assert_salary_structure(self, result: Dict[str, Any], expected_keys: Optional[set] = None):
        """Assert that payroll calculation result has expected structure."""
        assert_result_structure(result, expected_keys)
    
    def assert_decimal_field(self, result: Dict[str, Any], field_name: str, expected_value: Decimal):
        """Assert that a result field matches expected Decimal value."""
        self.assertIn(field_name, result, f"Field {field_name} missing from result")
        actual = result[field_name]
        self.assertIsInstance(actual, Decimal, f"{field_name} should be Decimal, got {type(actual)}")
        self.assertEqual(actual, expected_value, f"{field_name} value mismatch")
    
    def assert_overtime_calculation(self, result: Dict[str, Any], base_hours: Decimal, overtime_hours: Decimal):
        """Assert overtime calculation follows Israeli labor law."""
        total_hours = result.get('total_hours', Decimal('0'))
        expected_total = base_hours + overtime_hours
        self.assertEqual(total_hours, expected_total, "Total hours calculation incorrect")
        
        if overtime_hours > Decimal('0'):
            self.assertIn('breakdown', result, "Overtime breakdown missing")
            breakdown = result['breakdown']
            self.assertIsInstance(breakdown, dict, "Breakdown should be dictionary")


def create_test_context(employee, year: int, month: int, **kwargs):
    """
    Factory function to create CalculationContext for tests.
    
    Wrapper around make_context with explicit parameters for unittest usage.
    """
    return make_context(employee, year, month, **kwargs)


# Convenience constants for direct import
DAILY_NORM = ISRAELI_DAILY_NORM_HOURS
NIGHT_NORM = NIGHT_NORM_HOURS  
MONTHLY_NORM = MONTHLY_NORM_HOURS