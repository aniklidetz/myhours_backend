"""
Tests for safe logging utilities
"""

import unittest

from django.contrib.auth.models import User
from django.test import TestCase

from core.logging_utils import (
    hash_user_id,
    mask_coordinates,
    mask_email,
    mask_name,
    mask_phone,
    safe_log_employee,
    safe_log_location,
    safe_log_user,
)
from core.models import Employee


class SafeLoggingUtilsTest(TestCase):
    """Tests for PII data masking functions"""

    def test_mask_email(self):
        """Test email address masking"""
        # Regular emails
        self.assertEqual(mask_email("admin@example.com"), "a***@example.com")
        self.assertEqual(mask_email("john.doe@company.org"), "j***@company.org")
        self.assertEqual(mask_email("a@test.com"), "*@test.com")

        # Edge cases
        self.assertEqual(mask_email(""), "[invalid_email]")
        self.assertEqual(mask_email("invalid-email"), "[invalid_email]")
        self.assertEqual(mask_email("@domain.com"), "*@domain.com")

    def test_mask_phone(self):
        """Test phone number masking"""
        # Regular numbers
        self.assertEqual(mask_phone("+972501234567"), "***4567")
        self.assertEqual(mask_phone("1234567890"), "***7890")
        self.assertEqual(mask_phone("+1-234-567-8901"), "***8901")

        # Edge cases
        self.assertEqual(mask_phone(""), "[no_phone]")
        self.assertEqual(mask_phone("123"), "***")
        self.assertEqual(mask_phone("abc"), "***")

    def test_mask_coordinates(self):
        """Test GPS coordinates masking"""
        # Office area (Tel Aviv)
        self.assertEqual(mask_coordinates(32.05, 34.78), "Office Area")
        self.assertEqual(mask_coordinates(32.051, 34.781), "Office Area")

        # City area
        self.assertEqual(mask_coordinates(32.5, 34.5), "City Area")
        self.assertEqual(mask_coordinates(31.8, 34.2), "City Area")

        # Remote location
        self.assertEqual(mask_coordinates(40.7, -74.0), "Remote Location")
        self.assertEqual(mask_coordinates(51.5, -0.1), "Remote Location")

    def test_mask_name(self):
        """Test full name masking"""
        # Regular names
        self.assertEqual(mask_name("John Doe"), "J.D.")
        self.assertEqual(mask_name("Sarah Jane Smith"), "S.J.")
        self.assertEqual(mask_name("Admin"), "A.")

        # Edge cases
        self.assertEqual(mask_name(""), "[no_name]")
        self.assertEqual(mask_name("   "), "[no_name]")

    def test_hash_user_id(self):
        """Test user ID hashing"""
        # Check that hashes are identical for same IDs
        hash1 = hash_user_id(123)
        hash2 = hash_user_id(123)
        self.assertEqual(hash1, hash2)

        # Check that hashes are different for different IDs
        hash3 = hash_user_id(456)
        self.assertNotEqual(hash1, hash3)

        # Check format
        self.assertTrue(hash1.startswith("usr_"))
        self.assertEqual(len(hash1), 12)  # usr_ + 8 characters

        # Edge cases
        self.assertEqual(hash_user_id(None), "[no_id]")
        self.assertEqual(hash_user_id(""), "[no_id]")

    def test_safe_log_location(self):
        """Test safe location logging"""
        # Regular coordinates
        self.assertEqual(safe_log_location(32.05, 34.78), "Office Area")
        self.assertEqual(safe_log_location(None, None), "Location Unknown")
        self.assertEqual(safe_log_location(32.05, None), "Location Unknown")


class SafeLoggingIntegrationTest(TestCase):
    """Integration tests with Django models"""

    def setUp(self):
        """Prepare test data"""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            first_name="Test",
            last_name="User",
        )

        # Note: Employee.save() will sync employee.email to user.email
        # So we use the same email for both to avoid confusion in tests
        self.employee = Employee.objects.create(
            user=self.user,
            email="test@example.com",  # Same as user email
            first_name="John",
            last_name="Employee",
            phone="+972501234567",
            role="employee",
        )

    def test_safe_log_user(self):
        """Тест безопасного логирования пользователя"""
        safe_data = safe_log_user(self.user, "test_action")

        # Проверяем, что данные маскированы
        self.assertEqual(safe_data["action"], "test_action")
        self.assertEqual(safe_data["email_masked"], "t***@example.com")
        self.assertTrue(safe_data["user_hash"].startswith("usr_"))

        # Проверяем, что оригинальные данные НЕ присутствуют
        self.assertNotIn("email", safe_data)
        self.assertNotIn("first_name", safe_data)
        self.assertNotIn("last_name", safe_data)

    def test_safe_log_employee(self):
        """Тест безопасного логирования сотрудника"""
        safe_data = safe_log_employee(self.employee, "employee_action")

        # Проверяем маскирование
        self.assertEqual(safe_data["action"], "employee_action")
        self.assertEqual(safe_data["email_masked"], "t***@example.com")
        self.assertEqual(safe_data["name_initials"], "J.E.")
        self.assertEqual(safe_data["phone_masked"], "***4567")
        self.assertTrue(safe_data["employee_hash"].startswith("usr_"))

        # Проверяем отсутствие оригинальных данных
        self.assertNotIn("email", safe_data)
        self.assertNotIn("first_name", safe_data)
        self.assertNotIn("last_name", safe_data)
        self.assertNotIn("phone", safe_data)

    def test_safe_log_none_user(self):
        """Тест с пустыми пользователями"""
        safe_data = safe_log_user(None, "anonymous_action")
        self.assertEqual(safe_data["user"], "anonymous")

        safe_data = safe_log_employee(None, "no_employee")
        self.assertEqual(safe_data["employee"], "none")


class PIIDetectionTest(TestCase):
    """Тесты обнаружения потенциальных утечек PII"""

    def test_email_detection_patterns(self):
        """Тест обнаружения email в строках"""
        import re

        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"

        # Должны обнаруживаться
        test_strings = [
            "User admin@example.com logged in",
            "Contact: john.doe@company.org for details",
            "Email sent to test+tag@domain.co.uk",
        ]

        for test_str in test_strings:
            with self.subTest(test_str=test_str):
                self.assertTrue(re.search(email_pattern, test_str))

        # НЕ должны обнаруживаться
        safe_strings = [
            "User a***@example.com logged in",
            "Contact details masked",
            "Email sent successfully",
        ]

        for test_str in safe_strings:
            with self.subTest(test_str=test_str):
                self.assertFalse(re.search(email_pattern, test_str))

    def test_coordinates_detection_patterns(self):
        """Тест обнаружения точных координат"""
        import re

        coord_pattern = r"\b\d{1,3}\.\d{4,}\b"  # Точные координаты с 4+ знаками

        # Должны обнаруживаться (точные координаты)
        risky_strings = [
            "Location: 32.050936, 34.781800",
            "GPS: lat=40.7589, lng=-73.9851",
        ]

        for test_str in risky_strings:
            with self.subTest(test_str=test_str):
                self.assertTrue(re.search(coord_pattern, test_str))

        # НЕ должны обнаруживаться (обобщённые данные)
        safe_strings = ["Location: Office Area", "GPS: City Area", "Distance: 1.02m"]

        for test_str in safe_strings:
            with self.subTest(test_str=test_str):
                self.assertFalse(re.search(coord_pattern, test_str))


if __name__ == "__main__":
    unittest.main()
