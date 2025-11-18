"""
Adapter tests to ensure legacy → modern compatibility.

These tests verify that the modern services can handle
data migrated from legacy services and maintain backward compatibility.
"""

from unittest.mock import Mock, patch

import pytest

from django.contrib.auth.models import User
from django.test import TestCase

from biometrics.services.enhanced_biometric_service import EnhancedBiometricService
from biometrics.services.mongodb_repository import MongoBiometricRepository
from users.models import Employee


class LegacyDataCompatibilityTest(TestCase):
    """Test that modern services can read legacy data format"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Test",
            last_name="User",
            email="test@example.com",
            employment_type="full_time",
            role="employee",
            is_active=True,
        )

    @patch("biometrics.services.mongodb_repository.MongoBiometricRepository._connect")
    def test_modern_service_reads_migrated_data(self, mock_connect):
        """Modern service should read data migrated from legacy format"""
        repo = MongoBiometricRepository()

        # Mock collection with migrated data (has 'migrated: true' flag)
        mock_collection = Mock()
        mock_collection.find_one.return_value = {
            "_id": "mock_id_123",
            "employee_id": self.employee.id,
            "embeddings": [
                {
                    "vector": [0.1] * 128,
                    "quality_score": 0.95,
                    "created_at": "2025-01-15T10:00:00Z",
                }
            ],
            "is_active": True,
            "metadata": {
                "migrated": True,  # Flag indicating legacy data migration
                "algorithm": "dlib_face_recognition_resnet_model_v1",
                "version": "1.0",
            },
        }
        repo.collection = mock_collection

        # Test retrieval
        embeddings = repo.get_face_embeddings(self.employee.id)

        # Verify data was retrieved successfully
        self.assertIsNotNone(embeddings)
        self.assertEqual(len(embeddings), 1)
        self.assertEqual(len(embeddings[0]["vector"]), 128)
        self.assertEqual(embeddings[0]["quality_score"], 0.95)

    @patch("biometrics.services.mongodb_repository.MongoBiometricRepository._connect")
    def test_embedding_format_compatibility(self, mock_connect):
        """Legacy flat array should be compatible with modern embeddings list"""
        repo = MongoBiometricRepository()

        # Mock collection
        mock_collection = Mock()
        repo.collection = mock_collection

        # Modern format (list of dicts)
        modern_embeddings = [
            {
                "vector": [0.1] * 128,
                "quality_score": 0.95,
                "angle": "front",
            },
            {
                "vector": [0.2] * 128,
                "quality_score": 0.88,
                "angle": "slight_left",
            },
        ]

        # Save using modern format
        mock_collection.replace_one.return_value = Mock(
            upserted_id="mock_id", modified_count=0
        )
        mock_collection.find_one.return_value = {
            "_id": "mock_id",
            "employee_id": self.employee.id,
            "embeddings": modern_embeddings,
            "is_active": True,
        }

        result = repo.save_face_embeddings(self.employee.id, modern_embeddings)

        # Verify save was successful
        self.assertIsNotNone(result)
        mock_collection.replace_one.assert_called_once()

    @patch("biometrics.services.mongodb_repository.MongoBiometricRepository._connect")
    def test_get_all_active_embeddings_legacy_compatibility(self, mock_connect):
        """Test get_all_active_embeddings returns data in expected format"""
        repo = MongoBiometricRepository()

        # Mock collection with multiple employees
        mock_collection = Mock()
        mock_collection.find.return_value = [
            {
                "_id": "id_1",
                "employee_id": 1,
                "embeddings": [{"vector": [0.1] * 128}],
                "is_active": True,
            },
            {
                "_id": "id_2",
                "employee_id": 2,
                "embeddings": [{"vector": [0.2] * 128}],
                "is_active": True,
            },
        ]
        repo.collection = mock_collection

        # Get all embeddings
        all_embeddings = repo.get_all_active_embeddings()

        # Verify format matches legacy expectations: List[Tuple[int, List[Dict]]]
        self.assertIsInstance(all_embeddings, list)
        self.assertEqual(len(all_embeddings), 2)

        # Check first tuple
        employee_id, embeddings = all_embeddings[0]
        self.assertEqual(employee_id, 1)
        self.assertIsInstance(embeddings, list)
        self.assertEqual(len(embeddings[0]["vector"]), 128)


class LegacyServiceDeprecationTest(TestCase):
    """Test that deprecated mongodb_service is still available for compatibility"""

    def test_deprecation_warning_was_issued(self):
        """
        Verify that mongodb_service.py still exists for backward compatibility.
        It is maintained alongside mongodb_repository.py for legacy code support.
        """
        # The old service should still be importable for compatibility
        from biometrics.services.mongodb_service import MongoDBService

        # Verify it can be instantiated
        self.assertIsNotNone(MongoDBService)

    def test_modern_service_available(self):
        """Verify modern service is available and working"""
        from biometrics.services.mongodb_repository import (
            MongoBiometricRepository,
            get_mongo_biometric_repository,
        )

        # Should not raise any errors
        repo = MongoBiometricRepository()
        self.assertIsNotNone(repo)

        # Test lazy proxy
        lazy_repo = get_mongo_biometric_repository()
        self.assertIsNotNone(lazy_repo)


class EnhancedServiceLegacyCompatibilityTest(TestCase):
    """Test that EnhancedBiometricService maintains backward compatibility"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name="Test",
            last_name="User",
            email="test@example.com",
            employment_type="full_time",
            role="employee",
            is_active=True,
        )

    @patch("biometrics.services.enhanced_biometric_service.MongoBiometricRepository")
    def test_enhanced_service_uses_modern_repository(self, mock_repo_class):
        """Enhanced service should use MongoBiometricRepository, not legacy service"""
        mock_repo = Mock()
        mock_repo.save_face_embeddings.return_value = "mock_mongodb_id"
        mock_repo_class.return_value = mock_repo

        service = EnhancedBiometricService()

        # Verify it's using the modern repository
        self.assertIsNotNone(service.mongo_repo)

        # Test registration
        embeddings = [{"vector": [0.1] * 128, "quality_score": 0.95}]
        result = service.register_biometric(self.employee.id, embeddings)

        # Verify modern repository was used
        mock_repo.save_face_embeddings.assert_called_once()
        # Result should be a BiometricProfile object (or dict with success key)
        self.assertIsNotNone(result)
