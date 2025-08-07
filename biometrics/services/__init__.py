# Conditional imports for CI compatibility
try:
    from .face_recognition_service import FaceRecognitionService  # noqa: F401
except ImportError:
    # Mock for CI environment where cv2/face_recognition aren't available
    FaceRecognitionService = None
