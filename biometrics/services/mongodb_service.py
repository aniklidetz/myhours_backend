# biometrics/services/mongodb_service.py
import logging
from typing import List, Dict, Optional, Tuple
import numpy as np
from bson import ObjectId
from django.conf import settings
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, OperationFailure
import json

logger = logging.getLogger(__name__)


class MongoDBService:
    """Service for interacting with MongoDB for biometric data storage"""
    
    def __init__(self):
        self.client = None
        self.db = None
        self.collection = None
        self._connect()
    
    def _connect(self):
        """Establish connection to MongoDB"""
        try:
            self.client = settings.MONGO_CLIENT
            self.db = settings.MONGO_DB
            
            if self.db is not None:
                self.collection = self.db['face_embeddings']
                # Create indexes for better performance
                self._create_indexes()
                logger.info("MongoDB connection established for biometrics")
            else:
                logger.error("MongoDB database not available")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            self.client = None
            self.db = None
            self.collection = None
    
    def _create_indexes(self):
        """Create necessary indexes for the collection"""
        try:
            # Index on employee_id for fast lookups
            self.collection.create_index([("employee_id", ASCENDING)])
            # Index on is_active for filtering
            self.collection.create_index([("is_active", ASCENDING)])
            # Compound index for active employee lookups
            self.collection.create_index([
                ("employee_id", ASCENDING),
                ("is_active", ASCENDING)
            ])
            logger.info("MongoDB indexes created successfully")
        except Exception as e:
            logger.error(f"Failed to create indexes: {e}")
    
    def save_face_embeddings(self, employee_id: int, embeddings: List[Dict]) -> Optional[str]:
        """
        Save face embeddings for an employee
        
        Args:
            employee_id: Employee ID
            embeddings: List of embedding dictionaries containing vector and metadata
            
        Returns:
            MongoDB document ID if successful, None otherwise
        """
        if self.collection is None:
            logger.error("MongoDB collection not available")
            return None
        
        try:
            # Check if employee already has embeddings
            existing = self.collection.find_one({"employee_id": employee_id})
            
            if existing:
                # Update existing embeddings
                result = self.collection.update_one(
                    {"employee_id": employee_id},
                    {
                        "$set": {
                            "embeddings": embeddings,
                            "metadata.last_updated": np.datetime64('now').tolist(),
                            "is_active": True
                        }
                    }
                )
                if result.modified_count > 0:
                    logger.info(f"Updated embeddings for employee {employee_id}")
                    return str(existing['_id'])
            else:
                # Create new document
                document = {
                    "employee_id": employee_id,
                    "embeddings": embeddings,
                    "metadata": {
                        "algorithm": "dlib_face_recognition_resnet_model_v1",
                        "version": "1.0",
                        "created_at": np.datetime64('now').tolist(),
                        "last_updated": np.datetime64('now').tolist()
                    },
                    "is_active": True
                }
                
                result = self.collection.insert_one(document)
                logger.info(f"Created new embeddings document for employee {employee_id}")
                return str(result.inserted_id)
                
        except Exception as e:
            logger.error(f"Failed to save embeddings: {e}")
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
            return None
        
        try:
            document = self.collection.find_one({
                "employee_id": employee_id,
                "is_active": True
            })
            
            if document:
                return document.get('embeddings', [])
            return None
            
        except Exception as e:
            logger.error(f"Failed to retrieve embeddings: {e}")
            return None
    
    def get_all_active_embeddings(self) -> List[Tuple[int, List[Dict]]]:
        """
        Retrieve all active face embeddings for matching
        
        Returns:
            List of tuples (employee_id, embeddings)
        """
        if self.collection is None:
            return []
        
        try:
            results = []
            cursor = self.collection.find({"is_active": True})
            
            for document in cursor:
                employee_id = document.get('employee_id')
                embeddings = document.get('embeddings', [])
                if employee_id and embeddings:
                    results.append((employee_id, embeddings))
            
            logger.info(f"Retrieved {len(results)} active embedding sets")
            return results
            
        except Exception as e:
            logger.error(f"Failed to retrieve all embeddings: {e}")
            return []
    
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
                        "metadata.deactivated_at": np.datetime64('now').tolist()
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"Deactivated embeddings for employee {employee_id}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Failed to deactivate embeddings: {e}")
            return False
    
    def delete_embeddings(self, employee_id: int) -> bool:
        """
        Permanently delete embeddings for an employee
        
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
                logger.info(f"Deleted embeddings for employee {employee_id}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Failed to delete embeddings: {e}")
            return False
    
    def get_statistics(self) -> Dict:
        """
        Get statistics about stored embeddings
        
        Returns:
            Dictionary with statistics
        """
        if self.collection is None:
            return {
                "total_employees": 0,
                "active_employees": 0,
                "total_embeddings": 0,
                "status": "disconnected"
            }
        
        try:
            total_docs = self.collection.count_documents({})
            active_docs = self.collection.count_documents({"is_active": True})
            
            # Count total embeddings
            pipeline = [
                {"$match": {"is_active": True}},
                {"$project": {"embeddings_count": {"$size": "$embeddings"}}},
                {"$group": {"_id": None, "total": {"$sum": "$embeddings_count"}}}
            ]
            
            result = list(self.collection.aggregate(pipeline))
            total_embeddings = result[0]['total'] if result else 0
            
            return {
                "total_employees": total_docs,
                "active_employees": active_docs,
                "total_embeddings": total_embeddings,
                "status": "connected"
            }
            
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {
                "total_employees": 0,
                "active_employees": 0,
                "total_embeddings": 0,
                "status": "error",
                "error": str(e)
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
            self.client.admin.command('ping')
            return True
        except Exception as e:
            logger.error(f"MongoDB health check failed: {e}")
            return False


# Global instance
mongodb_service = MongoDBService()