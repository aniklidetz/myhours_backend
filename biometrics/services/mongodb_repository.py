"""
MongoDB Repository - Isolated layer for biometric data operations
"""

import datetime
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
from bson import ObjectId
from pymongo import ASCENDING, MongoClient
from pymongo.errors import ConnectionFailure, DuplicateKeyError, OperationFailure

from django.conf import settings

from core.logging_utils import err_tag

logger = logging.getLogger("biometrics")


class MongoBiometricRepository:
    """
    Isolated MongoDB repository for biometric operations

    This class provides a clean, focused interface for biometric data operations,
    reducing coupling with the main service layer.
    """

    COLLECTION_NAME = "face_embeddings"  # Fixed collection name - no dynamic selection!

    def __init__(self):
        self.client = None
        self.db = None
        self.collection = None
        self._connect()

    def _connect(self):
        """Establish connection to MongoDB with fixed collection"""
        # Skip MongoDB connection during tests to prevent hanging
        import sys
        import os
        
        # Multiple checks to ensure we skip MongoDB in test environments
        is_testing = (
            getattr(settings, "TESTING", False) or 
            hasattr(settings, "GITHUB_ACTIONS") or
            "test" in sys.argv or
            os.environ.get("TESTING") == "True"
        )
        
        if is_testing:
            logger.debug("Skipping MongoDB connection in test environment")
            self.client = None
            self.db = None
            self.collection = None
            return

        try:
            self.client = settings.MONGO_CLIENT
            self.db = settings.MONGO_DB

            if self.db is not None:
                # FIXED: Always use face_embeddings collection
                self.collection = self.db[self.COLLECTION_NAME]
                logger.info(
                    f"MongoDB repository connected to '{self.COLLECTION_NAME}' collection"
                )

                # Create indexes for better performance
                self._create_indexes()
            else:
                # Only log error if not testing
                import sys

                if "test" not in sys.argv:
                    logger.error("MongoDB database not available")

        except Exception as e:
            import sys

            if "test" not in sys.argv:

                logger.error(
                    f"Failed to connect to MongoDB: {err_tag(e)}"
                )  # lgtm[py/clear-text-logging-sensitive-data]
            self.client = None
            self.db = None
            self.collection = None

    def _create_indexes(self):
        """Create necessary indexes for the collection"""
        try:
            # Check existing indexes first
            existing_indexes = {
                idx["name"]: idx for idx in self.collection.list_indexes()
            }

            # Unique index on employee_id (prevents duplicates)
            if "employee_id_1" in existing_indexes:
                existing_idx = existing_indexes["employee_id_1"]
                # Check if existing index is unique
                if not existing_idx.get("unique", False):
                    logger.info(
                        "Dropping non-unique employee_id index to recreate as unique"
                    )
                    self.collection.drop_index("employee_id_1")
                    self.collection.create_index(
                        [("employee_id", ASCENDING)], unique=True, background=True
                    )
                    logger.info("Recreated employee_id index as unique")
                else:
                    logger.debug("Unique employee_id index already exists")
            else:
                self.collection.create_index(
                    [("employee_id", ASCENDING)], unique=True, background=True
                )
                logger.info("Created unique employee_id index")

            # Index on is_active for filtering
            if "is_active_1" not in existing_indexes:
                self.collection.create_index(
                    [("is_active", ASCENDING)], background=True
                )
                logger.debug("Created is_active index")

            # Compound index for active employee lookups
            compound_name = "employee_id_1_is_active_1"
            if compound_name not in existing_indexes:
                self.collection.create_index(
                    [("employee_id", ASCENDING), ("is_active", ASCENDING)],
                    background=True,
                )
                logger.debug("Created compound employee_id + is_active index")

            logger.info("MongoDB indexes verified/created successfully")

        except Exception as e:

            logger.error(
                f"Failed to create indexes: {err_tag(e)}"
            )  # lgtm[py/clear-text-logging-sensitive-data]

    def save_face_embeddings(
        self, employee_id: int, embeddings: List[Dict]
    ) -> Optional[str]:
        """
        Save face embeddings for an employee with upsert logic

        Args:
            employee_id: Employee ID
            embeddings: List of embedding dictionaries containing vector and metadata

        Returns:
            MongoDB document ID if successful, None otherwise
        """
        if self.collection is None:
            logger.error("MongoDB collection not available")
            return None

        if not isinstance(employee_id, int) or employee_id <= 0:
            logger.error(f"Invalid employee_id: {employee_id}")
            return None

        if not embeddings or not isinstance(embeddings, list):
            logger.error("Invalid embeddings data")
            return None

        logger.info(f"🔍 Saving face embeddings for employee {employee_id}")
        logger.debug(f"   - Embeddings count: {len(embeddings)}")
        logger.debug(f"   - Collection: {self.collection.name}")

        try:
            # Prepare document
            now = datetime.datetime.now(datetime.timezone.utc)
            document = {
                "employee_id": employee_id,
                "embeddings": embeddings,
                "metadata": {
                    "algorithm": "dlib_face_recognition_resnet_model_v1",
                    "version": "1.0",
                    "created_at": now,
                    "last_updated": now,
                },
                "is_active": True,
            }

            # Upsert operation (update if exists, insert if not)
            result = self.collection.replace_one(
                {"employee_id": employee_id}, document, upsert=True
            )

            if result.upserted_id:
                # New document created
                document_id = str(result.upserted_id)
                logger.info(f"✅ New embeddings document created: {document_id}")
            elif result.modified_count > 0:
                # Existing document updated
                existing_doc = self.collection.find_one({"employee_id": employee_id})
                document_id = str(existing_doc["_id"]) if existing_doc else None
                logger.info(f"✅ Existing embeddings document updated: {document_id}")
            else:
                logger.warning(f"⚠️ No changes made for employee {employee_id}")
                return None

            # Verify the document was saved correctly
            saved_doc = self.collection.find_one({"employee_id": employee_id})
            if saved_doc and saved_doc.get("embeddings"):
                logger.info(
                    f"✅ Verification passed: {len(saved_doc['embeddings'])} embeddings saved"
                )
                return document_id
            else:
                logger.error(
                    "❌ Verification failed: Document not found or empty after save"
                )
                return None

        except DuplicateKeyError as e:

            logger.error(
                f"❌ Duplicate key error for employee {employee_id}: {err_tag(e)}"
            )  # lgtm[py/clear-text-logging-sensitive-data]
            return None
        except Exception as e:

            logger.error(
                f"❌ Failed to save embeddings for employee {employee_id}: {err_tag(e)}"
            )  # lgtm[py/clear-text-logging-sensitive-data]
            return None

    def get_face_embeddings(self, employee_id: int) -> Optional[List[Dict]]:
        """
        Retrieve face embeddings for a specific employee

        Args:
            employee_id: Employee ID

        Returns:
            List of embeddings if found, None otherwise
        """
        if self.collection is None:
            logger.warning("MongoDB collection not available")
            return None

        try:
            document = self.collection.find_one(
                {"employee_id": employee_id, "is_active": True}
            )

            if document:
                embeddings = document.get("embeddings", [])
                logger.debug(
                    f"Retrieved {len(embeddings)} embeddings for employee {employee_id}"
                )
                return embeddings
            else:
                logger.debug(f"No embeddings found for employee {employee_id}")
                return None

        except Exception as e:

            logger.error(
                f"Failed to retrieve embeddings for employee {employee_id}: {err_tag(e)}"
            )  # lgtm[py/clear-text-logging-sensitive-data]
            return None

    def get_all_employee_ids(self) -> List[int]:
        """
        Get all employee IDs that have active biometric data

        Returns:
            List of employee IDs
        """
        if self.collection is None:
            return []

        try:
            cursor = self.collection.find(
                {"is_active": True}, {"employee_id": 1, "_id": 0}
            )
            employee_ids = [doc["employee_id"] for doc in cursor]
            logger.debug(
                f"Found {len(employee_ids)} employees with active biometric data"
            )
            return employee_ids

        except Exception as e:

            logger.error(
                f"Failed to get all employee IDs: {err_tag(e)}"
            )  # lgtm[py/clear-text-logging-sensitive-data]
            return []

    def find_matching_employee(
        self, face_encoding: List[float], tolerance: float = 0.6
    ) -> Optional[Tuple[int, float]]:
        """
        Find matching employee for given face encoding

        Args:
            face_encoding: Face encoding vector to match
            tolerance: Matching tolerance (lower = stricter)

        Returns:
            Tuple of (employee_id, confidence_score) if match found, None otherwise
        """
        if self.collection is None:
            return None

        try:
            # Get all active embeddings
            cursor = self.collection.find({"is_active": True})

            best_match = None
            best_distance = float("inf")

            for document in cursor:
                employee_id = document.get("employee_id")
                embeddings = document.get("embeddings", [])

                for embedding_data in embeddings:
                    stored_encoding = embedding_data.get("vector", [])
                    if not stored_encoding:
                        continue

                    # Calculate Euclidean distance
                    try:
                        distance = np.linalg.norm(
                            np.array(face_encoding) - np.array(stored_encoding)
                        )

                        if distance < tolerance and distance < best_distance:
                            best_distance = distance
                            # Convert distance to confidence score (0-1, higher is better)
                            confidence = max(0.0, 1.0 - (distance / tolerance))
                            best_match = (employee_id, confidence)

                    except Exception as e:

                        logger.warning(
                            f"Failed to calculate distance for employee {employee_id}: {err_tag(e)}"
                        )  # lgtm[py/clear-text-logging-sensitive-data]
                        continue

            if best_match:
                employee_id, confidence = best_match
                logger.debug(
                    f"Best match found: employee_id={employee_id}, confidence={confidence:.3f}"
                )
            else:
                logger.debug("No matching employee found")

            return best_match

        except Exception as e:

            logger.error(
                f"Failed to find matching employee: {err_tag(e)}"
            )  # lgtm[py/clear-text-logging-sensitive-data]
            return None

    def delete_embeddings(self, employee_id: int) -> bool:
        """
        Delete embeddings for an employee

        Args:
            employee_id: Employee ID

        Returns:
            True if successful, False otherwise
        """
        if self.collection is None:
            return False

        try:
            result = self.collection.delete_one({"employee_id": employee_id})

            if result.deleted_count > 0:
                logger.info(f"✅ Embeddings deleted for employee {employee_id}")
                return True
            else:
                logger.warning(
                    f"⚠️ No embeddings found to delete for employee {employee_id}"
                )
                return False

        except Exception as e:

            logger.error(
                f"❌ Failed to delete embeddings for employee {employee_id}: {err_tag(e)}"
            )  # lgtm[py/clear-text-logging-sensitive-data]
            return False

    def deactivate_embeddings(self, employee_id: int) -> bool:
        """
        Deactivate embeddings for an employee (soft delete)

        Args:
            employee_id: Employee ID

        Returns:
            True if successful, False otherwise
        """
        if self.collection is None:
            return False

        try:
            result = self.collection.update_one(
                {"employee_id": employee_id},
                {
                    "$set": {
                        "is_active": False,
                        "metadata.deactivated_at": datetime.datetime.now(
                            datetime.timezone.utc
                        ),
                    }
                },
            )

            if result.modified_count > 0:
                logger.info(f"✅ Embeddings deactivated for employee {employee_id}")
                return True
            else:
                logger.warning(
                    f"⚠️ No embeddings found to deactivate for employee {employee_id}"
                )
                return False

        except Exception as e:

            logger.error(
                f"❌ Failed to deactivate embeddings for employee {employee_id}: {err_tag(e)}"
            )  # lgtm[py/clear-text-logging-sensitive-data]
            return False

    def get_statistics(self) -> Dict:
        """
        Get repository statistics

        Returns:
            Dictionary with statistics
        """
        if self.collection is None:
            return {
                "status": "disconnected",
                "total_documents": 0,
                "active_documents": 0,
                "total_embeddings": 0,
            }

        try:
            total_docs = self.collection.count_documents({})
            active_docs = self.collection.count_documents({"is_active": True})

            # Count total embeddings in active documents
            pipeline = [
                {"$match": {"is_active": True}},
                {"$project": {"embeddings_count": {"$size": "$embeddings"}}},
                {"$group": {"_id": None, "total": {"$sum": "$embeddings_count"}}},
            ]

            result = list(self.collection.aggregate(pipeline))
            total_embeddings = result[0]["total"] if result else 0

            return {
                "status": "connected",
                "collection_name": self.COLLECTION_NAME,
                "total_documents": total_docs,
                "active_documents": active_docs,
                "inactive_documents": total_docs - active_docs,
                "total_embeddings": total_embeddings,
                "avg_embeddings_per_employee": (
                    round(total_embeddings / active_docs, 2) if active_docs > 0 else 0
                ),
            }

        except Exception as e:

            logger.error(
                f"Failed to get statistics: {err_tag(e)}"
            )  # lgtm[py/clear-text-logging-sensitive-data]
            return {
                "status": "error",
                "error": err_tag(e),  # Use safe error tag in return value too
                "total_documents": 0,
                "active_documents": 0,
                "total_embeddings": 0,
            }

    def health_check(self) -> bool:
        """
        Check if MongoDB connection is healthy

        Returns:
            True if healthy, False otherwise
        """
        if self.client is None:
            return False

        try:
            # Ping the server
            self.client.admin.command("ping")

            # Verify collection access
            self.collection.count_documents({}, limit=1)

            return True
        except Exception as e:

            logger.error(
                f"MongoDB health check failed: {err_tag(e)}"
            )  # lgtm[py/clear-text-logging-sensitive-data]
            return False


# Global instance with lazy initialization to prevent test hangs
_mongo_biometric_repository = None

def get_mongo_biometric_repository():
    """Get the global MongoDB biometric repository instance with lazy initialization"""
    global _mongo_biometric_repository
    if _mongo_biometric_repository is None:
        _mongo_biometric_repository = MongoBiometricRepository()
    return _mongo_biometric_repository

class _LazyMongoRepositoryProxy:
    """Proxy that delays MongoDB repository initialization until actually needed"""
    def __getattr__(self, name):
        return getattr(get_mongo_biometric_repository(), name)

# Use lazy proxy to prevent MongoDB connection during test imports
mongo_biometric_repository = _LazyMongoRepositoryProxy()
