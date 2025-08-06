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
                # Try to use existing collection with data first
                if 'faces' in self.db.list_collection_names() and self.db['faces'].count_documents({}) > 0:
                    self.collection = self.db['faces']
                    logger.info("Using existing 'faces' collection with data")
                else:
                    self.collection = self.db['face_embeddings']
                    logger.info("Using 'face_embeddings' collection")
                
                # Skip index creation - handled by mongodb_repository.py to avoid conflicts
                logger.info("MongoDB connection established for biometrics")
            else:
                # Only log error if not testing
                import sys
                if 'test' not in sys.argv:
                    logger.error("MongoDB database not available")
        except Exception as e:
            # Only log error if not testing
            import sys
            if 'test' not in sys.argv:
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
        
        # DETAILED LOGGING for registration debugging  
        logger.info(f"🔍 MongoDB save_face_embeddings:")
        logger.info(f"   - Employee ID to save: {employee_id}")
        logger.info(f"   - Embeddings count: {len(embeddings)}")
        logger.info(f"   - Collection name: {self.collection.name}")
        
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
                    logger.info("Face embeddings updated")
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
                logger.info(f"Face embeddings document created with ID: {result.inserted_id}")
                
                # Verify the document was saved correctly
                saved_doc = self.collection.find_one({"_id": result.inserted_id})
                if saved_doc:
                    logger.info(f"✅ Verified: Document saved for employee_id {saved_doc.get('employee_id')}")
                else:
                    logger.error(f"❌ Verification failed: Document not found after insert")
                
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
            # Check if using 'faces' collection (legacy format)
            if self.collection.name == 'faces':
                document = self.collection.find_one({"employee_id": employee_id})
                if document:
                    encodings = document.get('encodings', [])
                    if encodings:
                        # Convert legacy format to new format
                        embeddings = []
                        for i, encoding in enumerate(encodings):
                            embeddings.append({
                                'vector': encoding,
                                'quality_score': 0.8,  # Default quality
                                'created_at': document.get('created_at'),
                                'angle': f'angle_{i}'
                            })
                        return embeddings
            else:
                # New format
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
            logger.warning("MongoDB collection is None")
            return []
        
        try:
            logger.info("Fetching all active embeddings from MongoDB...")
            results = []
            
            # Check if using 'faces' collection (legacy format)
            if self.collection.name == 'faces':
                # Legacy format: look for all documents (no is_active field)
                cursor = self.collection.find({})
                for document in cursor:
                    employee_id = document.get('employee_id')
                    encodings = document.get('encodings', [])
                    if employee_id and encodings:
                        # Convert legacy format to new format
                        embeddings = []
                        for i, encoding in enumerate(encodings):
                            embeddings.append({
                                'vector': encoding,
                                'quality_score': 0.8,  # Default quality
                                'created_at': document.get('created_at'),
                                'angle': f'angle_{i}'
                            })
                        results.append((employee_id, embeddings))
            else:
                # New format: use is_active field
                cursor = self.collection.find({"is_active": True})
                for document in cursor:
                    employee_id = document.get('employee_id')
                    embeddings = document.get('embeddings', [])
                    if employee_id and embeddings:
                        results.append((employee_id, embeddings))
            
            logger.info(f"Retrieved {len(results)} active embedding sets from {self.collection.name}")
            for employee_id, embeddings in results:
                logger.debug(f"  Employee {employee_id}: {len(embeddings)} embeddings")
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
                logger.info("Face embeddings deactivated")
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
                logger.info("Face embeddings deleted")
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
            logger.exception("Failed to get MongoDB statistics")
            return {
                "total_employees": 0,
                "active_employees": 0,
                "total_embeddings": 0,
                "status": "error",
                "error": "Statistics retrieval failed"
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