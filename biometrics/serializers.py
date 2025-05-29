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
        """Basic validation for base64 image"""
        if not value:
            raise serializers.ValidationError("Image data is required")
        
        # Check if it looks like base64 data
        if len(value) < 100:
            raise serializers.ValidationError("Image data appears to be too short")
        
        # Remove data URI prefix for validation
        if ',' in value:
            value = value.split(',')[1]
        
        # Basic base64 validation
        import base64
        try:
            base64.b64decode(value[:100])  # Test decode small portion
        except Exception:
            raise serializers.ValidationError("Invalid base64 image data")
        
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
        """Basic validation for base64 image"""
        if not value:
            raise serializers.ValidationError("Image data is required")
        
        # Check if it looks like base64 data
        if len(value) < 100:
            raise serializers.ValidationError("Image data appears to be too short")
        
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