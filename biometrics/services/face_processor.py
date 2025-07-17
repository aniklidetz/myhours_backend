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
            is_blurry = laplacian_var < 30  # Lowered threshold for blur
            
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
            logger.exception("Failed to check image quality")
            return {
                'quality_score': 0,
                'passed': False,
                'error': "Image quality check failed"
            }
    
    def detect_faces(self, image: np.ndarray) -> Tuple[List, List]:
        """
        Detect faces in the image with aggressive detection methods
        
        Args:
            image: Numpy array of the image
            
        Returns:
            Tuple of (face_locations, face_landmarks)
        """
        try:
            original_shape = image.shape
            logger.info(f"Starting face detection on image: {original_shape}")
            
            # Try on multiple image sizes for better detection
            working_image = image.copy()
            face_locations = []
            scale_factor = 1.0
            
            # Method 1: Try original size first (if not too large)
            if max(image.shape[:2]) <= 800:
                logger.info("Trying original size detection...")
                try:
                    face_locations = face_recognition.face_locations(working_image, model='hog')
                    logger.info(f"Original size HOG: {len(face_locations)} faces")
                    if not face_locations:
                        face_locations = face_recognition.face_locations(working_image, model='cnn')
                        logger.info(f"Original size CNN: {len(face_locations)} faces")
                except Exception as e:
                    logger.warning(f"Original size detection failed: {e}")
            
            # Method 2: Resize to optimal size (800px max) 
            if not face_locations:
                target_size = 800
                if max(image.shape[:2]) > target_size:
                    scale_factor = target_size / max(image.shape[:2])
                    new_width = int(image.shape[1] * scale_factor)
                    new_height = int(image.shape[0] * scale_factor)
                    working_image = cv2.resize(image, (new_width, new_height))
                    logger.info(f"Resized to {working_image.shape} for detection")
                
                logger.info("Trying resized image HOG detection...")
                try:
                    face_locations = face_recognition.face_locations(working_image, model='hog')
                    logger.info(f"Resized HOG: {len(face_locations)} faces")
                except Exception as e:
                    logger.warning(f"Resized HOG failed: {e}")
            
            # Method 3: Try upsampling on resized image
            if not face_locations:
                logger.info("Trying upsampled detection...")
                try:
                    face_locations = face_recognition.face_locations(working_image, number_of_times_to_upsample=1)
                    logger.info(f"Upsampled: {len(face_locations)} faces")
                except Exception as e:
                    logger.warning(f"Upsampled detection failed: {e}")
            
            # Method 4: CNN on smaller image
            if not face_locations:
                logger.info("Trying CNN detection...")
                try:
                    # Make even smaller for CNN
                    if max(working_image.shape[:2]) > 400:
                        cnn_scale = 400 / max(working_image.shape[:2])
                        cnn_width = int(working_image.shape[1] * cnn_scale)
                        cnn_height = int(working_image.shape[0] * cnn_scale)
                        cnn_image = cv2.resize(working_image, (cnn_width, cnn_height))
                        scale_factor *= cnn_scale
                    else:
                        cnn_image = working_image
                    
                    face_locations = face_recognition.face_locations(cnn_image, model='cnn')
                    logger.info(f"CNN: {len(face_locations)} faces")
                    working_image = cnn_image  # Update working image for scaling
                except Exception as e:
                    logger.warning(f"CNN detection failed: {e}")
                    
            # Method 5: OpenCV cascade as fallback - MORE AGGRESSIVE
            if not face_locations:
                logger.info("Trying OpenCV Haar cascades...")
                try:
                    gray = cv2.cvtColor(working_image, cv2.COLOR_RGB2GRAY)
                    
                    # Try different cascade files
                    cascade_files = [
                        'haarcascade_frontalface_default.xml',
                        'haarcascade_frontalface_alt.xml',
                        'haarcascade_frontalface_alt2.xml'
                    ]
                    
                    for cascade_file in cascade_files:
                        try:
                            cascade_path = cv2.data.haarcascades + cascade_file
                            face_cascade = cv2.CascadeClassifier(cascade_path)
                            
                            # Try different scale factors AND minimum neighbors
                            for scale in [1.05, 1.1, 1.15, 1.2, 1.3, 1.5]:
                                for min_neighbors in [1, 2, 3, 4, 5]:
                                    faces = face_cascade.detectMultiScale(gray, scale, min_neighbors)
                                    if len(faces) > 0:
                                        face_locations = [(y, x + w, y + h, x) for (x, y, w, h) in faces]
                                        logger.info(f"OpenCV {cascade_file} scale {scale} neighbors {min_neighbors}: {len(face_locations)} faces")
                                        break
                                if face_locations:
                                    break
                            if face_locations:
                                break
                        except Exception as e:
                            logger.warning(f"OpenCV cascade {cascade_file} failed: {e}")
                except Exception as e:
                    logger.warning(f"All OpenCV detection failed: {e}")
            
            # Method 6: Try with image enhancement - MULTIPLE ENHANCEMENTS
            if not face_locations:
                logger.info("Trying with enhanced image...")
                try:
                    # Try different enhancement techniques
                    enhancements = [
                        # Contrast and brightness
                        {"alpha": 1.2, "beta": 30, "name": "contrast_bright"},
                        {"alpha": 1.5, "beta": 20, "name": "high_contrast"},
                        {"alpha": 0.8, "beta": 40, "name": "low_contrast_bright"},
                        {"alpha": 1.0, "beta": 50, "name": "brightness_only"}
                    ]
                    
                    for enhancement in enhancements:
                        enhanced = cv2.convertScaleAbs(working_image, alpha=enhancement["alpha"], beta=enhancement["beta"])
                        
                        # Try both HOG and OpenCV on enhanced image
                        face_locations = face_recognition.face_locations(enhanced, model='hog')
                        if face_locations:
                            logger.info(f"Enhanced image {enhancement['name']} HOG: {len(face_locations)} faces")
                            working_image = enhanced
                            break
                        
                        # Try OpenCV on enhanced image
                        gray_enhanced = cv2.cvtColor(enhanced, cv2.COLOR_RGB2GRAY)
                        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
                        faces = face_cascade.detectMultiScale(gray_enhanced, 1.1, 2)
                        if len(faces) > 0:
                            face_locations = [(y, x + w, y + h, x) for (x, y, w, h) in faces]
                            logger.info(f"Enhanced image {enhancement['name']} OpenCV: {len(face_locations)} faces")
                            working_image = enhanced
                            break
                            
                except Exception as e:
                    logger.warning(f"Enhanced detection failed: {e}")
            
            # Method 7: Histogram equalization
            if not face_locations:
                logger.info("Trying histogram equalization...")
                try:
                    gray = cv2.cvtColor(working_image, cv2.COLOR_RGB2GRAY)
                    equalized = cv2.equalizeHist(gray)
                    equalized_rgb = cv2.cvtColor(equalized, cv2.COLOR_GRAY2RGB)
                    
                    face_locations = face_recognition.face_locations(equalized_rgb, model='hog')
                    if face_locations:
                        logger.info(f"Histogram equalized: {len(face_locations)} faces")
                        working_image = equalized_rgb
                    else:
                        # Try OpenCV on histogram equalized
                        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
                        faces = face_cascade.detectMultiScale(equalized, 1.1, 2)
                        if len(faces) > 0:
                            face_locations = [(y, x + w, y + h, x) for (x, y, w, h) in faces]
                            logger.info(f"Histogram equalized OpenCV: {len(face_locations)} faces")
                            working_image = equalized_rgb
                except Exception as e:
                    logger.warning(f"Histogram equalization failed: {e}")
            
            # Scale face_locations back to original size
            if face_locations and scale_factor != 1.0:
                scale_back = 1.0 / scale_factor
                scaled_locations = []
                for (top, right, bottom, left) in face_locations:
                    scaled_locations.append((
                        int(top * scale_back),
                        int(right * scale_back), 
                        int(bottom * scale_back),
                        int(left * scale_back)
                    ))
                face_locations = scaled_locations
                logger.info(f"Scaled face locations back by factor {scale_back}")
            
            # Get face landmarks if faces found
            face_landmarks = []
            if face_locations:
                try:
                    face_landmarks = face_recognition.face_landmarks(working_image, 
                        [(int(top/scale_factor), int(right/scale_factor), int(bottom/scale_factor), int(left/scale_factor)) 
                         for top, right, bottom, left in face_locations] if scale_factor != 1.0 else face_locations)
                except Exception as e:
                    logger.warning(f"Failed to get face landmarks: {e}")
                    face_landmarks = []
            
            logger.info(f"FINAL DETECTION RESULT: {len(face_locations)} faces found")
            if face_locations:
                for i, (top, right, bottom, left) in enumerate(face_locations):
                    face_width = right - left
                    face_height = bottom - top
                    logger.info(f"Face {i+1}: size {face_width}x{face_height}, position ({left},{top})")
            
            return face_locations, face_landmarks
            
        except Exception as e:
            logger.exception(f"Face detection completely failed: {e}")
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
        logger.info("Starting biometric image processing")
        
        # Decode image
        logger.info(f"Decoding base64 image (length: {len(base64_image)})")
        image = self.decode_base64_image(base64_image)
        if image is None:
            logger.error("Failed to decode base64 image")
            return {
                'success': False,
                'error': 'Failed to decode image'
            }
        
        logger.info(f"Image decoded successfully: shape={image.shape}")
        
        # Check image quality
        logger.info("Checking image quality")
        quality_check = self.check_image_quality(image)
        logger.info(f"Quality check result: {quality_check}")
        if not quality_check['passed']:
            logger.error(f"Image quality too low: {quality_check}")
            return {
                'success': False,
                'error': 'Image quality too low',
                'quality_check': quality_check
            }
        
        # Detect faces
        logger.info("Detecting faces in image")
        face_locations, face_landmarks = self.detect_faces(image)
        logger.info(f"Face detection result: {len(face_locations)} faces found")
        
        if not face_locations:
            logger.error("No face detected in image")
            return {
                'success': False,
                'error': 'No face detected',
                'quality_check': quality_check
            }
        
        if len(face_locations) > 1:
            logger.error(f"Multiple faces detected: {len(face_locations)}")
            return {
                'success': False,
                'error': 'Multiple faces detected',
                'face_count': len(face_locations),
                'quality_check': quality_check
            }
        
        # Extract face encoding
        logger.info("Extracting face encoding")
        face_location = face_locations[0]
        encoding = self.extract_face_encoding(image, face_location)
        
        if encoding is None:
            logger.error("Failed to extract face encoding")
            return {
                'success': False,
                'error': 'Failed to extract face encoding'
            }
        
        logger.info(f"Face encoding extracted successfully: shape={encoding.shape}")
        
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
    
    def process_images(self, base64_images: List[str]) -> Dict[str, Any]:
        """
        Process images for registration (alias for process_multiple_images)
        
        Args:
            base64_images: List of base64 encoded images
            
        Returns:
            Dictionary with processing results
        """
        return self.process_multiple_images(base64_images)
    
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