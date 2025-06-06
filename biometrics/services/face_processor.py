# biometrics/services/face_processor.py
import base64
import io
import logging
import time
from typing import List, Dict, Optional, Tuple, Any
import numpy as np
from PIL import Image
import face_recognition
import cv2
from django.conf import settings

logger = logging.getLogger(__name__)


class FaceProcessor:
    """Service for processing face images and extracting embeddings"""
    
    def __init__(self):
        self.tolerance = getattr(settings, 'FACE_RECOGNITION_TOLERANCE', 0.6)
        self.model = getattr(settings, 'FACE_ENCODING_MODEL', 'large')
        self.min_face_size = getattr(settings, 'MIN_FACE_SIZE', (50, 50))
        self.quality_threshold = getattr(settings, 'FACE_QUALITY_THRESHOLD', 0.7)
    
    def decode_base64_image(self, base64_string: str) -> Optional[np.ndarray]:
        """
        Decode base64 image string to numpy array
        
        Args:
            base64_string: Base64 encoded image
            
        Returns:
            Numpy array of the image or None if failed
        """
        try:
            # Remove data URI prefix if present
            if ',' in base64_string:
                base64_string = base64_string.split(',')[1]
            
            # Decode base64
            image_data = base64.b64decode(base64_string)
            
            # Convert to PIL Image
            image = Image.open(io.BytesIO(image_data))
            
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Convert to numpy array
            return np.array(image)
            
        except Exception as e:
            logger.error(f"Failed to decode base64 image: {e}")
            return None
    
    def check_image_quality(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Check image quality metrics
        
        Args:
            image: Numpy array of the image
            
        Returns:
            Dictionary with quality metrics
        """
        try:
            # Convert to grayscale for analysis
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            
            # Check brightness
            brightness = np.mean(gray)
            is_too_dark = brightness < 50
            is_too_bright = brightness > 200
            
            # Check blur using Laplacian variance
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            is_blurry = laplacian_var < 100
            
            # Calculate overall quality score
            quality_score = 1.0
            if is_too_dark or is_too_bright:
                quality_score *= 0.7
            if is_blurry:
                quality_score *= 0.8
            
            return {
                'brightness': float(brightness),
                'blur_score': float(laplacian_var),
                'is_too_dark': is_too_dark,
                'is_too_bright': is_too_bright,
                'is_blurry': is_blurry,
                'quality_score': quality_score,
                'passed': quality_score >= self.quality_threshold
            }
            
        except Exception as e:
            logger.error(f"Failed to check image quality: {e}")
            return {
                'quality_score': 0,
                'passed': False,
                'error': str(e)
            }
    
    def detect_faces(self, image: np.ndarray) -> Tuple[List, List]:
        """
        Detect faces in the image
        
        Args:
            image: Numpy array of the image
            
        Returns:
            Tuple of (face_locations, face_landmarks)
        """
        try:
            # Detect face locations
            face_locations = face_recognition.face_locations(
                image,
                model='hog'  # 'hog' is faster, 'cnn' is more accurate
            )
            
            # Get face landmarks for quality checking
            face_landmarks = []
            if face_locations:
                face_landmarks = face_recognition.face_landmarks(image, face_locations)
            
            return face_locations, face_landmarks
            
        except Exception as e:
            logger.error(f"Failed to detect faces: {e}")
            return [], []
    
    def extract_face_encoding(self, image: np.ndarray, face_location: Tuple) -> Optional[np.ndarray]:
        """
        Extract face encoding from a specific face location
        
        Args:
            image: Numpy array of the image
            face_location: Tuple of (top, right, bottom, left)
            
        Returns:
            128-dimensional face encoding or None
        """
        try:
            # Extract face encoding
            encodings = face_recognition.face_encodings(
                image,
                known_face_locations=[face_location],
                model=self.model
            )
            
            if encodings:
                return encodings[0]
            return None
            
        except Exception as e:
            logger.error(f"Failed to extract face encoding: {e}")
            return None
    
    def process_registration_image(self, base64_image: str) -> Dict[str, Any]:
        """
        Process a single image for registration
        
        Args:
            base64_image: Base64 encoded image
            
        Returns:
            Dictionary with processing results
        """
        start_time = time.time()
        
        # Decode image
        image = self.decode_base64_image(base64_image)
        if image is None:
            return {
                'success': False,
                'error': 'Failed to decode image'
            }
        
        # Check image quality
        quality_check = self.check_image_quality(image)
        if not quality_check['passed']:
            return {
                'success': False,
                'error': 'Image quality too low',
                'quality_check': quality_check
            }
        
        # Detect faces
        face_locations, face_landmarks = self.detect_faces(image)
        
        if not face_locations:
            return {
                'success': False,
                'error': 'No face detected',
                'quality_check': quality_check
            }
        
        if len(face_locations) > 1:
            return {
                'success': False,
                'error': 'Multiple faces detected',
                'face_count': len(face_locations),
                'quality_check': quality_check
            }
        
        # Extract face encoding
        face_location = face_locations[0]
        encoding = self.extract_face_encoding(image, face_location)
        
        if encoding is None:
            return {
                'success': False,
                'error': 'Failed to extract face encoding'
            }
        
        # Calculate face size ratio
        top, right, bottom, left = face_location
        face_width = right - left
        face_height = bottom - top
        image_height, image_width = image.shape[:2]
        face_size_ratio = (face_width * face_height) / (image_width * image_height)
        
        # Check if eyes are visible (basic check)
        has_eyes = False
        if face_landmarks:
            has_eyes = 'left_eye' in face_landmarks[0] and 'right_eye' in face_landmarks[0]
        
        processing_time = int((time.time() - start_time) * 1000)
        
        return {
            'success': True,
            'encoding': encoding.tolist(),  # Convert to list for JSON serialization
            'quality_check': quality_check,
            'face_location': face_location,
            'face_size_ratio': face_size_ratio,
            'has_eyes': has_eyes,
            'processing_time_ms': processing_time
        }
    
    def process_multiple_images(self, base64_images: List[str]) -> Dict[str, Any]:
        """
        Process multiple images for registration
        
        Args:
            base64_images: List of base64 encoded images
            
        Returns:
            Dictionary with processing results
        """
        results = []
        successful_encodings = []
        
        for idx, base64_image in enumerate(base64_images):
            result = self.process_registration_image(base64_image)
            results.append(result)
            
            if result['success']:
                successful_encodings.append({
                    'vector': result['encoding'],
                    'quality_score': result['quality_check']['quality_score'],
                    'created_at': np.datetime64('now').tolist(),
                    'angle': f'angle_{idx}'  # You can improve this with actual angle detection
                })
        
        return {
            'success': len(successful_encodings) > 0,
            'encodings': successful_encodings,
            'processed_count': len(base64_images),
            'successful_count': len(successful_encodings),
            'results': results
        }
    
    def compare_faces(self, unknown_encoding: np.ndarray, known_encodings: List[np.ndarray]) -> Tuple[bool, float]:
        """
        Compare an unknown face encoding with known encodings
        
        Args:
            unknown_encoding: Encoding of the face to check
            known_encodings: List of known face encodings
            
        Returns:
            Tuple of (match_found, best_distance)
        """
        if not known_encodings:
            return False, 1.0
        
        try:
            # Calculate face distances
            distances = face_recognition.face_distance(known_encodings, unknown_encoding)
            
            # Find the best match
            best_distance = min(distances)
            best_match_index = np.argmin(distances)
            
            # Check if it's a match based on tolerance
            is_match = best_distance <= self.tolerance
            
            # Convert distance to confidence score (0-1, where 1 is perfect match)
            confidence = 1 - best_distance
            
            return is_match, float(confidence)
            
        except Exception as e:
            logger.error(f"Failed to compare faces: {e}")
            return False, 0.0
    
    def find_matching_employee(self, base64_image: str, all_embeddings: List[Tuple[int, List[Dict]]]) -> Dict[str, Any]:
        """
        Find matching employee from a face image
        
        Args:
            base64_image: Base64 encoded image
            all_embeddings: List of tuples (employee_id, embeddings)
            
        Returns:
            Dictionary with matching results
        """
        start_time = time.time()
        
        # Process the input image
        result = self.process_registration_image(base64_image)
        if not result['success']:
            return {
                'success': False,
                'error': result.get('error', 'Failed to process image'),
                'details': result
            }
        
        unknown_encoding = np.array(result['encoding'])
        
        # Compare with all known embeddings
        best_match_employee_id = None
        best_confidence = 0.0
        
        for employee_id, employee_embeddings in all_embeddings:
            # Extract encoding vectors
            known_encodings = []
            for embedding in employee_embeddings:
                if 'vector' in embedding:
                    known_encodings.append(np.array(embedding['vector']))
            
            if not known_encodings:
                continue
            
            # Compare with this employee's encodings
            is_match, confidence = self.compare_faces(unknown_encoding, known_encodings)
            
            if is_match and confidence > best_confidence:
                best_match_employee_id = employee_id
                best_confidence = confidence
        
        processing_time = int((time.time() - start_time) * 1000)
        
        if best_match_employee_id:
            return {
                'success': True,
                'employee_id': best_match_employee_id,
                'confidence': best_confidence,
                'processing_time_ms': processing_time,
                'quality_check': result['quality_check']
            }
        else:
            return {
                'success': False,
                'error': 'No matching employee found',
                'processing_time_ms': processing_time,
                'quality_check': result['quality_check']
            }


# Global instance
face_processor = FaceProcessor()