import logging
import pymongo
from pymongo import MongoClient
from bson.objectid import ObjectId
from django.conf import settings
import numpy as np
import json
import datetime

logger = logging.getLogger(__name__)

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
            # Using the client from Django settings
            from django.conf import settings
            
            db = settings.MONGO_DB
            collection = db['face_encodings']
            
            # Create indexes if they don't exist
            collection.create_index([("employee_id", pymongo.ASCENDING)])
            
            return collection
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
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
            str: MongoDB document ID
        """
        collection = cls.get_collection()
        if not collection:
            logger.error("MongoDB collection not available")
            return None
        
        try:
            # Convert numpy array to list for MongoDB storage
            if isinstance(face_encoding, np.ndarray):
                face_encoding = face_encoding.tolist()
            
            # Create document
            document = {
                "employee_id": employee_id,
                "face_encoding": face_encoding,
                "created_at": datetime.datetime.now(datetime.timezone.utc),
            }
            
            # Optionally store the reference image if provided
            if image_data:
                document["reference_image"] = image_data
            
            # Insert document
            result = collection.insert_one(document)
            document_id = str(result.inserted_id)
            
            logger.info(f"Face encoding saved with ID: {document_id}")
            return document_id
        
        except Exception as e:
            logger.error(f"Error saving face encoding: {e}")
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
            if employee_id:
                query["employee_id"] = employee_id
            
            # Get documents
            documents = list(collection.find(query, {"employee_id": 1, "face_encoding": 1}))
            
            # Convert ObjectId to string for serialization
            for doc in documents:
                doc["_id"] = str(doc["_id"])
                # Convert face_encoding list back to numpy array
                if doc.get("face_encoding"):
                    doc["face_encoding"] = np.array(doc["face_encoding"])
            
            return documents
        
        except Exception as e:
            logger.error(f"Error retrieving face encodings: {e}")
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
            # Delete documents
            result = collection.delete_many({"employee_id": employee_id})
            deleted_count = result.deleted_count
            
            logger.info(f"Deleted {deleted_count} face encodings for employee {employee_id}")
            return deleted_count
        
        except Exception as e:
            logger.error(f"Error deleting face encodings: {e}")
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
            # Convert numpy array to list for MongoDB storage
            if isinstance(face_encoding, np.ndarray):
                face_encoding = face_encoding.tolist()
            
            # Create update document
            update_doc = {
                "$set": {
                    "face_encoding": face_encoding,
                    "updated_at": datetime.datetime.now(datetime.timezone.utc)
                }
            }
            
            # Add image data if provided
            if image_data:
                update_doc["$set"]["reference_image"] = image_data
            
            # Update document
            result = collection.update_one(
                {"_id": ObjectId(document_id)},
                update_doc
            )
            
            return result.modified_count > 0
        
        except Exception as e:
            logger.error(f"Error updating face encoding: {e}")
            return False