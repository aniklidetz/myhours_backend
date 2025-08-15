"""
Targeted tests for biometrics/services/mongodb_service.py
Focus on achieving 70%+ coverage for critical uncovered branches
"""

from unittest.mock import MagicMock, Mock, patch

import numpy as np
import pytest

from django.test import TestCase

from biometrics.services.mongodb_service import MongoDBService, get_mongodb_service


class MongoDBServiceConnectionTest(TestCase):
    """Test MongoDB connection error scenarios"""

    @patch("biometrics.services.mongodb_service.settings")
    def test_connection_settings_none(self, mock_settings):
        """Test connection when settings are None"""
        mock_settings.MONGO_CLIENT = None
        mock_settings.MONGO_DB = None

        service = MongoDBService()

        # Should handle None settings gracefully
        self.assertIsNone(service.client)
        self.assertIsNone(service.db)
        self.assertIsNone(service.collection)

    @patch("biometrics.services.mongodb_service.settings")
    @patch("biometrics.services.mongodb_service.logger")
    def test_connection_exception_handling(self, mock_logger, mock_settings):
        """Test connection exception handling"""
        # Mock database access to raise exception
        mock_db = Mock()
        mock_db.list_collection_names.side_effect = Exception("Connection failed")

        mock_settings.MONGO_CLIENT = MagicMock()
        mock_settings.MONGO_DB = mock_db

        with patch("sys.argv", ["manage.py", "runserver"]):  # Ensure logging happens
            service = MongoDBService()

        # Should handle exception gracefully
        self.assertIsNone(service.client)
        self.assertIsNone(service.db)
        self.assertIsNone(service.collection)

    @patch("biometrics.services.mongodb_service.settings")
    @patch("biometrics.services.mongodb_service.logger")
    def test_connection_with_faces_collection(self, mock_logger, mock_settings):
        """Test connection preferring 'faces' collection when it has data"""
        # Mock database with faces collection containing data
        mock_db = MagicMock()
        mock_db.list_collection_names.return_value = ["faces", "face_embeddings"]
        mock_faces_collection = MagicMock()
        mock_faces_collection.count_documents.return_value = 5  # Has data
        mock_db.__getitem__.return_value = mock_faces_collection

        mock_settings.MONGO_CLIENT = MagicMock()
        mock_settings.MONGO_DB = mock_db

        service = MongoDBService()

        # Should use faces collection
        self.assertEqual(service.collection, mock_faces_collection)
        # Check that the specific log message was called
        mock_logger.info.assert_any_call("Using existing 'faces' collection with data")

    @patch("biometrics.services.mongodb_service.settings")
    @patch("biometrics.services.mongodb_service.logger")
    def test_connection_with_empty_faces_collection(self, mock_logger, mock_settings):
        """Test connection using face_embeddings when faces collection is empty"""
        # Mock database with empty faces collection
        mock_db = MagicMock()
        mock_db.list_collection_names.return_value = ["faces", "face_embeddings"]
        mock_faces_collection = MagicMock()
        mock_faces_collection.count_documents.return_value = 0  # Empty
        mock_embeddings_collection = MagicMock()
        mock_db.__getitem__.side_effect = lambda name: (
            mock_faces_collection if name == "faces" else mock_embeddings_collection
        )

        mock_settings.MONGO_CLIENT = MagicMock()
        mock_settings.MONGO_DB = mock_db

        service = MongoDBService()

        # Should use face_embeddings collection
        self.assertEqual(service.collection, mock_embeddings_collection)
        # Check that the specific log message was called
        mock_logger.info.assert_any_call("Using 'face_embeddings' collection")

    @patch("biometrics.services.mongodb_service.settings")
    @patch("biometrics.services.mongodb_service.logger")
    def test_connection_error_logging_suppressed_in_test(
        self, mock_logger, mock_settings
    ):
        """Test that error logging is suppressed during tests"""
        mock_settings.MONGO_CLIENT = None
        mock_settings.MONGO_DB = None

        with patch("sys.argv", ["test_command", "test"]):
            service = MongoDBService()

        # Should not log error during tests
        mock_logger.error.assert_not_called()

    @patch("biometrics.services.mongodb_service.settings")
    @patch("biometrics.services.mongodb_service.logger")
    def test_connection_error_logging_in_production(self, mock_logger, mock_settings):
        """Test that error logging works in production"""
        mock_settings.MONGO_CLIENT = None
        mock_settings.MONGO_DB = None

        with patch("sys.argv", ["manage.py", "runserver"]):
            service = MongoDBService()

        # Should log error in production
        mock_logger.error.assert_called_with("MongoDB database not available")


class MongoDBServiceIndexTest(TestCase):
    """Test MongoDB index creation scenarios"""

    @patch("biometrics.services.mongodb_service.settings")
    @patch("biometrics.services.mongodb_service.logger")
    def test_create_indexes_success(self, mock_logger, mock_settings):
        """Test successful index creation"""
        mock_collection = MagicMock()
        mock_db = MagicMock()
        mock_db.list_collection_names.return_value = []
        mock_db.__getitem__.return_value = mock_collection

        mock_settings.MONGO_CLIENT = MagicMock()
        mock_settings.MONGO_DB = mock_db

        service = MongoDBService()
        service._create_indexes()

        # Should create all three indexes
        self.assertEqual(mock_collection.create_index.call_count, 3)
        mock_logger.info.assert_called_with("MongoDB indexes created successfully")

    @patch("biometrics.services.mongodb_service.settings")
    @patch("biometrics.services.mongodb_service.logger")
    def test_create_indexes_failure(self, mock_logger, mock_settings):
        """Test index creation failure handling"""
        mock_collection = MagicMock()
        mock_collection.create_index.side_effect = Exception("Index creation failed")
        mock_db = MagicMock()
        mock_db.list_collection_names.return_value = []
        mock_db.__getitem__.return_value = mock_collection

        mock_settings.MONGO_CLIENT = MagicMock()
        mock_settings.MONGO_DB = mock_db

        service = MongoDBService()
        service._create_indexes()

        # Should handle exception and log error
        mock_logger.error.assert_called_with(
            "Failed to create indexes: Index creation failed"
        )


class MongoDBServiceCRUDTest(TestCase):
    """Test CRUD operations and edge cases"""

    def setUp(self):
        """Set up mock service"""
        self.service = MongoDBService()
        self.mock_collection = MagicMock()
        self.service.collection = self.mock_collection

    def test_save_face_embeddings_collection_none(self):
        """Test save when collection is None"""
        self.service.collection = None

        result = self.service.save_face_embeddings(123, [])

        self.assertIsNone(result)

    @patch("biometrics.services.mongodb_service.logger")
    def test_save_face_embeddings_new_document_success(self, mock_logger):
        """Test saving new embeddings successfully"""
        # Mock no existing document
        self.mock_collection.find_one.return_value = None

        # Mock successful insert
        mock_result = MagicMock()
        mock_result.inserted_id = "507f1f77bcf86cd799439011"
        self.mock_collection.insert_one.return_value = mock_result

        # Mock verification
        self.mock_collection.find_one.side_effect = [None, {"employee_id": 123}]

        embeddings = [{"vector": [0.1, 0.2], "quality_score": 0.8}]
        result = self.service.save_face_embeddings(123, embeddings)

        self.assertEqual(result, "507f1f77bcf86cd799439011")
        mock_logger.info.assert_called()

    @patch("biometrics.services.mongodb_service.logger")
    def test_save_face_embeddings_update_existing(self, mock_logger):
        """Test updating existing embeddings"""
        # Mock existing document
        existing_doc = {"_id": "507f1f77bcf86cd799439011", "employee_id": 123}
        self.mock_collection.find_one.return_value = existing_doc

        # Mock successful update
        mock_result = MagicMock()
        mock_result.modified_count = 1
        self.mock_collection.update_one.return_value = mock_result

        embeddings = [{"vector": [0.1, 0.2], "quality_score": 0.8}]
        result = self.service.save_face_embeddings(123, embeddings)

        self.assertEqual(result, "507f1f77bcf86cd799439011")
        mock_logger.info.assert_called_with("Face embeddings updated")

    @patch("biometrics.services.mongodb_service.logger")
    def test_save_face_embeddings_update_failed(self, mock_logger):
        """Test when update returns 0 modified count"""
        # Mock existing document
        existing_doc = {"_id": "507f1f77bcf86cd799439011", "employee_id": 123}
        self.mock_collection.find_one.return_value = existing_doc

        # Mock failed update (no modifications)
        mock_result = MagicMock()
        mock_result.modified_count = 0
        self.mock_collection.update_one.return_value = mock_result

        embeddings = [{"vector": [0.1, 0.2], "quality_score": 0.8}]
        result = self.service.save_face_embeddings(123, embeddings)

        self.assertIsNone(result)

    @patch("biometrics.services.mongodb_service.logger")
    def test_save_face_embeddings_verification_failed(self, mock_logger):
        """Test when document verification fails after insert"""
        # Mock no existing document, then None for verification
        self.mock_collection.find_one.side_effect = [None, None]

        # Mock successful insert
        mock_result = MagicMock()
        mock_result.inserted_id = "507f1f77bcf86cd799439011"
        self.mock_collection.insert_one.return_value = mock_result

        embeddings = [{"vector": [0.1, 0.2], "quality_score": 0.8}]
        result = self.service.save_face_embeddings(123, embeddings)

        self.assertEqual(result, "507f1f77bcf86cd799439011")
        mock_logger.error.assert_called_with(
            "❌ Verification failed: Document not found after insert"
        )

    @patch("biometrics.services.mongodb_service.logger")
    def test_save_face_embeddings_exception(self, mock_logger):
        """Test exception handling during save"""
        self.mock_collection.find_one.side_effect = Exception("Database error")

        embeddings = [{"vector": [0.1, 0.2], "quality_score": 0.8}]
        result = self.service.save_face_embeddings(123, embeddings)

        self.assertIsNone(result)
        mock_logger.error.assert_called_with(
            "Failed to save embeddings: Database error"
        )

    def test_get_face_embeddings_collection_none(self):
        """Test get when collection is None"""
        self.service.collection = None

        result = self.service.get_face_embeddings(123)

        self.assertIsNone(result)

    def test_get_face_embeddings_legacy_format(self):
        """Test retrieving embeddings from legacy 'faces' collection"""
        # Mock legacy collection
        self.mock_collection.name = "faces"
        legacy_doc = {
            "employee_id": 123,
            "encodings": [[0.1, 0.2], [0.3, 0.4]],
            "created_at": "2023-01-01",
        }
        self.mock_collection.find_one.return_value = legacy_doc

        result = self.service.get_face_embeddings(123)

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["vector"], [0.1, 0.2])
        self.assertEqual(result[0]["quality_score"], 0.8)

    def test_get_face_embeddings_new_format(self):
        """Test retrieving embeddings from new format"""
        # Mock new collection format
        self.mock_collection.name = "face_embeddings"
        new_doc = {
            "employee_id": 123,
            "embeddings": [
                {"vector": [0.1, 0.2], "quality_score": 0.9, "angle": "front"}
            ],
        }
        self.mock_collection.find_one.return_value = new_doc

        result = self.service.get_face_embeddings(123)

        self.assertEqual(result, new_doc["embeddings"])

    def test_get_face_embeddings_not_found(self):
        """Test retrieving non-existent embeddings"""
        self.mock_collection.find_one.return_value = None

        result = self.service.get_face_embeddings(123)

        self.assertIsNone(result)

    @patch("biometrics.services.mongodb_service.logger")
    def test_get_face_embeddings_exception(self, mock_logger):
        """Test exception handling during get"""
        self.mock_collection.find_one.side_effect = Exception("Query error")

        result = self.service.get_face_embeddings(123)

        self.assertIsNone(result)
        mock_logger.error.assert_called_with(
            "Failed to retrieve embeddings: Query error"
        )


class MongoDBServiceActiveEmbeddingsTest(TestCase):
    """Test get_all_active_embeddings method"""

    def setUp(self):
        """Set up mock service"""
        self.service = MongoDBService()
        self.mock_collection = MagicMock()
        self.service.collection = self.mock_collection

    @patch("biometrics.services.mongodb_service.logger")
    def test_get_all_active_embeddings_collection_none(self, mock_logger):
        """Test when collection is None"""
        self.service.collection = None

        result = self.service.get_all_active_embeddings()

        self.assertEqual(result, [])
        mock_logger.warning.assert_called_with("MongoDB collection is None")

    @patch("biometrics.services.mongodb_service.logger")
    def test_get_all_active_embeddings_legacy_format(self, mock_logger):
        """Test retrieving from legacy 'faces' collection"""
        self.mock_collection.name = "faces"

        # Mock cursor with legacy documents
        mock_docs = [
            {
                "employee_id": 123,
                "encodings": [[0.1, 0.2], [0.3, 0.4]],
                "created_at": "2023-01-01",
            },
            {"employee_id": 456, "encodings": [[0.5, 0.6]], "created_at": "2023-01-02"},
        ]
        self.mock_collection.find.return_value = mock_docs

        result = self.service.get_all_active_embeddings()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], 123)  # employee_id
        self.assertEqual(len(result[0][1]), 2)  # 2 embeddings
        self.assertEqual(result[1][0], 456)  # employee_id
        self.assertEqual(len(result[1][1]), 1)  # 1 embedding

    @patch("biometrics.services.mongodb_service.logger")
    def test_get_all_active_embeddings_new_format(self, mock_logger):
        """Test retrieving from new format collection"""
        self.mock_collection.name = "face_embeddings"

        # Mock cursor with new format documents
        mock_docs = [
            {
                "employee_id": 123,
                "embeddings": [
                    {"vector": [0.1, 0.2], "quality_score": 0.9, "angle": "front"}
                ],
            },
            {
                "employee_id": 456,
                "embeddings": [
                    {"vector": [0.3, 0.4], "quality_score": 0.8, "angle": "left"}
                ],
            },
        ]
        self.mock_collection.find.return_value = mock_docs

        result = self.service.get_all_active_embeddings()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], 123)
        self.assertEqual(result[0][1][0]["vector"], [0.1, 0.2])
        self.assertEqual(result[1][0], 456)
        self.assertEqual(result[1][1][0]["vector"], [0.3, 0.4])

    def test_get_all_active_embeddings_empty_documents(self):
        """Test handling documents without employee_id or embeddings"""
        self.mock_collection.name = "face_embeddings"

        # Mock documents with missing fields
        mock_docs = [
            {"employee_id": 123, "embeddings": []},  # Empty embeddings
            {"embeddings": [{"vector": [0.1, 0.2]}]},  # Missing employee_id
            {
                "employee_id": None,
                "embeddings": [{"vector": [0.3, 0.4]}],
            },  # None employee_id
        ]
        self.mock_collection.find.return_value = mock_docs

        result = self.service.get_all_active_embeddings()

        self.assertEqual(len(result), 0)  # Should skip all invalid documents

    @patch("biometrics.services.mongodb_service.logger")
    def test_get_all_active_embeddings_exception(self, mock_logger):
        """Test exception handling"""
        self.mock_collection.find.side_effect = Exception("Query failed")

        result = self.service.get_all_active_embeddings()

        self.assertEqual(result, [])
        mock_logger.error.assert_called_with(
            "Failed to retrieve all embeddings: Query failed"
        )


class MongoDBServiceDeactivateDeleteTest(TestCase):
    """Test deactivate and delete operations"""

    def setUp(self):
        """Set up mock service"""
        self.service = MongoDBService()
        self.mock_collection = MagicMock()
        self.service.collection = self.mock_collection

    def test_deactivate_embeddings_collection_none(self):
        """Test deactivate when collection is None"""
        self.service.collection = None

        result = self.service.deactivate_embeddings(123)

        self.assertFalse(result)

    @patch("biometrics.services.mongodb_service.logger")
    def test_deactivate_embeddings_success(self, mock_logger):
        """Test successful deactivation"""
        mock_result = MagicMock()
        mock_result.modified_count = 1
        self.mock_collection.update_one.return_value = mock_result

        result = self.service.deactivate_embeddings(123)

        self.assertTrue(result)
        mock_logger.info.assert_called_with("Face embeddings deactivated")

    def test_deactivate_embeddings_no_modification(self):
        """Test deactivation when no documents modified"""
        mock_result = MagicMock()
        mock_result.modified_count = 0
        self.mock_collection.update_one.return_value = mock_result

        result = self.service.deactivate_embeddings(123)

        self.assertFalse(result)

    @patch("biometrics.services.mongodb_service.logger")
    def test_deactivate_embeddings_exception(self, mock_logger):
        """Test exception during deactivation"""
        self.mock_collection.update_one.side_effect = Exception("Update failed")

        result = self.service.deactivate_embeddings(123)

        self.assertFalse(result)
        mock_logger.error.assert_called_with(
            "Failed to deactivate embeddings: Update failed"
        )

    def test_delete_embeddings_collection_none(self):
        """Test delete when collection is None"""
        self.service.collection = None

        result = self.service.delete_embeddings(123)

        self.assertFalse(result)

    @patch("biometrics.services.mongodb_service.logger")
    def test_delete_embeddings_success(self, mock_logger):
        """Test successful deletion"""
        mock_result = MagicMock()
        mock_result.deleted_count = 1
        self.mock_collection.delete_one.return_value = mock_result

        result = self.service.delete_embeddings(123)

        self.assertTrue(result)
        mock_logger.info.assert_called_with("Face embeddings deleted")

    def test_delete_embeddings_no_deletion(self):
        """Test deletion when no documents deleted"""
        mock_result = MagicMock()
        mock_result.deleted_count = 0
        self.mock_collection.delete_one.return_value = mock_result

        result = self.service.delete_embeddings(123)

        self.assertFalse(result)

    @patch("biometrics.services.mongodb_service.logger")
    def test_delete_embeddings_exception(self, mock_logger):
        """Test exception during deletion"""
        self.mock_collection.delete_one.side_effect = Exception("Delete failed")

        result = self.service.delete_embeddings(123)

        self.assertFalse(result)
        mock_logger.error.assert_called_with(
            "Failed to delete embeddings: Delete failed"
        )


class MongoDBServiceStatisticsTest(TestCase):
    """Test statistics and health check methods"""

    def setUp(self):
        """Set up mock service"""
        self.service = MongoDBService()
        self.mock_collection = MagicMock()
        self.service.collection = self.mock_collection

    def test_get_statistics_collection_none(self):
        """Test statistics when collection is None"""
        self.service.collection = None

        result = self.service.get_statistics()

        expected = {
            "total_employees": 0,
            "active_employees": 0,
            "total_embeddings": 0,
            "status": "disconnected",
        }
        self.assertEqual(result, expected)

    def test_get_statistics_success(self):
        """Test successful statistics retrieval"""
        # Mock count queries
        self.mock_collection.count_documents.side_effect = [10, 8]  # total, active

        # Mock aggregation pipeline
        mock_aggregate_result = [{"total": 15}]
        self.mock_collection.aggregate.return_value = mock_aggregate_result

        result = self.service.get_statistics()

        expected = {
            "total_employees": 10,
            "active_employees": 8,
            "total_embeddings": 15,
            "status": "connected",
        }
        self.assertEqual(result, expected)

    def test_get_statistics_no_embeddings(self):
        """Test statistics when no embeddings found"""
        self.mock_collection.count_documents.side_effect = [5, 3]
        self.mock_collection.aggregate.return_value = []  # Empty result

        result = self.service.get_statistics()

        expected = {
            "total_employees": 5,
            "active_employees": 3,
            "total_embeddings": 0,
            "status": "connected",
        }
        self.assertEqual(result, expected)

    @patch("biometrics.services.mongodb_service.logger")
    def test_get_statistics_exception(self, mock_logger):
        """Test exception handling in statistics"""
        self.mock_collection.count_documents.side_effect = Exception("Count failed")

        result = self.service.get_statistics()

        expected = {
            "total_employees": 0,
            "active_employees": 0,
            "total_embeddings": 0,
            "status": "error",
            "error": "Statistics retrieval failed",
        }
        self.assertEqual(result, expected)
        mock_logger.exception.assert_called_with("Failed to get MongoDB statistics")

    def test_health_check_client_none(self):
        """Test health check when client is None"""
        self.service.client = None

        result = self.service.health_check()

        self.assertFalse(result)

    def test_health_check_success(self):
        """Test successful health check"""
        mock_client = MagicMock()
        self.service.client = mock_client

        result = self.service.health_check()

        self.assertTrue(result)
        mock_client.admin.command.assert_called_with("ping")

    @patch("biometrics.services.mongodb_service.logger")
    def test_health_check_exception(self, mock_logger):
        """Test health check exception handling"""
        mock_client = MagicMock()
        mock_client.admin.command.side_effect = Exception("Ping failed")
        self.service.client = mock_client

        result = self.service.health_check()

        self.assertFalse(result)
        mock_logger.error.assert_called_with("MongoDB health check failed: Ping failed")


class MongoDBServiceGlobalInstanceTest(TestCase):
    """Test global service instance management"""

    def setUp(self):
        """Clear global instance before each test"""
        # Clear global instance
        import biometrics.services.mongodb_service

        biometrics.services.mongodb_service.mongodb_service = None

    def tearDown(self):
        """Clear global instance after each test"""
        import biometrics.services.mongodb_service

        biometrics.services.mongodb_service.mongodb_service = None

    @patch("biometrics.services.mongodb_service.MongoDBService")
    def test_get_mongodb_service_creates_instance(self, mock_service_class):
        """Test that get_mongodb_service creates new instance"""
        mock_instance = MagicMock()
        mock_service_class.return_value = mock_instance

        result = get_mongodb_service()

        self.assertEqual(result, mock_instance)
        mock_service_class.assert_called_once()

    @patch("biometrics.services.mongodb_service.MongoDBService")
    def test_get_mongodb_service_singleton_pattern(self, mock_service_class):
        """Test singleton pattern - same instance returned"""
        mock_instance = MagicMock()
        mock_service_class.return_value = mock_instance

        # Get service twice
        result1 = get_mongodb_service()
        result2 = get_mongodb_service()

        # Should be same instance
        self.assertEqual(result1, result2)
        # Service should be created only once
        mock_service_class.assert_called_once()
