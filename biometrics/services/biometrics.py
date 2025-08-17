import datetime
import json
import logging

import numpy as np
import pymongo
from bson.objectid import ObjectId
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, PyMongoError

from django.conf import settings

logger = logging.getLogger("biometrics")


def safe_log_data(data, max_length=8):
    """Safely log sensitive data by truncating and masking"""
    if data is None:
        return "None"
    data_str = str(data)
    if len(data_str) > max_length:
        return f"{data_str[:max_length]}..."
    return data_str


class BiometricService:
    """
    Service for handling biometric data storage in MongoDB.
    This service manages face encodings and related data.
    """

    @staticmethod
    def get_collection():
        """
        Get the MongoDB collection for face encodings.

        Returns:
            pymongo.collection.Collection or None: MongoDB collection or None if connection failed
        """
        try:
            # Check if MongoDB is available
            if not hasattr(settings, "MONGO_DB") or settings.MONGO_DB is None:
                logger.error("MongoDB not configured or not available")
                return None

            db = settings.MONGO_DB
            collection = db["face_encodings"]

            # Test connection
            try:
                collection.database.client.admin.command("ping")
            except ConnectionFailure:
                logger.error("MongoDB connection failed")
                return None

            # Create indexes if they don't exist
            try:
                collection.create_index(
                    [("employee_id", pymongo.ASCENDING)], background=True
                )
                collection.create_index(
                    [("created_at", pymongo.DESCENDING)], background=True
                )
            except Exception as e:
                logger.warning(f"Failed to create indexes: {e}")

            return collection
        except Exception as e:
            from core.logging_utils import err_tag

            logger.error("Failed to get MongoDB collection", extra={"err": err_tag(e)})
            return None

    @classmethod
    def save_face_encoding(cls, employee_id, face_encoding, image_data=None):
        """
        Save employee face encoding to MongoDB.

        Args:
            employee_id (int): Employee ID
            face_encoding (np.ndarray): Face encoding vector
            image_data (str, optional): Base64 image data

        Returns:
            str or None: MongoDB document ID if successful, None if failed
        """
        collection = cls.get_collection()
        if not collection:
            logger.error("MongoDB collection not available")
            return None

        try:
            # Validate inputs
            if not isinstance(employee_id, int) or employee_id <= 0:
                logger.error("Invalid employee_id provided")
                return None

            if face_encoding is None:
                logger.error("face_encoding cannot be None")
                return None

            # Convert numpy array to list for MongoDB storage
            if isinstance(face_encoding, np.ndarray):
                face_encoding = face_encoding.tolist()
            elif not isinstance(face_encoding, list):
                logger.error("Invalid face_encoding type provided")
                return None

            # Create document
            document = {
                "employee_id": int(employee_id),
                "face_encoding": face_encoding,
                "created_at": datetime.datetime.now(datetime.timezone.utc),
                "version": "1.0",  # For future compatibility
            }

            # Optionally store the reference image if provided
            if image_data:
                # Limit image data size
                if len(image_data) > 10000:  # Limit to ~10KB
                    image_data = image_data[:10000]
                document["reference_image"] = image_data

            # Check if employee already exists
            existing_doc = collection.find_one({"employee_id": employee_id})

            if existing_doc:
                # Update existing document
                document["updated_at"] = datetime.datetime.now(datetime.timezone.utc)
                result = collection.replace_one({"employee_id": employee_id}, document)
                document_id = str(existing_doc["_id"])
                logger.info("Face encoding updated")
            else:
                # Insert new document
                result = collection.insert_one(document)
                document_id = str(result.inserted_id)
                logger.info("Face encoding created successfully")

            return document_id

        except PyMongoError as e:
            logger.exception("MongoDB error while saving face encoding")
            return None
        except Exception as e:
            logger.exception("Unexpected error saving face encoding")
            return None

    @classmethod
    def get_employee_face_encodings(cls, employee_id=None):
        """
        Get face encodings for an employee or all employees.

        Args:
            employee_id (int, optional): Employee ID

        Returns:
            list: List of dict with employee_id and face_encoding
        """
        collection = cls.get_collection()
        if not collection:
            logger.error("MongoDB collection not available")
            return []

        try:
            # Query filter
            query = {}
            if employee_id is not None:
                query["employee_id"] = int(employee_id)

            # Get documents - only fetch necessary fields
            projection = {
                "employee_id": 1,
                "face_encoding": 1,
                "created_at": 1,
                "version": 1,
            }

            documents = list(collection.find(query, projection))

            # Process documents
            result = []
            for doc in documents:
                try:
                    # Convert ObjectId to string for serialization
                    doc["_id"] = str(doc["_id"])

                    # Convert face_encoding list back to numpy array
                    if doc.get("face_encoding"):
                        doc["face_encoding"] = np.array(
                            doc["face_encoding"], dtype=np.float32
                        )

                    result.append(doc)
                except Exception as e:
                    logger.warning(f"Error processing document {doc.get('_id')}: {e}")
                    continue

            logger.info(f"Retrieved {len(result)} face encodings")
            return result

        except PyMongoError as e:
            logger.exception("MongoDB error retrieving face encodings")
            return []
        except Exception as e:
            logger.exception("Unexpected error retrieving face encodings")
            return []

    @classmethod
    def delete_employee_face_encodings(cls, employee_id):
        """
        Delete all face encodings for an employee.

        Args:
            employee_id (int): Employee ID

        Returns:
            int: Number of deleted documents
        """
        collection = cls.get_collection()
        if not collection:
            logger.error("MongoDB collection not available")
            return 0

        try:
            if not isinstance(employee_id, int) or employee_id <= 0:
                logger.error("Invalid employee_id provided")
                return 0

            # Delete documents
            result = collection.delete_many({"employee_id": int(employee_id)})
            deleted_count = result.deleted_count

            logger.info(f"Deleted {deleted_count} face encodings")
            return deleted_count

        except PyMongoError as e:
            logger.exception("MongoDB error deleting face encodings")
            return 0
        except Exception as e:
            logger.exception("Unexpected error deleting face encodings")
            return 0

    @classmethod
    def update_face_encoding(cls, document_id, face_encoding, image_data=None):
        """
        Update an existing face encoding document.

        Args:
            document_id (str): MongoDB document ID
            face_encoding (np.ndarray): New face encoding vector
            image_data (str, optional): New base64 image data

        Returns:
            bool: Success status
        """
        collection = cls.get_collection()
        if not collection:
            logger.error("MongoDB collection not available")
            return False

        try:
            # Validate document_id
            if not document_id or not ObjectId.is_valid(document_id):
                logger.error("Invalid document_id provided")
                return False

            # Validate face_encoding
            if face_encoding is None:
                logger.error("face_encoding cannot be None")
                return False

            # Convert numpy array to list for MongoDB storage
            if isinstance(face_encoding, np.ndarray):
                face_encoding = face_encoding.tolist()
            elif not isinstance(face_encoding, list):
                logger.error("Invalid face_encoding type provided")
                return False

            # Create update document
            update_doc = {
                "$set": {
                    "face_encoding": face_encoding,
                    "updated_at": datetime.datetime.now(datetime.timezone.utc),
                }
            }

            # Add image data if provided
            if image_data:
                # Limit image data size
                if len(image_data) > 10000:  # Limit to ~10KB
                    image_data = image_data[:10000]
                update_doc["$set"]["reference_image"] = image_data

            # Update document
            result = collection.update_one({"_id": ObjectId(document_id)}, update_doc)

            success = result.modified_count > 0
            if success:
                logger.info("Face encoding document updated")
            else:
                logger.warning("No document updated")

            return success

        except PyMongoError as e:
            logger.exception("MongoDB error updating face encoding")
            return False
        except Exception as e:
            logger.exception("Unexpected error updating face encoding")
            return False

    @classmethod
    def get_stats(cls):
        """
        Get statistics about stored face encodings.

        Returns:
            dict: Statistics including total count, unique employees, etc.
        """
        collection = cls.get_collection()
        if not collection:
            return {"error": "MongoDB collection not available"}

        try:
            # Get basic counts
            total_count = collection.count_documents({})

            # Get unique employee count
            unique_employees = len(collection.distinct("employee_id"))

            # Get recent uploads (last 7 days)
            week_ago = datetime.datetime.now(
                datetime.timezone.utc
            ) - datetime.timedelta(days=7)
            recent_count = collection.count_documents(
                {"created_at": {"$gte": week_ago}}
            )

            return {
                "total_face_encodings": total_count,
                "unique_employees": unique_employees,
                "recent_uploads": recent_count,
                "collection_name": collection.name,
            }
        except Exception as e:
            logger.exception("Error getting biometric statistics")
            return {"error": "Failed to retrieve biometric statistics"}
