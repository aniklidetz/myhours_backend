"""
Simplified tests for safe logging utilities (without database dependencies)
"""

import os
import sys
import unittest

# Add project path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logging_utils import (
    hash_user_id,
    mask_coordinates,
    mask_email,
    mask_name,
    mask_phone,
    safe_log_location,
)


class SafeLoggingUtilsTest(unittest.TestCase):
    """Тесты функций маскирования PII данных"""

    def test_mask_email(self):
        """Тест маскирования email адресов"""
        # Обычные email
        self.assertEqual(mask_email("admin@example.com"), "a***@example.com")
        self.assertEqual(mask_email("john.doe@company.org"), "j***@company.org")
        self.assertEqual(mask_email("a@test.com"), "*@test.com")

        # Граничные случаи
        self.assertEqual(mask_email(""), "[invalid_email]")
        self.assertEqual(mask_email("invalid-email"), "[invalid_email]")
        self.assertEqual(mask_email("@domain.com"), "*@domain.com")

    def test_mask_phone(self):
        """Тест маскирования номеров телефонов"""
        # Обычные номера
        self.assertEqual(mask_phone("+972501234567"), "***4567")
        self.assertEqual(mask_phone("1234567890"), "***7890")
        self.assertEqual(mask_phone("+1-234-567-8901"), "***8901")

        # Граничные случаи
        self.assertEqual(mask_phone(""), "[no_phone]")
        self.assertEqual(mask_phone("123"), "***")
        self.assertEqual(mask_phone("abc"), "***")

    def test_mask_coordinates(self):
        """Тест маскирования GPS координат"""
        # Офисная зона (Тель-Авив)
        self.assertEqual(mask_coordinates(32.05, 34.78), "Office Area")
        self.assertEqual(mask_coordinates(32.051, 34.781), "Office Area")

        # Городская зона
        self.assertEqual(mask_coordinates(32.5, 34.5), "City Area")
        self.assertEqual(mask_coordinates(31.8, 34.2), "City Area")

        # Удалённое местоположение
        self.assertEqual(mask_coordinates(40.7, -74.0), "Remote Location")
        self.assertEqual(mask_coordinates(51.5, -0.1), "Remote Location")

    def test_mask_name(self):
        """Тест маскирования полных имён"""
        # Обычные имена
        self.assertEqual(mask_name("John Doe"), "J.D.")
        self.assertEqual(mask_name("Sarah Jane Smith"), "S.J.")
        self.assertEqual(mask_name("Admin"), "A.")

        # Граничные случаи
        self.assertEqual(mask_name(""), "[no_name]")
        self.assertEqual(mask_name("   "), "[no_name]")

    def test_hash_user_id(self):
        """Тест хэширования user ID"""
        # Проверяем, что хэши одинаковы для одинаковых ID
        hash1 = hash_user_id(123)
        hash2 = hash_user_id(123)
        self.assertEqual(hash1, hash2)

        # Проверяем, что хэши разные для разных ID
        hash3 = hash_user_id(456)
        self.assertNotEqual(hash1, hash3)

        # Проверяем формат
        self.assertTrue(hash1.startswith("usr_"))
        self.assertEqual(len(hash1), 12)  # usr_ + 8 символов

        # Граничные случаи
        self.assertEqual(hash_user_id(None), "[no_id]")
        self.assertEqual(hash_user_id(""), "[no_id]")

    def test_safe_log_location(self):
        """Тест безопасного логирования местоположения"""
        # Обычные координаты
        self.assertEqual(safe_log_location(32.05, 34.78), "Office Area")
        self.assertEqual(safe_log_location(None, None), "Location Unknown")
        self.assertEqual(safe_log_location(32.05, None), "Location Unknown")


class PIIDetectionTest(unittest.TestCase):
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


class SecurityComplianceTest(unittest.TestCase):
    """Тесты на соответствие требованиям безопасности"""

    def test_email_masking_gdpr_compliance(self):
        """Проверка соответствия GDPR при маскировании email"""
        test_emails = ["user@example.com", "long.email.address@very-long-domain.co.uk"]

        for email in test_emails:
            masked = mask_email(email)

            # Email должен быть маскирован
            self.assertNotEqual(email, masked)

            # Большая часть username должна быть скрыта
            username = email.split("@")[0]
            if len(username) > 1:
                # Проверяем, что средняя часть username скрыта
                self.assertNotIn(username[1:], masked)

            # Домен должен остаться для технических целей
            original_domain = email.split("@")[1]
            self.assertIn(original_domain, masked)

        # Специальный случай для коротких email
        short_masked = mask_email("a@b.com")
        self.assertEqual(short_masked, "*@b.com")

    def test_coordinates_privacy_protection(self):
        """Проверка защиты приватности при маскировании координат"""
        # Точные координаты офиса
        office_lat, office_lng = 32.050936, 34.781800

        # После маскирования должна быть только общая зона
        masked_location = mask_coordinates(office_lat, office_lng)

        # Точные координаты НЕ должны присутствовать в результате
        self.assertNotIn(str(office_lat), masked_location)
        self.assertNotIn(str(office_lng), masked_location)

        # Результат должен быть обобщённым
        self.assertIn("Area", masked_location)


if __name__ == "__main__":
    print("🧪 Running safe logging tests...")
    print("=" * 50)

    # Run all tests
    unittest.main(verbosity=2)
