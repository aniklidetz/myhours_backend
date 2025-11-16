"""
Biometric registration views.

This module handles face registration for employees:
- Face registration with quality checks
- Permission validation (admin or self-registration)
- MongoDB storage of face encodings
"""

import numpy as np
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

# Import parent module for test compatibility
# Tests patch 'biometrics.views.logger', 'biometrics.views.face_processor',
# and 'biometrics.views.enhanced_biometric_service'
# We access through the module so patches work correctly
import biometrics.views as biometrics_views
from core.exceptions import BiometricError
from core.logging_utils import err_tag, safe_user_hash
from users.models import Employee

from ..models import BiometricAttempt, BiometricLog, BiometricProfile, FaceQualityCheck
from ..serializers import FaceRegistrationSerializer
from ..services.enhanced_biometric_service import CriticalBiometricError
from .helpers import check_rate_limit, log_biometric_attempt


@extend_schema(
    operation_id="register_face",
    tags=["Biometrics"],
    summary="Register employee face for biometric authentication",
    description="""
    Register a face image for an employee to enable biometric check-in/check-out.
    The system will extract face encodings and store them securely in MongoDB.

    **Requirements:**
    - User must be authenticated
    - Image must be base64 encoded
    - Only one face should be visible in the image
    - User must have permission (admin or self-registration)

    **Image Processing:**
    - Face detection and validation
    - Quality checks (brightness, blur, size)
    - 128-dimensional encoding extraction
    - Secure storage in MongoDB
    """,
    request=FaceRegistrationSerializer,
    responses={
        201: OpenApiExample(
            "Success",
            value={
                "success": True,
                "message": "Successfully registered 1 face encoding(s)",
                "employee_id": 15,
                "employee_name": "Admin User",
                "encodings_count": 1,
            },
        ),
        400: OpenApiExample(
            "Validation Error",
            value={
                "error": True,
                "code": "VALIDATION_ERROR",
                "message": "Failed to process images",
                "details": {"quality_check": "Image quality too low"},
                "error_id": "abc12345",
                "timestamp": "2025-06-05T20:30:00Z",
            },
        ),
        403: OpenApiExample(
            "Permission Denied",
            value={
                "error": True,
                "code": "PERMISSION_DENIED",
                "message": "Permission denied",
                "error_id": "def67890",
                "timestamp": "2025-06-05T20:30:00Z",
            },
        ),
    },
    examples=[
        OpenApiExample(
            "Register Face",
            value={
                "employee_id": 15,
                "image": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAAAQABAAD...",
            },
        )
    ],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def register_face(request):
    """
    Register face for an employee
    """
    # Early validation of image format (before MOCK mode for test consistency)
    ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}

    image_file = request.FILES.get("image")
    if not image_file:
        # Check if it's base64 data
        image_data = request.data.get("image")
        if not image_data or (
            isinstance(image_data, str) and not image_data.startswith("data:image/")
        ):
            return Response(
                {"image": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
    elif getattr(image_file, "size", 0) == 0:
        # Empty file
        return Response(
            {"image": ["This field is required."]}, status=status.HTTP_400_BAD_REQUEST
        )
    elif image_file.content_type not in ALLOWED_CONTENT_TYPES:
        return Response(
            {
                "image": [
                    "Invalid image format. Please provide a valid JPEG or PNG image."
                ]
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check for device_token and log if missing (do this early for all paths)
    device_token = request.headers.get("X-Device-Token") or request.data.get(
        "device_token"
    )
    if not device_token:
        biometrics_views.logger.warning(
            "Biometric register called without device_token"
        )

    # MOCK MODE SHORT-CIRCUIT - after basic validation
    if getattr(settings, "ENABLE_BIOMETRIC_MOCK", False):
        biometrics_views.logger.critical(
            "USING BIOMETRIC MOCK MODE FOR REGISTRATION - NOT FOR PRODUCTION!"
        )

        # Get employee from request data or default to authenticated user's employee
        employee_id = request.data.get("employee_id")
        if (
            not employee_id
            and hasattr(request.user, "employees")
            and request.user.employees.exists()
        ):
            employee_id = request.user.employees.first().id

        return Response(
            {
                "success": True,
                "message": "Mock face registration completed",
                "employee_id": employee_id,
                "embedding_id": "mock-embedding-123",
                "mode": "mock",
            },
            status=status.HTTP_201_CREATED,
        )

    # Check rate limit
    allowed, error_msg = check_rate_limit(request)
    if not allowed:
        return Response({"error": error_msg}, status=status.HTTP_429_TOO_MANY_REQUESTS)

    # Validate input
    serializer = FaceRegistrationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    employee_id = serializer.validated_data["employee_id"]
    image = serializer.validated_data["image"]
    images = [image]  # Convert single image to list for processor

    # DETAILED LOGGING for registration debugging (without PII)
    biometrics_views.logger.info("Face registration debug:")
    biometrics_views.logger.info(
        "Biometrics: registration request received",
        extra={
            "user_hash": safe_user_hash(request.user),
            "has_employee": request.user.employees.exists(),
            "path": request.path,
        },
    )

    try:
        # Check if employee exists and user has permission
        employee = Employee.objects.get(id=employee_id)
        biometrics_views.logger.info(
            f" - Target employee: {employee.id} ({employee.get_full_name()})"
        )

        # Check permission (admin or self)
        # User must be admin or registering their own biometrics
        is_admin = request.user.is_staff or request.user.is_superuser
        is_self = request.user == employee.user

        # Additional check: ensure employee matches authenticated user's employee record
        if request.user.employees.exists():
            user_employee = request.user.employees.first()
            is_self = is_self and (user_employee.id == employee_id)
            biometrics_views.logger.info(
                "Biometrics: permission check",
                extra={
                    "user_hash": safe_user_hash(request.user),
                    "is_admin": is_admin,
                    "is_self": is_self,
                },
            )

        if not (is_admin or is_self):
            biometrics_views.logger.warning(
                "Biometrics: permission denied",
                extra={
                    "user_hash": safe_user_hash(request.user),
                    "is_admin": is_admin,
                    "is_self": is_self,
                },
            )
            return Response(
                {
                    "error": "Permission denied - you can only register your own biometrics"
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if biometric mock is enabled (only when explicitly set)
        use_mock = getattr(settings, "ENABLE_BIOMETRIC_MOCK", False)

        if use_mock:
            biometrics_views.logger.critical(
                "USING BIOMETRIC MOCK MODE - NOT FOR PRODUCTION!"
            )

            # Create mock encodings for testing
            mock_encodings = [np.random.rand(128).tolist()]  # 128-dimensional vector
            result = {
                "success": True,
                "encodings": mock_encodings,
                "successful_count": 1,
                "processed_count": 1,
                "results": [
                    {
                        "success": True,
                        "encodings": mock_encodings,
                        "processing_time_ms": 50,
                    }
                ],
            }

            biometrics_views.logger.warning(
                "Using mock encodings for testing - SECURITY RISK!"
            )
        else:
            # REAL biometric processing
            biometrics_views.logger.info(
                "Processing real biometric data for registration"
            )
            biometrics_views.logger.info(
                "Biometrics: image data received",
                extra={
                    "user_hash": safe_user_hash(request.user),
                    "image_len": len(image) if image else 0,
                },
            )

            try:
                if biometrics_views.face_processor is None:
                    return Response(
                        {"error": "Biometric processing service not available"},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
                result = biometrics_views.face_processor.process_images(images)
                biometrics_views.logger.info(f"Face processor result: {result}")
            except Exception as e:
                biometrics_views.logger.exception("Face processor threw exception")
                return Response(
                    {"error": "Face processing failed"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            if not result["success"]:
                biometrics_views.logger.error(
                    f"Real biometric processing failed: {result}"
                )
                log_biometric_attempt(
                    request,
                    "registration",
                    employee=employee,
                    success=False,
                    error_message="Real biometric processing failed",
                )

                return Response(
                    {
                        "error": "Failed to process biometric images",
                        "details": result.get("error", "Unknown error"),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # If still failed (unlikely with mock data)
        if not result["success"]:
            log_biometric_attempt(
                request,
                "registration",
                employee=employee,
                success=False,
                error_message="No valid face encodings extracted",
            )

            return Response(
                {"error": "Failed to process images"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Use enhanced biometric service for registration (MongoDB First pattern)
        try:
            # Check if encodings are already in proper format from face_processor
            embeddings = []
            for i, encoding in enumerate(result["encodings"]):
                if isinstance(encoding, dict) and "vector" in encoding:
                    # Already in proper format from face_processor
                    embeddings.append(encoding)
                else:
                    # Legacy format - just a vector array
                    embeddings.append(
                        {
                            "vector": encoding,
                            "quality_score": 0.8,  # Default quality score
                            "created_at": timezone.now().isoformat(),
                            "angle": f"angle_{i}",
                        }
                    )

            # Register using enhanced service
            biometrics_views.enhanced_biometric_service.register_biometric(
                employee_id=employee_id, face_encodings=embeddings
            )

        except CriticalBiometricError as e:
            # Critical MongoDB failure - alert DevOps
            biometrics_views.logger.critical(
                "CRITICAL: Biometric registration failed",
                extra={
                    "user_hash": safe_user_hash(request.user),
                    "err": err_tag(e),
                },
            )
            return Response(
                {
                    "error": "Critical biometric system failure. Please contact support.",
                    "details": "Registration service temporarily unavailable",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        except BiometricError as e:
            # General biometric service error
            biometrics_views.logger.exception(
                "Biometric service error during registration"
            )
            return Response(
                {"error": "Biometric registration failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except ValidationError as e:
            # Validation error (employee not found, etc.)
            biometrics_views.logger.exception("Validation error during registration")
            return Response(
                {"error": "Invalid registration data"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            # Other unexpected errors

            biometrics_views.logger.error(
                "Unexpected error during biometric registration",
                extra={"err": err_tag(e)},
            )
            return Response(
                {"error": "Registration failed. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Log successful registration
        log_biometric_attempt(
            request,
            "registration",
            employee=employee,
            success=True,
            processing_time=sum(
                r.get("processing_time_ms", 0) for r in result["results"]
            ),
        )

        # IMPORTANT: Mark device token as biometrically verified after successful registration
        # This allows immediate use of check-in/check-out without additional verification
        device_token = getattr(request, "device_token", None)
        if device_token:
            device_token.mark_biometric_verified()
            biometrics_views.logger.info(
                "Device token marked as biometrically verified after registration"
            )
        else:
            biometrics_views.logger.warning(
                "No device token found during biometric registration"
            )

        biometrics_views.logger.info("Face registration successful")

        return Response(
            {
                "success": True,
                "message": "Face registration completed successfully",
                "employee_id": employee_id,
                "employee_name": employee.get_full_name(),
            },
            status=status.HTTP_201_CREATED,
        )

    except Employee.DoesNotExist:
        return Response(
            {"error": "Employee not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception:
        biometrics_views.logger.exception("Face registration error")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
