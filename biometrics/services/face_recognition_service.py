import logging
import cv2
import numpy as np
import base64
from io import BytesIO
from PIL import Image
from .biometrics import BiometricService
from django.core.cache import cache

logger = logging.getLogger(__name__)

class FaceRecognitionService:
    """
    Service for face recognition using OpenCV.
    """
    
    # Инициализация распознавателя лиц
    FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    FACE_RECOGNIZER = cv2.face.LBPHFaceRecognizer_create()
    
    @staticmethod
    def decode_image(base64_image):
        """Decode base64 image to OpenCV format"""
        try:
            # Remove data URI prefix if present
            if ',' in base64_image:
                base64_image = base64_image.split(',', 1)[1]
            
            # Decode base64 to bytes
            image_bytes = base64.b64decode(base64_image)
            
            # Convert to numpy array
            nparr = np.frombuffer(image_bytes, np.uint8)
            
            # Decode to OpenCV image (BGR format)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
            return image
        except Exception as e:
            logger.error(f"Error decoding image: {e}")
            return None
    
    @classmethod
    def extract_face_features(cls, image):
        """Extract face features from an image"""
        try:
            # Convert to grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Detect faces
            faces = cls.FACE_CASCADE.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30)
            )
            
            if len(faces) == 0:
                logger.warning("No faces detected in the image")
                return None
            
            # Get the largest face
            largest_face = max(faces, key=lambda rect: rect[2] * rect[3])
            x, y, w, h = largest_face
            
            # Extract face ROI
            face_roi = gray[y:y+h, x:x+w]
            
            # Resize to standard size
            face_roi = cv2.resize(face_roi, (100, 100))
            
            return face_roi
        except Exception as e:
            logger.error(f"Error extracting face features: {e}")
            return None
    
    @classmethod
    def save_employee_face(cls, employee_id, base64_image):
        """Save employee face to database"""
        try:
            # Decode image
            image = cls.decode_image(base64_image)
            if image is None:
                return None
            
            # Extract face features
            face_roi = cls.extract_face_features(image)
            if face_roi is None:
                return None
            
            # Flatten the face for storage
            face_encoding = face_roi.flatten()
            
            # Save to database
            document_id = BiometricService.save_face_encoding(
                employee_id, 
                face_encoding,
                base64_image
            )
            
            return document_id
        except Exception as e:
            logger.error(f"Error saving employee face: {e}")
            return None
    
    @classmethod
    def recognize_employee(cls, base64_image, threshold=4000):
        """Recognize employee from face image"""
        # Try to use cache
        cache_key = f"face_recognition_{hash(base64_image[:100])}"
        cached_employee_id = cache.get(cache_key)
        if cached_employee_id:
            return cached_employee_id
        
        try:
            # Decode image
            image = cls.decode_image(base64_image)
            if image is None:
                return None
            
            # Extract face features
            face_roi = cls.extract_face_features(image)
            if face_roi is None:
                return None
            
            # Flatten for comparison
            input_face = face_roi.flatten()
            
            # Get stored faces
            stored_faces = BiometricService.get_employee_face_encodings()
            if not stored_faces:
                logger.warning("No faces found in database")
                return None
            
            # Find best match
            best_match = None
            min_distance = float('inf')
            
            for doc in stored_faces:
                stored_face = doc.get("face_encoding")
                employee_id = doc.get("employee_id")
                
                if stored_face is not None and employee_id is not None:
                    # Convert to numpy array of same shape
                    stored_face = np.array(stored_face).reshape(input_face.shape)
                    
                    # Calculate Euclidean distance
                    distance = np.sum((input_face - stored_face) ** 2)
                    
                    if distance < threshold and distance < min_distance:
                        min_distance = distance
                        best_match = employee_id
            
            if best_match:
                logger.info(f"Face matched with employee ID {best_match}, distance: {min_distance}")
                cache.set(cache_key, best_match, 600)  # Cache for 10 minutes
                return best_match
            
            return None
        except Exception as e:
            logger.error(f"Error recognizing employee: {e}")
            return None