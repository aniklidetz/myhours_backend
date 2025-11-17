"""
Tests for BiometricEncryptionService - GDPR Article 9 Compliance
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings

from biometrics.services.encryption_service import BiometricEncryptionService


class BiometricEncryptionServiceTests(TestCase):
    """Test suite for biometric encryption service"""

    def setUp(self):
        """Set up test environment"""
        # Clear cache before each test
        cache.clear()

        # Generate a valid test key
        self.test_key = Fernet.generate_key().decode("utf-8")

    def tearDown(self):
        """Clean up after tests"""
        cache.clear()

    @override_settings(BIOMETRIC_ENCRYPTION_KEY=None)
    def test_initialization_without_key_raises_error(self):
        """Test that service raises error if key not configured"""
        with self.assertRaises(ValueError) as context:
            BiometricEncryptionService()

        self.assertIn("BIOMETRIC_ENCRYPTION_KEY not configured", str(context.exception))

    @override_settings(BIOMETRIC_ENCRYPTION_KEY="invalid_key")
    def test_initialization_with_invalid_key_raises_error(self):
        """Test that service raises error if key is invalid"""
        with self.assertRaises(ValueError) as context:
            BiometricEncryptionService()

        self.assertIn("Invalid BIOMETRIC_ENCRYPTION_KEY format", str(context.exception))

    def test_initialization_with_valid_key(self):
        """Test successful initialization with valid key"""
        with override_settings(BIOMETRIC_ENCRYPTION_KEY=self.test_key):
            service = BiometricEncryptionService()

            self.assertIsNotNone(service.cipher)
            self.assertEqual(service.ENCRYPTION_VERSION, "v1")

    def test_encrypt_embeddings_valid_data(self):
        """Test encryption of valid embeddings data"""
        with override_settings(BIOMETRIC_ENCRYPTION_KEY=self.test_key):
            service = BiometricEncryptionService()

            embeddings = [
                {"vector": [0.1, 0.2, 0.3], "quality": 0.95, "index": 0},
                {"vector": [0.4, 0.5, 0.6], "quality": 0.88, "index": 1},
            ]

            encrypted = service.encrypt_embeddings(embeddings)

            # Check format
            self.assertIsInstance(encrypted, str)
            self.assertTrue(encrypted.startswith("v1:"))

            # Check it's actually encrypted (not readable JSON)
            encrypted_part = encrypted.split(":", 1)[1]
            with self.assertRaises(json.JSONDecodeError):
                json.loads(encrypted_part)

    def test_encrypt_embeddings_empty_list_raises_error(self):
        """Test that encrypting empty list raises error"""
        with override_settings(BIOMETRIC_ENCRYPTION_KEY=self.test_key):
            service = BiometricEncryptionService()

            with self.assertRaises(ValueError) as context:
                service.encrypt_embeddings([])

            self.assertIn("must be a non-empty list", str(context.exception))

    def test_encrypt_embeddings_invalid_type_raises_error(self):
        """Test that encrypting non-list raises error"""
        with override_settings(BIOMETRIC_ENCRYPTION_KEY=self.test_key):
            service = BiometricEncryptionService()

            with self.assertRaises(ValueError) as context:
                service.encrypt_embeddings("not a list")

            self.assertIn("must be a non-empty list", str(context.exception))

    def test_decrypt_embeddings_valid_data(self):
        """Test decryption of valid encrypted data"""
        with override_settings(BIOMETRIC_ENCRYPTION_KEY=self.test_key):
            service = BiometricEncryptionService()

            original_data = [
                {"vector": [0.1, 0.2, 0.3], "quality": 0.95, "index": 0},
                {"vector": [0.4, 0.5, 0.6], "quality": 0.88, "index": 1},
            ]

            encrypted = service.encrypt_embeddings(original_data)
            decrypted = service.decrypt_embeddings(encrypted)

            self.assertEqual(decrypted, original_data)

    def test_decrypt_embeddings_wrong_key_raises_error(self):
        """Test that decrypting with wrong key raises error"""
        # Encrypt with one key
        with override_settings(BIOMETRIC_ENCRYPTION_KEY=self.test_key):
            service = BiometricEncryptionService()
            embeddings = [{"vector": [0.1, 0.2, 0.3], "quality": 0.95}]
            encrypted = service.encrypt_embeddings(embeddings)

        # Try to decrypt with different key
        different_key = Fernet.generate_key().decode("utf-8")
        with override_settings(BIOMETRIC_ENCRYPTION_KEY=different_key):
            # Clear cache to ensure new key is used
            cache.clear()
            service = BiometricEncryptionService()

            with self.assertRaises(ValueError) as context:
                service.decrypt_embeddings(encrypted)

            self.assertIn("Decryption failed", str(context.exception))

    def test_decrypt_embeddings_corrupted_data_raises_error(self):
        """Test that decrypting corrupted data raises error"""
        with override_settings(BIOMETRIC_ENCRYPTION_KEY=self.test_key):
            service = BiometricEncryptionService()

            corrupted_data = "v1:corrupted_base64_data"

            with self.assertRaises(ValueError):
                service.decrypt_embeddings(corrupted_data)

    def test_decrypt_embeddings_legacy_format_without_version(self):
        """Test decryption of legacy data without version prefix"""
        with override_settings(BIOMETRIC_ENCRYPTION_KEY=self.test_key):
            service = BiometricEncryptionService()

            embeddings = [{"vector": [0.1, 0.2, 0.3], "quality": 0.95}]

            # Encrypt without version prefix (simulate legacy data)
            embeddings_json = json.dumps(embeddings, separators=(",", ":"))
            encrypted_bytes = service.cipher.encrypt(embeddings_json.encode("utf-8"))
            legacy_encrypted = encrypted_bytes.decode("utf-8")

            # Should still decrypt with warning
            decrypted = service.decrypt_embeddings(legacy_encrypted)
            self.assertEqual(decrypted, embeddings)

    def test_decrypt_embeddings_unsupported_version_raises_error(self):
        """Test that unsupported version raises error"""
        with override_settings(BIOMETRIC_ENCRYPTION_KEY=self.test_key):
            service = BiometricEncryptionService()

            # Create data with future version
            future_version_data = "v2:some_encrypted_data"

            with self.assertRaises(ValueError) as context:
                service.decrypt_embeddings(future_version_data)

            self.assertIn("Unsupported encryption version", str(context.exception))

    def test_encrypt_decrypt_round_trip_preserves_data(self):
        """Test that encryption/decryption round-trip preserves data"""
        with override_settings(BIOMETRIC_ENCRYPTION_KEY=self.test_key):
            service = BiometricEncryptionService()

            test_cases = [
                # Single embedding
                [{"vector": [0.1, 0.2, 0.3], "quality": 0.95, "index": 0}],
                # Multiple embeddings
                [
                    {"vector": [0.1] * 128, "quality": 0.99, "index": 0},
                    {"vector": [0.2] * 128, "quality": 0.85, "index": 1},
                    {"vector": [0.3] * 128, "quality": 0.92, "index": 2},
                ],
                # Complex metadata
                [
                    {
                        "vector": [0.1, 0.2, 0.3],
                        "quality": 0.95,
                        "metadata": {
                            "timestamp": "2025-01-12T10:00:00Z",
                            "camera": "front",
                        },
                    }
                ],
            ]

            for embeddings in test_cases:
                with self.subTest(embeddings=len(embeddings)):
                    encrypted = service.encrypt_embeddings(embeddings)
                    decrypted = service.decrypt_embeddings(encrypted)
                    self.assertEqual(decrypted, embeddings)

    def test_generate_key_returns_valid_key(self):
        """Test that generate_key returns valid Fernet key"""
        key = BiometricEncryptionService.generate_key()

        # Should be a string
        self.assertIsInstance(key, str)

        # Should be valid Fernet key
        try:
            Fernet(key.encode("utf-8"))
        except Exception:
            self.fail("Generated key is not a valid Fernet key")

    def test_health_check_success(self):
        """Test health check with valid configuration"""
        with override_settings(BIOMETRIC_ENCRYPTION_KEY=self.test_key):
            service = BiometricEncryptionService()

            health = service.health_check()

            self.assertEqual(health["status"], "ok")
            self.assertEqual(health["version"], "v1")
            self.assertIn("operational", health["message"])

    @override_settings(BIOMETRIC_ENCRYPTION_KEY=None)
    def test_health_check_failure_no_key(self):
        """Test health check fails without key"""
        # Should raise error during initialization
        with self.assertRaises(ValueError):
            BiometricEncryptionService()

    def test_encryption_key_caching(self):
        """Test that encryption key is cached for performance"""
        with override_settings(BIOMETRIC_ENCRYPTION_KEY=self.test_key):
            # Clear cache first
            cache.clear()

            # First initialization should cache the key
            service1 = BiometricEncryptionService()

            # Check cache has the key
            cache_key = f"{service1.CACHE_KEY_PREFIX}_{service1.ENCRYPTION_VERSION}"
            cached_key = cache.get(cache_key)
            self.assertIsNotNone(cached_key)

            # Second initialization should use cached key
            service2 = BiometricEncryptionService()

            # Both should work the same
            embeddings = [{"vector": [0.1, 0.2, 0.3], "quality": 0.95}]
            encrypted1 = service1.encrypt_embeddings(embeddings)
            encrypted2 = service2.encrypt_embeddings(embeddings)

            # Should be able to decrypt with either service
            decrypted1 = service1.decrypt_embeddings(encrypted2)
            decrypted2 = service2.decrypt_embeddings(encrypted1)

            self.assertEqual(decrypted1, embeddings)
            self.assertEqual(decrypted2, embeddings)

    def test_encrypted_data_is_different_each_time(self):
        """Test that encrypting same data produces different ciphertext (due to IV)"""
        with override_settings(BIOMETRIC_ENCRYPTION_KEY=self.test_key):
            service = BiometricEncryptionService()

            embeddings = [{"vector": [0.1, 0.2, 0.3], "quality": 0.95}]

            encrypted1 = service.encrypt_embeddings(embeddings)
            encrypted2 = service.encrypt_embeddings(embeddings)

            # Should be different (due to random IV)
            self.assertNotEqual(encrypted1, encrypted2)

            # But both should decrypt to same data
            decrypted1 = service.decrypt_embeddings(encrypted1)
            decrypted2 = service.decrypt_embeddings(encrypted2)

            self.assertEqual(decrypted1, embeddings)
            self.assertEqual(decrypted2, embeddings)

    def test_large_embedding_vectors(self):
        """Test encryption of large embedding vectors (realistic size)"""
        with override_settings(BIOMETRIC_ENCRYPTION_KEY=self.test_key):
            service = BiometricEncryptionService()

            # Realistic face embedding size (128 dimensions)
            large_embeddings = [
                {"vector": [0.123456] * 128, "quality": 0.95, "index": i}
                for i in range(5)
            ]

            encrypted = service.encrypt_embeddings(large_embeddings)
            decrypted = service.decrypt_embeddings(encrypted)

            self.assertEqual(decrypted, large_embeddings)

    def test_rotate_encryption_key_not_implemented(self):
        """Test that key rotation raises NotImplementedError"""
        with override_settings(BIOMETRIC_ENCRYPTION_KEY=self.test_key):
            service = BiometricEncryptionService()

            old_key = self.test_key
            new_key = Fernet.generate_key().decode("utf-8")

            with self.assertRaises(NotImplementedError) as context:
                service.rotate_encryption_key(old_key, new_key)

            self.assertIn("not yet implemented", str(context.exception))


@pytest.mark.django_db
class BiometricEncryptionIntegrationTests(TestCase):
    """Integration tests for encryption service with Django settings"""

    def test_settings_warning_when_key_not_configured(self):
        """Test that Django shows warning when key not configured"""
        # This is tested in settings.py - just verify the setting exists
        from django.conf import settings

        # In test environment, key should be None
        self.assertIsNone(settings.BIOMETRIC_ENCRYPTION_KEY)
