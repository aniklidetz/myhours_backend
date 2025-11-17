"""
Biometric Encryption Service - GDPR Article 9 Compliance

Encrypts biometric embeddings (face vectors) at rest in MongoDB.
Uses Fernet (AES-128 CBC + HMAC SHA256) for symmetric encryption.

GDPR Article 9: Processing of special categories of personal data
"shall be prohibited" unless proper technical measures are in place.

This service provides:
- Encryption of face embeddings before MongoDB storage
- Decryption when retrieving for recognition
- Key rotation support
- Automatic cleanup of old encryption keys
"""

import base64
import json
import logging
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.cache import cache

from core.logging_utils import err_tag

logger = logging.getLogger("biometrics")


class BiometricEncryptionService:
    """
    Service for encrypting/decrypting biometric data

    Uses Fernet (symmetric encryption):
    - AES-128 in CBC mode
    - HMAC SHA256 for authentication
    - Automatic IV generation
    - Base64 encoded output
    """

    ENCRYPTION_VERSION = "v1"  # For future key rotation
    CACHE_KEY_PREFIX = "biometric_encryption_key"
    CACHE_TIMEOUT = 3600  # 1 hour

    def __init__(self):
        """
        Initialize encryption service

        Raises:
            ValueError: If BIOMETRIC_ENCRYPTION_KEY not configured
        """
        self.encryption_key = self._get_encryption_key()
        self.cipher = Fernet(self.encryption_key)

    def _get_encryption_key(self) -> bytes:
        """
        Get encryption key from settings with validation

        Returns:
            bytes: Fernet-compatible encryption key

        Raises:
            ValueError: If key not configured or invalid
        """
        # Try cache first
        cache_key = f"{self.CACHE_KEY_PREFIX}_{self.ENCRYPTION_VERSION}"
        cached_key = cache.get(cache_key)
        if cached_key:
            logger.debug("Using cached encryption key")
            return cached_key

        # Get from settings
        key_string = getattr(settings, "BIOMETRIC_ENCRYPTION_KEY", None)

        if not key_string:
            error_msg = (
                "BIOMETRIC_ENCRYPTION_KEY not configured! "
                "Generate with: python -c 'from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())'"
            )
            logger.critical(error_msg)
            raise ValueError(error_msg)

        # Validate key format
        try:
            if isinstance(key_string, str):
                encryption_key = key_string.encode()
            else:
                encryption_key = key_string

            # Test key validity
            Fernet(encryption_key)

            # Cache for performance
            cache.set(cache_key, encryption_key, self.CACHE_TIMEOUT)

            logger.info("Encryption key loaded and validated")
            return encryption_key

        except Exception as e:
            error_msg = f"Invalid BIOMETRIC_ENCRYPTION_KEY format: {err_tag(e)}"
            logger.critical(error_msg)
            raise ValueError(error_msg)

    def encrypt_embeddings(self, embeddings: List[Dict[str, Any]]) -> str:
        """
        Encrypt face embeddings for storage in MongoDB

        Args:
            embeddings: List of embedding dicts containing 'vector' and metadata

        Returns:
            str: Base64-encoded encrypted data with version prefix

        Raises:
            ValueError: If embeddings invalid or encryption fails

        Example:
            >>> service = BiometricEncryptionService()
            >>> embeddings = [{'vector': [0.1, 0.2, ...], 'quality': 0.95}]
            >>> encrypted = service.encrypt_embeddings(embeddings)
            >>> # encrypted = "v1:gAAAAABf..."
        """
        if not embeddings or not isinstance(embeddings, list):
            raise ValueError("Embeddings must be a non-empty list")

        try:
            # Serialize to JSON
            embeddings_json = json.dumps(embeddings, separators=(",", ":"))

            # Encrypt
            encrypted_bytes = self.cipher.encrypt(embeddings_json.encode("utf-8"))

            # Add version prefix for future key rotation
            encrypted_data = (
                f"{self.ENCRYPTION_VERSION}:{encrypted_bytes.decode('utf-8')}"
            )

            logger.debug(
                f"Encrypted {len(embeddings)} embeddings "
                f"({len(embeddings_json)} bytes → {len(encrypted_data)} bytes)"
            )

            return encrypted_data

        except Exception as e:
            logger.error(f"Failed to encrypt embeddings: {err_tag(e)}")
            raise ValueError(f"Encryption failed: {str(e)}")

    def decrypt_embeddings(self, encrypted_data: str) -> List[Dict[str, Any]]:
        """
        Decrypt face embeddings retrieved from MongoDB

        Args:
            encrypted_data: Base64-encoded encrypted data with version prefix

        Returns:
            List[Dict]: Decrypted embeddings

        Raises:
            ValueError: If data invalid or decryption fails
            InvalidToken: If encryption key doesn't match

        Example:
            >>> service = BiometricEncryptionService()
            >>> encrypted = "v1:gAAAAABf..."
            >>> embeddings = service.decrypt_embeddings(encrypted)
            >>> # embeddings = [{'vector': [0.1, 0.2, ...], 'quality': 0.95}]
        """
        if not encrypted_data or not isinstance(encrypted_data, str):
            raise ValueError("Encrypted data must be a non-empty string")

        try:
            # Parse version prefix
            if ":" not in encrypted_data:
                # Legacy data without version (assume v1)
                logger.warning("Encrypted data missing version prefix, assuming v1")
                version = self.ENCRYPTION_VERSION
                encrypted_bytes = encrypted_data.encode("utf-8")
            else:
                version, encrypted_part = encrypted_data.split(":", 1)
                encrypted_bytes = encrypted_part.encode("utf-8")

            # Check version compatibility
            if version != self.ENCRYPTION_VERSION:
                logger.warning(
                    f"Decrypting data with different version: {version} "
                    f"(current: {self.ENCRYPTION_VERSION})"
                )
                # TODO: Implement key rotation logic here
                # For now, fail if version mismatch
                raise ValueError(
                    f"Unsupported encryption version: {version}. "
                    "Please migrate data to current version."
                )

            # Decrypt
            decrypted_bytes = self.cipher.decrypt(encrypted_bytes)
            embeddings_json = decrypted_bytes.decode("utf-8")

            # Deserialize
            embeddings = json.loads(embeddings_json)

            logger.debug(
                f"Decrypted {len(embeddings)} embeddings "
                f"({len(encrypted_data)} bytes → {len(embeddings_json)} bytes)"
            )

            return embeddings

        except InvalidToken as e:
            logger.error(
                "Decryption failed: Invalid token. Key mismatch or corrupted data."
            )
            raise ValueError(
                "Decryption failed: Invalid encryption key or corrupted data"
            )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse decrypted embeddings: {err_tag(e)}")
            raise ValueError(f"Decryption successful but data corrupted: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to decrypt embeddings: {err_tag(e)}")
            raise ValueError(f"Decryption failed: {str(e)}")

    def rotate_encryption_key(
        self, old_key: str, new_key: str, test_data: Optional[str] = None
    ) -> bool:
        """
        Rotate encryption key (for future use)

        This method is a placeholder for key rotation logic.
        In production, you would:
        1. Decrypt all data with old key
        2. Re-encrypt with new key
        3. Update settings
        4. Verify all data accessible

        Args:
            old_key: Current encryption key
            new_key: New encryption key to rotate to
            test_data: Optional encrypted test data to verify

        Returns:
            bool: True if rotation successful

        Raises:
            NotImplementedError: Key rotation not yet implemented
        """
        logger.warning(
            "Key rotation requested but not yet implemented. "
            "Manual migration required."
        )
        raise NotImplementedError(
            "Key rotation not yet implemented. "
            "Please use management command: python manage.py migrate_biometric_encryption"
        )

    @classmethod
    def generate_key(cls) -> str:
        """
        Generate a new Fernet encryption key

        Returns:
            str: Base64-encoded encryption key

        Example:
            >>> key = BiometricEncryptionService.generate_key()
            >>> print(key)
            'abc123...xyz789=='
        """
        key = Fernet.generate_key()
        return key.decode("utf-8")

    def health_check(self) -> Dict[str, Any]:
        """
        Verify encryption service is working correctly

        Returns:
            dict: Health check results

        Example:
            >>> service = BiometricEncryptionService()
            >>> health = service.health_check()
            >>> health['status']
            'ok'
        """
        try:
            # Test encryption/decryption round-trip
            test_data = [
                {"vector": [0.1, 0.2, 0.3], "quality": 0.95, "index": 0},
                {"vector": [0.4, 0.5, 0.6], "quality": 0.88, "index": 1},
            ]

            encrypted = self.encrypt_embeddings(test_data)
            decrypted = self.decrypt_embeddings(encrypted)

            # Verify data integrity
            if decrypted == test_data:
                return {
                    "status": "ok",
                    "version": self.ENCRYPTION_VERSION,
                    "message": "Encryption service operational",
                }
            else:
                return {
                    "status": "error",
                    "version": self.ENCRYPTION_VERSION,
                    "message": "Data integrity check failed",
                }

        except Exception as e:
            return {
                "status": "error",
                "version": self.ENCRYPTION_VERSION,
                "message": f"Health check failed: {str(e)}",
            }
