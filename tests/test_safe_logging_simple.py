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
        # Regular phone numbers
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
        # Check that hashes are identical for identical IDs
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
        """Test secure location logging"""
        # Regular coordinates
        self.assertEqual(safe_log_location(32.05, 34.78), "Office Area")
        self.assertEqual(safe_log_location(None, None), "Location Unknown")
        self.assertEqual(safe_log_location(32.05, None), "Location Unknown")


class PIIDetectionTest(unittest.TestCase):
    """Tests for detecting potential PII leaks"""

    def test_email_detection_patterns(self):
        """Test email detection in strings"""
        import re

        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"

        # Should be detected
        test_strings = [
            "User admin@example.com logged in",
            "Contact: john.doe@company.org for details",
            "Email sent to test+tag@domain.co.uk",
        ]

        for test_str in test_strings:
            with self.subTest(test_str=test_str):
                self.assertTrue(re.search(email_pattern, test_str))

        # Should NOT be detected
        safe_strings = [
            "User a***@example.com logged in",
            "Contact details masked",
            "Email sent successfully",
        ]

        for test_str in safe_strings:
            with self.subTest(test_str=test_str):
                self.assertFalse(re.search(email_pattern, test_str))

    def test_coordinates_detection_patterns(self):
        """Test precise coordinates detection"""
        import re

        coord_pattern = r"\b\d{1,3}\.\d{4,}\b"  # Precise coordinates with 4+ digits

        # Should be detected (precise coordinates)
        risky_strings = [
            "Location: 32.050936, 34.781800",
            "GPS: lat=40.7589, lng=-73.9851",
        ]

        for test_str in risky_strings:
            with self.subTest(test_str=test_str):
                self.assertTrue(re.search(coord_pattern, test_str))

        # Should NOT be detected (generalized data)
        safe_strings = ["Location: Office Area", "GPS: City Area", "Distance: 1.02m"]

        for test_str in safe_strings:
            with self.subTest(test_str=test_str):
                self.assertFalse(re.search(coord_pattern, test_str))


class SecurityComplianceTest(unittest.TestCase):
    """Tests for security compliance requirements"""

    def test_email_masking_gdpr_compliance(self):
        """Test GDPR compliance when masking emails"""
        test_emails = ["user@example.com", "long.email.address@very-long-domain.co.uk"]

        for email in test_emails:
            masked = mask_email(email)

            # Email should be masked
            self.assertNotEqual(email, masked)

            # Most of the username should be hidden
            username = email.split("@")[0]
            if len(username) > 1:
                # Check that middle part of username is hidden
                self.assertNotIn(username[1:], masked)

            # Domain should remain for technical purposes
            original_domain = email.split("@")[1]
            self.assertIn(original_domain, masked)

        # Special case for short emails
        short_masked = mask_email("a@b.com")
        self.assertEqual(short_masked, "*@b.com")

    def test_coordinates_privacy_protection(self):
        """Test privacy protection when masking coordinates"""
        # Precise office coordinates
        office_lat, office_lng = 32.050936, 34.781800

        # After masking should only show general area
        masked_location = mask_coordinates(office_lat, office_lng)

        # Precise coordinates should NOT be present in result
        self.assertNotIn(str(office_lat), masked_location)
        self.assertNotIn(str(office_lng), masked_location)

        # Result should be generalized
        self.assertIn("Area", masked_location)


if __name__ == "__main__":
    print("Running safe logging tests...")
    print("=" * 50)

    # Run all tests
    unittest.main(verbosity=2)
