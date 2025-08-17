"""
Safe domain exceptions for biometrics module

These exceptions provide safe error messages for logging while maintaining
backward compatibility with existing tests.
"""


class BiometricServiceError(Exception):
    """Base exception for biometric service errors"""
    
    def __init__(self, message: str, safe_message: str = None):
        super().__init__(message)
        self.safe_message = safe_message or "BiometricServiceError"


class MongoConnectionError(BiometricServiceError):
    """MongoDB connection related errors"""
    
    def __init__(self, message: str):
        super().__init__(message, "MongoConnectionError")


class MongoOperationError(BiometricServiceError):
    """MongoDB operation related errors"""
    
    def __init__(self, message: str):
        super().__init__(message, "MongoOperationError")


class BiometricDataError(BiometricServiceError):
    """Biometric data processing errors"""
    
    def __init__(self, message: str):
        super().__init__(message, "BiometricDataError")


class FaceProcessingError(BiometricServiceError):
    """Face processing related errors"""
    
    def __init__(self, message: str):
        super().__init__(message, "FaceProcessingError")