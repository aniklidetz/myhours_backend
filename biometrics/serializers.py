# biometrics/serializers.py
from rest_framework import serializers
from users.models import Employee

class FaceRegistrationSerializer(serializers.Serializer):
    """Serializer for face registration"""
    employee_id = serializers.IntegerField(
        help_text="ID of the employee to register"
    )
    image = serializers.CharField(
        help_text="Base64 encoded image data"
    )
    
    def validate_employee_id(self, value):
        """Validate that employee exists and is active"""
        try:
            employee = Employee.objects.get(id=value, is_active=True)
            return value
        except Employee.DoesNotExist:
            raise serializers.ValidationError(
                f"Active employee with ID {value} does not exist"
            )
    
    def validate_image(self, value):
        """Enhanced validation for base64 image data"""
        if not value:
            raise serializers.ValidationError("Image data is required")
        
        # Remove data URI prefix if present
        if value.startswith('data:image'):
            if ',' not in value:
                raise serializers.ValidationError("Invalid data URI format")
            header, value = value.split(',', 1)
            # Validate image type
            if not any(img_type in header for img_type in ['jpeg', 'jpg', 'png', 'webp']):
                raise serializers.ValidationError("Only JPEG, PNG, and WebP images are supported")
        
        # Check minimum length
        if len(value) < 100:
            raise serializers.ValidationError("Image data appears to be too short")
        
        # Validate base64 encoding
        import base64
        try:
            # Decode the entire image to ensure it's valid
            decoded = base64.b64decode(value, validate=True)
            # Check if decoded data looks like an image (basic check)
            if len(decoded) < 100:
                raise serializers.ValidationError("Decoded image data is too small")
            # Check for common image file signatures
            if not (decoded[:2] == b'\xff\xd8' or  # JPEG
                    decoded[:8] == b'\x89PNG\r\n\x1a\n' or  # PNG
                    decoded[:4] == b'RIFF' and decoded[8:12] == b'WEBP'):  # WebP
                raise serializers.ValidationError("Image data does not appear to be a valid image format")
        except base64.binascii.Error:
            raise serializers.ValidationError("Invalid base64 encoding")
        except Exception as e:
            raise serializers.ValidationError(f"Image validation failed: {str(e)}")
        
        return value

class FaceRecognitionSerializer(serializers.Serializer):
    """Serializer for face recognition check-in/check-out"""
    image = serializers.CharField(
        help_text="Base64 encoded image data"
    )
    location = serializers.CharField(
        max_length=255,
        required=False,
        default='',
        help_text="Location where check-in/check-out occurred"
    )
    
    def validate_image(self, value):
        """Enhanced validation for base64 image data"""
        if not value:
            raise serializers.ValidationError("Image data is required")
        
        # Remove data URI prefix if present
        if value.startswith('data:image'):
            if ',' not in value:
                raise serializers.ValidationError("Invalid data URI format")
            header, value = value.split(',', 1)
            # Validate image type
            if not any(img_type in header for img_type in ['jpeg', 'jpg', 'png', 'webp']):
                raise serializers.ValidationError("Only JPEG, PNG, and WebP images are supported")
        
        # Check minimum length
        if len(value) < 100:
            raise serializers.ValidationError("Image data appears to be too short")
        
        # Basic base64 validation (lighter than full decode for performance)
        import base64
        try:
            # Test decode a small portion to validate format
            base64.b64decode(value[:1000], validate=True)
        except base64.binascii.Error:
            raise serializers.ValidationError("Invalid base64 encoding")
        
        return value

class BiometricResponseSerializer(serializers.Serializer):
    """Serializer for biometric API responses"""
    success = serializers.BooleanField()
    message = serializers.CharField()
    employee_id = serializers.IntegerField(required=False)
    employee_name = serializers.CharField(required=False)
    worklog_id = serializers.IntegerField(required=False)
    document_id = serializers.CharField(required=False)
    check_in_time = serializers.DateTimeField(required=False)
    check_out_time = serializers.DateTimeField(required=False)
    hours_worked = serializers.FloatField(required=False)

class BiometricStatsSerializer(serializers.Serializer):
    """Serializer for biometric statistics"""
    total_face_encodings = serializers.IntegerField()
    unique_employees = serializers.IntegerField()
    recent_uploads = serializers.IntegerField()
    collection_name = serializers.CharField()
    error = serializers.CharField(required=False)