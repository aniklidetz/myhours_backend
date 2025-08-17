import base64
import logging
from io import BytesIO

try:
    import cv2
except ImportError:
    cv2 = None
import numpy as np
from PIL import Image

from django.core.cache import cache

from .biometrics import BiometricService

logger = logging.getLogger("biometrics")


class FaceRecognitionService:
    """
    Service for face recognition using OpenCV.
    """

    # Initialize face cascade classifier
    FACE_CASCADE = None
    if cv2 is not None:
        try:
            FACE_CASCADE = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
            if FACE_CASCADE.empty():
                logger.error("Failed to load face cascade classifier")
                FACE_CASCADE = None
        except Exception as e:
            from core.logging_utils import err_tag

            logger.error("Error initializing face cascade", extra={"err": err_tag(e)})
            FACE_CASCADE = None

    @staticmethod
    def decode_image(base64_image):
        """Decode base64 image to OpenCV format"""
        try:
            # Remove data URI prefix if present
            if "," in base64_image:
                base64_image = base64_image.split(",", 1)[1]

            # Decode base64 to bytes
            image_bytes = base64.b64decode(base64_image)

            # Convert to numpy array
            nparr = np.frombuffer(image_bytes, np.uint8)

            # Decode to OpenCV image (BGR format)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if image is None:
                logger.error("Failed to decode image - invalid format")
                return None

            return image
        except Exception as e:
            from core.logging_utils import err_tag

            logger.error("Error decoding image", extra={"err": err_tag(e)})
            return None

    @classmethod
    def extract_face_features(cls, image):
        """Extract face features from an image"""
        try:
            if cls.FACE_CASCADE is None:
                logger.error("Face cascade classifier not initialized")
                return None

            # Convert to grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # Enhance contrast
            gray = cv2.equalizeHist(gray)

            # Detect faces
            faces = cls.FACE_CASCADE.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30),
                flags=cv2.CASCADE_SCALE_IMAGE,
            )

            if len(faces) == 0:
                logger.warning("No faces detected in the image")
                return None

            if len(faces) > 1:
                logger.warning(
                    f"Multiple faces detected ({len(faces)}), using the largest one"
                )

            # Get the largest face
            largest_face = max(faces, key=lambda rect: rect[2] * rect[3])
            x, y, w, h = largest_face

            # Add padding around face
            padding = int(0.1 * min(w, h))
            x = max(0, x - padding)
            y = max(0, y - padding)
            w = min(gray.shape[1] - x, w + 2 * padding)
            h = min(gray.shape[0] - y, h + 2 * padding)

            # Extract face ROI
            face_roi = gray[y : y + h, x : x + w]

            # Resize to standard size for consistent comparison
            face_roi = cv2.resize(face_roi, (100, 100))

            return face_roi
        except Exception as e:
            from core.logging_utils import err_tag

            logger.error("Error extracting face features", extra={"err": err_tag(e)})
            return None

    @classmethod
    def save_employee_face(cls, employee_id, base64_image):
        """Save employee face to database"""
        try:
            logger.info("Starting face registration")

            # Decode image
            image = cls.decode_image(base64_image)
            if image is None:
                logger.error("Failed to decode image for registration")
                return None

            # Extract face features
            face_roi = cls.extract_face_features(image)
            if face_roi is None:
                logger.error("No face detected for registration")
                return None

            # Flatten the face for storage (create face encoding)
            face_encoding = face_roi.flatten().astype(np.float32)

            # Normalize the encoding
            face_encoding = face_encoding / np.linalg.norm(face_encoding)

            # Check if employee already has a face registered
            existing_faces = BiometricService.get_employee_face_encodings(employee_id)
            if existing_faces:
                logger.info("Updating existing face encoding")
                # For updating, we would need to implement an update method
                # For now, delete old and create new
                BiometricService.delete_employee_face_encodings(employee_id)

            # Save to database
            document_id = BiometricService.save_face_encoding(
                employee_id,
                face_encoding,
                base64_image[:1000],  # Store limited image data for reference
            )

            if document_id:
                logger.info("Face successfully saved")
            else:
                logger.error("Failed to save face")

            return document_id
        except Exception as e:
            from core.logging_utils import err_tag

            logger.error("Error saving employee face", extra={"err": err_tag(e)})
            return None

    @classmethod
    def extract_face_embedding(cls, base64_image):
        """Extract face embedding - alias for extract_face_features for test compatibility"""
        return cls.extract_face_features(base64_image)

    @classmethod
    def verify_face(cls, base64_image, employee_id, threshold=0.8):
        """Verify face against stored employee face - for test compatibility"""
        result = cls.recognize_employee(base64_image, threshold)
        if result and result[0] == employee_id:
            return (True, employee_id, result[1])  # (success, employee_id, confidence)
        return (False, None, 0.0)

    @classmethod
    def recognize_employee(cls, base64_image, threshold=0.8):
        """
        Recognize employee from face image

        Args:
            base64_image (str): Base64 encoded image
            threshold (float): Similarity threshold (0-1, higher = more strict)

        Returns:
            int or None: Employee ID if recognized, None otherwise
        """
        # Create a cache key based on image hash
        try:
            image_hash = hash(base64_image[:200])  # Use first 200 chars for hash
            cache_key = f"face_recognition_{abs(image_hash)}"

            # Check cache first
            cached_employee_id = cache.get(cache_key)
            if cached_employee_id:
                logger.info("Found cached recognition result")
                return cached_employee_id

        except Exception as e:
            logger.warning(f"Cache lookup failed: {e}")
            cache_key = None

        try:
            logger.info("Starting face recognition process")

            # Decode image
            image = cls.decode_image(base64_image)
            if image is None:
                logger.error("Failed to decode image for recognition")
                return None

            # Extract face features
            face_roi = cls.extract_face_features(image)
            if face_roi is None:
                logger.error("No face detected in recognition image")
                return None

            # Flatten and normalize for comparison
            input_face = face_roi.flatten().astype(np.float32)
            input_face = input_face / np.linalg.norm(input_face)

            # Get stored faces
            stored_faces = BiometricService.get_employee_face_encodings()
            if not stored_faces:
                logger.warning("No faces found in database")
                return None

            logger.info(f"Comparing with {len(stored_faces)} stored faces")

            # Find best match using cosine similarity
            best_match = None
            best_similarity = 0

            for doc in stored_faces:
                stored_face = doc.get("face_encoding")
                employee_id = doc.get("employee_id")

                if stored_face is not None and employee_id is not None:
                    try:
                        # Convert to numpy array and normalize
                        stored_face = np.array(stored_face, dtype=np.float32)

                        # Ensure same shape
                        if stored_face.shape != input_face.shape:
                            logger.warning("Face shape mismatch detected")
                            continue

                        # Normalize stored face
                        stored_face = stored_face / np.linalg.norm(stored_face)

                        # Calculate cosine similarity
                        similarity = np.dot(input_face, stored_face)

                        logger.debug("Face similarity calculated")

                        if similarity > threshold and similarity > best_similarity:
                            best_similarity = similarity
                            best_match = employee_id

                    except Exception as e:
                        logger.error("Error in face comparison")
                        continue

            if best_match:
                logger.info("Face recognition successful")

                # Cache the result for 10 minutes
                if cache_key:
                    try:
                        cache.set(cache_key, best_match, 600)
                    except Exception as e:
                        logger.warning(f"Failed to cache result: {e}")

                return best_match
            else:
                logger.warning(
                    f"No face match found. Best similarity was {best_similarity} (threshold: {threshold})"
                )
                return None

        except Exception as e:
            from core.logging_utils import err_tag

            logger.error("Error during face recognition", extra={"err": err_tag(e)})
            return None
