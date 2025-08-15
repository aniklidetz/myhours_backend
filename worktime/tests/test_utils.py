"""
Tests for worktime utilities - calc_overtime function.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.test import TestCase

from worktime.utils import EIGHT_HOURS_6, calc_overtime


class CalcOvertimeTest(TestCase):
    """Tests for calc_overtime function"""

    def test_calc_overtime_no_overtime(self):
        """Test calc_overtime with hours equal to threshold"""
        result = calc_overtime(Decimal("8.6"))
        self.assertEqual(result, Decimal("0.00"))

    def test_calc_overtime_below_threshold(self):
        """Test calc_overtime with hours below overtime threshold"""
        result = calc_overtime(Decimal("7.5"))
        self.assertEqual(result, Decimal("0.00"))

    def test_calc_overtime_with_overtime(self):
        """Test calc_overtime with hours above threshold"""
        result = calc_overtime(Decimal("10.0"))
        expected = Decimal("1.40")  # 10.0 - 8.6 = 1.4
        self.assertEqual(result, expected)

    def test_calc_overtime_minimal_overtime(self):
        """Test calc_overtime with minimal overtime (8.61 hours)"""
        result = calc_overtime(Decimal("8.61"))
        expected = Decimal("0.01")  # 8.61 - 8.6 = 0.01
        self.assertEqual(result, expected)

    def test_calc_overtime_large_overtime(self):
        """Test calc_overtime with large overtime hours"""
        result = calc_overtime(Decimal("15.25"))
        expected = Decimal("6.65")  # 15.25 - 8.6 = 6.65
        self.assertEqual(result, expected)

    def test_calc_overtime_with_float_input(self):
        """Test calc_overtime converts float to Decimal"""
        result = calc_overtime(9.5)
        expected = Decimal("0.90")  # 9.5 - 8.6 = 0.9
        self.assertEqual(result, expected)

    def test_calc_overtime_with_int_input(self):
        """Test calc_overtime converts int to Decimal"""
        result = calc_overtime(12)
        expected = Decimal("3.40")  # 12 - 8.6 = 3.4
        self.assertEqual(result, expected)

    def test_calc_overtime_with_string_input(self):
        """Test calc_overtime converts string to Decimal"""
        result = calc_overtime("10.75")
        expected = Decimal("2.15")  # 10.75 - 8.6 = 2.15
        self.assertEqual(result, expected)

    def test_calc_overtime_zero_hours(self):
        """Test calc_overtime with zero hours"""
        result = calc_overtime(Decimal("0.0"))
        self.assertEqual(result, Decimal("0.00"))

    def test_calc_overtime_rounding_behavior(self):
        """Test calc_overtime rounding to 2 decimal places"""
        # Test value that requires rounding
        result = calc_overtime(Decimal("9.126"))  # 9.126 - 8.6 = 0.526
        expected = Decimal("0.53")  # Rounded to 2 decimals (ROUND_HALF_UP)
        self.assertEqual(result, expected)

    def test_calc_overtime_precise_decimal(self):
        """Test calc_overtime with high precision input"""
        result = calc_overtime(Decimal("8.615"))
        expected = Decimal("0.02")  # 8.615 - 8.6 = 0.015, rounded up to 0.02
        self.assertEqual(result, expected)

    def test_calc_overtime_edge_case_8_59(self):
        """Test calc_overtime just below threshold (8.59)"""
        result = calc_overtime(Decimal("8.59"))
        self.assertEqual(result, Decimal("0.00"))

    def test_eight_hours_6_constant(self):
        """Test the EIGHT_HOURS_6 constant value"""
        self.assertEqual(EIGHT_HOURS_6, Decimal("8.6"))
        self.assertIsInstance(EIGHT_HOURS_6, Decimal)

    def test_calc_overtime_return_type(self):
        """Test that calc_overtime always returns Decimal"""
        result = calc_overtime(9.5)
        self.assertIsInstance(result, Decimal)

    def test_calc_overtime_decimal_precision(self):
        """Test that result always has 2 decimal places"""
        test_cases = [
            (Decimal("8.0"), "0.00"),   # No overtime
            (Decimal("9.0"), "0.40"),   # Overtime = 0.40
            (Decimal("10.5"), "1.90"),  # Overtime = 1.90
        ]
        
        for hours, expected_str in test_cases:
            result = calc_overtime(hours)
            # Check that result has exactly 2 decimal places when converted to string
            result_str = str(result)
            self.assertIn('.', result_str)
            decimal_part = result_str.split('.')[1]
            self.assertEqual(len(decimal_part), 2, f"Result {result} should have 2 decimal places")