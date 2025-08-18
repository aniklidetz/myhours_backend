import logging
from datetime import timedelta

import numpy as np
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.exceptions import BiometricError
from core.logging_utils import err_tag, safe_user_hash
from users.models import Employee
from users.permissions import IsEmployeeOrAbove
from worktime.models import WorkLog

from .models import BiometricAttempt, BiometricLog, BiometricProfile, FaceQualityCheck
from .serializers import FaceRecognitionSerializer, FaceRegistrationSerializer
from .services.enhanced_biometric_service import (
    CriticalBiometricError,
    enhanced_biometric_service,
)

try:
    from .services.face_processor import face_processor
except ImportError:
    face_processor = None
from .services.mongodb_service import get_mongodb_service

logger = logging.getLogger("biometrics.views")


def get_client_ip(request):
    """Extract client IP from request"""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def check_rate_limit(request):
    """Check if IP is rate limited"""
    ip_address = get_client_ip(request)

    try:
        attempt = BiometricAttempt.objects.get(ip_address=ip_address)
        if attempt.is_blocked():
            return False, "Too many failed attempts. Please try again later."
        return True, None
    except BiometricAttempt.DoesNotExist:
        return True, None


def log_biometric_attempt(
    request,
    action,
    employee=None,
    success=False,
    confidence_score=None,
    error_message=None,
    processing_time=None,
):
    """Log biometric attempt"""
    try:
        log = BiometricLog.objects.create(
            employee=employee,
            action=action,
            confidence_score=confidence_score,
            location=request.data.get("location", ""),
            device_info=request.data.get("device_info", {}),
            ip_address=get_client_ip(request),
            success=success,
            error_message=error_message or "",
            processing_time_ms=processing_time,
        )
        return log
    except Exception:
        logger.exception("Failed to log biometric attempt")
        return None


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
        logger.warning("Biometric register called without device_token")

    # MOCK MODE SHORT-CIRCUIT - after basic validation
    if getattr(settings, "ENABLE_BIOMETRIC_MOCK", False):
        logger.critical(
            "🚨 USING BIOMETRIC MOCK MODE FOR REGISTRATION - NOT FOR PRODUCTION!"
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
    logger.info("🔍 Face registration debug:")
    logger.info(
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
        logger.info(f"   - Target employee: {employee.id} ({employee.get_full_name()})")

        # Check permission (admin or self)
        # User must be admin or registering their own biometrics
        is_admin = request.user.is_staff or request.user.is_superuser
        is_self = request.user == employee.user

        # Additional check: ensure employee matches authenticated user's employee record
        if request.user.employees.exists():
            user_employee = request.user.employees.first()
            is_self = is_self and (user_employee.id == employee_id)
            logger.info(
                "Biometrics: permission check",
                extra={
                    "user_hash": safe_user_hash(request.user),
                    "is_admin": is_admin,
                    "is_self": is_self,
                },
            )

        if not (is_admin or is_self):
            logger.warning(
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
            logger.critical("🚨 USING BIOMETRIC MOCK MODE - NOT FOR PRODUCTION!")

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

            logger.warning("Using mock encodings for testing - SECURITY RISK!")
        else:
            # REAL biometric processing
            logger.info("Processing real biometric data for registration")
            logger.info(
                "Biometrics: image data received",
                extra={
                    "user_hash": safe_user_hash(request.user),
                    "image_len": len(image) if image else 0,
                },
            )

            try:
                if face_processor is None:
                    return Response(
                        {"error": "Biometric processing service not available"},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
                result = face_processor.process_images(images)
                logger.info(f"Face processor result: {result}")
            except Exception as e:
                logger.exception("Face processor threw exception")
                return Response(
                    {"error": "Face processing failed"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            if not result["success"]:
                logger.error(f"Real biometric processing failed: {result}")
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
            enhanced_biometric_service.register_biometric(
                employee_id=employee_id, face_encodings=embeddings
            )

        except CriticalBiometricError as e:
            # Critical MongoDB failure - alert DevOps
            logger.critical(
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
            logger.exception("Biometric service error during registration")
            return Response(
                {"error": "Biometric registration failed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except ValidationError as e:
            # Validation error (employee not found, etc.)
            logger.exception("Validation error during registration")
            return Response(
                {"error": "Invalid registration data"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            # Other unexpected errors
            from core.logging_utils import err_tag

            logger.error(
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
            logger.info(
                "Device token marked as biometrically verified after registration"
            )
        else:
            logger.warning("No device token found during biometric registration")

        logger.info("Face registration successful")

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
        logger.exception("Face registration error")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@extend_schema(
    operation_id="biometric_check_in",
    tags=["Biometrics"],
    summary="Biometric check-in for work time tracking",
    description="""
    Perform biometric face recognition to check-in for work.
    The system will compare the provided face image with registered employee faces.
    
    **Process:**
    1. Capture face image from camera
    2. Extract face encoding from image
    3. Compare with all registered employee faces
    4. Create WorkLog entry if match found
    5. Log biometric attempt for security
    
    **Requirements:**
    - User must be authenticated
    - Image must contain a clear face
    - Employee must not already be checked in
    - Face must match a registered employee
    
    **Fallback Behavior:**
    In development/testing, if face recognition fails, the system will use
    a test employee to demonstrate the workflow.
    """,
    request=FaceRecognitionSerializer,
    responses={
        200: OpenApiExample(
            "Check-in Success",
            value={
                "success": True,
                "employee_id": 15,
                "employee_name": "Admin User",
                "check_in_time": "2025-06-05T20:33:59.759251Z",
                "location": "Office (32.050939, 34.781791)",
                "confidence": 0.95,
                "worklog_id": 13,
            },
        ),
        400: OpenApiExample(
            "Already Checked In",
            value={
                "error": True,
                "code": "VALIDATION_ERROR",
                "message": "Already checked in",
                "details": {"check_in_time": "2025-06-05T20:15:21.783522Z"},
                "error_id": "xyz98765",
                "timestamp": "2025-06-05T20:30:00Z",
            },
        ),
    },
    examples=[
        OpenApiExample(
            "Check-in Request",
            value={
                "image": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAAAQABAAD...",
                "location": "Office Main Entrance",
            },
        )
    ],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def check_in(request):
    """
    Biometric check-in
    """
    # Early validation of image (before MOCK mode for test consistency)
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

    # MOCK MODE SHORT-CIRCUIT - after basic validation
    if getattr(settings, "ENABLE_BIOMETRIC_MOCK", False):
        logger.critical(
            "🚨 USING BIOMETRIC MOCK MODE FOR CHECK-IN - NOT FOR PRODUCTION!"
        )

        if hasattr(request.user, "employees") and request.user.employees.exists():
            employee = request.user.employees.first()
            return Response(
                {
                    "success": True,
                    "message": "Mock biometric check-in completed",
                    "employee_id": employee.id,
                    "check_in_time": timezone.now(),
                    "location": request.data.get("location", "Mock Office"),
                    "mode": "mock",
                },
                status=status.HTTP_201_CREATED,
            )

    try:
        # Check rate limit
        allowed, error_msg = check_rate_limit(request)
        if not allowed:
            return Response(
                {"error": error_msg}, status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # Validate input
        serializer = FaceRecognitionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        image = serializer.validated_data["image"]
        location = serializer.validated_data.get("location", "")

        # Get all active embeddings
        all_embeddings = get_mongodb_service().get_all_active_embeddings()

        if not all_embeddings:
            return Response(
                {"error": "No registered faces in the system"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Flag to track if we used fallback testing mode
        used_fallback = False

        # Check if biometric mock is enabled (only for development/testing)
        if settings.ENABLE_BIOMETRIC_MOCK:
            if request.user.employees.exists():
                logger.critical(
                    "USING BIOMETRIC MOCK MODE FOR CHECK-IN - NOT FOR PRODUCTION!"
                )
                test_employee = request.user.employees.first()
                match_result = {
                    "success": True,
                    "employee_id": test_employee.id,
                    "confidence": 0.95,  # Mock confidence
                    "processing_time_ms": 50,  # Fast mock processing
                }
                used_fallback = True
                logger.warning(
                    f"Using mock check-in for employee {test_employee.id} - SECURITY RISK!"
                )
            else:
                logger.error("Mock mode enabled but user has no employee profile")
                return Response(
                    {"error": "User has no employee profile"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            # REAL biometric processing
            logger.info("Processing real biometric data for check-in")
            if face_processor is None:
                return Response(
                    {"error": "Biometric processing service not available"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            match_result = face_processor.find_matching_employee(image, all_embeddings)

            if not match_result["success"]:
                # Real face recognition failed
                log_biometric_attempt(
                    request,
                    "check_in",
                    success=False,
                    error_message="Real biometric face recognition failed",
                    processing_time=match_result.get("processing_time_ms"),
                )

                return Response(
                    {
                        "success": False,
                        "error": "Face recognition failed - no matching employee found",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Get employee
        employee = Employee.objects.get(id=match_result["employee_id"])

        # DETAILED LOGGING for mismatch debugging (without PII)
        logger.info("Check-in matching debug")
        logger.info(
            "Biometrics: check-in match found",
            extra={
                "user_hash": safe_user_hash(request.user),
                "confidence": match_result["confidence"],
                "used_fallback": used_fallback,
                "has_employee": request.user.employees.exists(),
            },
        )
        if not request.user.employees.exists():
            logger.warning("   - No employee found for authenticated user")

        # IMPORTANT: Verify that the recognized face belongs to the authenticated user
        # This ensures multiple employees can check-in simultaneously
        # Skip this check if we used fallback mode (already authenticated user)
        if (
            not used_fallback
            and request.user.employees.exists()
            and request.user.employees.first() != employee
        ):
            logger.warning("Face recognition mismatch detected")
            logger.warning(
                f"   - Expected employee: {request.user.employees.first().id} ({request.user.employees.first().get_full_name()})"
            )
            logger.warning(
                f"   - Recognized employee: {employee.id} ({employee.get_full_name()})"
            )
            return Response(
                {
                    "success": False,
                    "error": "Face does not match authenticated user",
                    "details": "Please ensure you are logged in with your own account",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check if already checked in
        existing_worklog = WorkLog.objects.filter(
            employee=employee, check_out__isnull=True
        ).first()

        if existing_worklog:
            return Response(
                {
                    "success": False,
                    "error": "Already checked in",
                    "check_in_time": existing_worklog.check_in,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create work log
        try:
            with transaction.atomic():
                worklog = WorkLog.objects.create(
                    employee=employee,
                    check_in=timezone.now(),
                    location_check_in=location,
                )

            # Log successful check-in
            log = log_biometric_attempt(
                request,
                "check_in",
                employee=employee,
                success=True,
                confidence_score=match_result["confidence"],
                processing_time=match_result["processing_time_ms"],
            )

            # Save quality check
            if log and "quality_check" in match_result:
                quality = match_result["quality_check"]
                FaceQualityCheck.objects.create(
                    biometric_log=log,
                    face_detected=True,
                    face_count=1,
                    brightness_score=quality.get("brightness"),
                    blur_score=quality.get("blur_score"),
                    face_size_ratio=match_result.get("face_size_ratio", 0),
                    eye_visibility=match_result.get("has_eyes", False),
                )

                # Reset failed attempts
                try:
                    attempt = BiometricAttempt.objects.get(
                        ip_address=get_client_ip(request)
                    )
                    attempt.reset_attempts()
                except BiometricAttempt.DoesNotExist:
                    pass

        except Exception as worklog_error:
            logger.exception("Failed to create worklog")
            return Response(
                {"error": "Failed to create work log"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        logger.info("Check-in successful")

        return Response(
            {
                "success": True,
                "employee_id": employee.id,
                "employee_name": employee.get_full_name(),
                "check_in_time": worklog.check_in,
                "location": location,
                "confidence": round(match_result["confidence"], 2),
                "worklog_id": worklog.id,
            },
            status=status.HTTP_201_CREATED,
        )

    except Employee.DoesNotExist:
        return Response(
            {"error": "Employee record not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception:
        logger.exception("Check-in error")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def check_out(request):
    """
    Biometric check-out
    """
    # MOCK MODE with business logic validation
    if getattr(settings, "ENABLE_BIOMETRIC_MOCK", False):
        logger.critical("USING BIOMETRIC MOCK MODE FOR CHECK-OUT - NOT FOR PRODUCTION!")

        if hasattr(request.user, "employees") and request.user.employees.exists():
            employee = request.user.employees.first()

            # Check for active check-in (business logic validation)
            worklog = WorkLog.objects.filter(
                employee=employee, check_out__isnull=True
            ).first()

            if not worklog:
                return Response(
                    {"success": False, "error": "No active check-in found"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return Response(
                {
                    "success": True,
                    "message": "Mock biometric check-out completed",
                    "employee_id": employee.id,
                    "check_out_time": timezone.now(),
                    "location": request.data.get("location", "Mock Office"),
                    "mode": "mock",
                },
                status=status.HTTP_200_OK,
            )

    # Check rate limit
    allowed, error_msg = check_rate_limit(request)
    if not allowed:
        return Response({"error": error_msg}, status=status.HTTP_429_TOO_MANY_REQUESTS)

    # Validate input
    serializer = FaceRecognitionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    image = serializer.validated_data["image"]
    location = serializer.validated_data.get("location", "")

    try:

        # Flag to track if we used fallback testing mode
        used_fallback = False

        # Check if biometric mock is enabled (only for development/testing)
        if settings.ENABLE_BIOMETRIC_MOCK and request.user.employees.exists():
            logger.critical(
                "USING BIOMETRIC MOCK MODE FOR CHECK-OUT - NOT FOR PRODUCTION!"
            )
            test_employee = request.user.employees.first()
            match_result = {
                "success": True,
                "employee_id": test_employee.id,
                "confidence": 0.95,  # Mock confidence
                "processing_time_ms": 50,  # Fast mock processing
            }
            used_fallback = True
            logger.warning("Using mock check-out - SECURITY RISK!")
        else:
            # REAL biometric processing using enhanced service
            logger.info("Processing real biometric data for check-out")
            try:
                # Process image to get face encoding
                if face_processor is None:
                    return Response(
                        {"error": "Biometric processing service not available"},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
                result = face_processor.process_registration_image(image)
                if not result["success"]:
                    return Response(
                        {
                            "success": False,
                            "error": result.get(
                                "error", "Failed to process face image"
                            ),
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Use enhanced service for verification
                face_encoding = result["encoding"]
                verification_result = enhanced_biometric_service.verify_biometric(
                    face_encoding
                )

                if verification_result:
                    employee_id, confidence = verification_result
                    match_result = {
                        "success": True,
                        "employee_id": employee_id,
                        "confidence": confidence,
                        "processing_time_ms": result.get("processing_time_ms", 0),
                        "quality_check": result.get("quality_check", {}),
                        "face_size_ratio": result.get("face_size_ratio", 0),
                        "has_eyes": result.get("has_eyes", False),
                    }
                else:
                    match_result = {
                        "success": False,
                        "error": "No matching employee found",
                        "processing_time_ms": result.get("processing_time_ms", 0),
                    }

            except CriticalBiometricError as e:
                from core.logging_utils import err_tag

                logger.error(
                    "Critical biometric error during check-out",
                    extra={"err": err_tag(e)},
                )
                return Response(
                    {
                        "success": False,
                        "error": "Biometric system temporarily unavailable",
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            except Exception as e:
                from core.logging_utils import err_tag

                logger.error(
                    "Unexpected error during check-out", extra={"err": err_tag(e)}
                )
                match_result = {"success": False, "error": "Face processing failed"}

            if not match_result["success"]:
                # Real face recognition failed
                log_biometric_attempt(
                    request,
                    "check_out",
                    success=False,
                    error_message="Real biometric face recognition failed",
                    processing_time=match_result.get("processing_time_ms"),
                )

                return Response(
                    {
                        "success": False,
                        "error": "Face recognition failed - no matching employee found",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Get employee
        try:
            employee = Employee.objects.get(id=match_result["employee_id"])
        except Employee.DoesNotExist:
            logger.error(
                "Biometrics: employee not found in Django database",
                extra={
                    "user_hash": safe_user_hash(request.user),
                    "has_match": bool(match_result),
                },
            )
            logger.error(
                "This indicates stale data in MongoDB - face embeddings exist for non-existent employee"
            )
            return Response(
                {"success": False, "error": "Employee record not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # DETAILED LOGGING for mismatch debugging (without PII)
        logger.info("🔍 Check-out matching debug")
        logger.info(
            "Biometrics: check-out match found",
            extra={
                "user_hash": safe_user_hash(request.user),
                "confidence": match_result["confidence"],
                "used_fallback": used_fallback,
            },
        )
        if not request.user.employees.exists():
            logger.warning(
                "Biometrics: no employee found for authenticated user",
                extra={"user_hash": safe_user_hash(request.user)},
            )

        # IMPORTANT: Verify that the recognized face belongs to the authenticated user
        # This ensures multiple employees can check-out simultaneously
        # Skip this check if we used fallback mode (already authenticated user)
        if (
            not used_fallback
            and request.user.employees.exists()
            and request.user.employees.first() != employee
        ):
            logger.warning("Face recognition mismatch detected")
            logger.warning(
                f"   - Expected employee: {request.user.employees.first().id} ({request.user.employees.first().get_full_name()})"
            )
            logger.warning(
                f"   - Recognized employee: {employee.id} ({employee.get_full_name()})"
            )
            return Response(
                {
                    "success": False,
                    "error": "Face does not match authenticated user",
                    "details": "Please ensure you are logged in with your own account",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Find open work log
        worklog = WorkLog.objects.filter(
            employee=employee, check_out__isnull=True
        ).first()

        if not worklog:
            return Response(
                {"success": False, "error": "No active check-in found"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update work log
        try:
            with transaction.atomic():
                worklog.check_out = timezone.now()
                worklog.location_check_out = location
                worklog.save()

            # Log successful check-out
            log = log_biometric_attempt(
                request,
                "check_out",
                employee=employee,
                success=True,
                confidence_score=match_result["confidence"],
                processing_time=match_result["processing_time_ms"],
            )

            # Save quality check
            if log and "quality_check" in match_result:
                quality = match_result["quality_check"]
                FaceQualityCheck.objects.create(
                    biometric_log=log,
                    face_detected=True,
                    face_count=1,
                    brightness_score=quality.get("brightness"),
                    blur_score=quality.get("blur_score"),
                    face_size_ratio=match_result.get("face_size_ratio", 0),
                    eye_visibility=match_result.get("has_eyes", False),
                )

                # Reset failed attempts
                try:
                    attempt = BiometricAttempt.objects.get(
                        ip_address=get_client_ip(request)
                    )
                    attempt.reset_attempts()
                except BiometricAttempt.DoesNotExist:
                    pass

        except Exception as worklog_error:
            logger.exception("Failed to update worklog")
            return Response(
                {"error": "Failed to update work log"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Calculate hours worked
        hours_worked = worklog.get_total_hours()

        logger.info(
            "Successful check-out completed",
            extra={"employee_id": str(employee.id)[:8], "hours_worked": hours_worked},
        )

        return Response(
            {
                "success": True,
                "employee_id": employee.id,
                "employee_name": employee.get_full_name(),
                "check_in_time": worklog.check_in,
                "check_out_time": worklog.check_out,
                "hours_worked": round(hours_worked, 2),
                "location": location,
                "confidence": round(match_result["confidence"], 2),
                "worklog_id": worklog.id,
            }
        )

    except Employee.DoesNotExist:
        return Response(
            {"error": "Employee record not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception:
        logger.exception("Check-out error")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@extend_schema(
    operation_id="check_work_status",
    tags=["Biometrics"],
    summary="Check current work status for authenticated user",
    description="""
    Check if the authenticated user has an active check-in session.
    This endpoint helps the frontend determine whether to show check-in or check-out button.
    
    **Returns:**
    - `is_checked_in`: boolean indicating if user has active session
    - `current_session`: details of active session if exists
    - `employee_info`: current user's employee information
    """,
    responses={
        200: OpenApiExample(
            "User Status",
            value={
                "is_checked_in": True,
                "current_session": {
                    "worklog_id": 13,
                    "check_in_time": "2025-06-05T20:33:59.759251Z",
                    "location_check_in": "Office Main Entrance",
                    "duration_minutes": 45,
                },
                "employee_info": {
                    "employee_id": 15,
                    "employee_name": "Admin User",
                    "email": "admin@example.com",
                },
            },
        )
    },
)
@api_view(["GET"])
@permission_classes([IsEmployeeOrAbove])
def check_work_status(request):
    """
    Check current work status for authenticated user
    """
    try:
        # Get employee for current user
        if not request.user.employees.exists():
            return Response(
                {
                    "error": True,
                    "code": "NO_EMPLOYEE_PROFILE",
                    "message": "User does not have an employee profile",
                    "details": None,
                    "error_id": "status_001",
                    "timestamp": timezone.now().isoformat(),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        employee = request.user.employees.first()

        # Check for active work session
        active_worklog = WorkLog.objects.filter(
            employee=employee, check_out__isnull=True
        ).first()

        if active_worklog:
            # Calculate duration
            duration = timezone.now() - active_worklog.check_in
            duration_minutes = int(duration.total_seconds() / 60)

            return Response(
                {
                    "is_checked_in": True,
                    "current_session": {
                        "worklog_id": active_worklog.id,
                        "check_in_time": active_worklog.check_in,
                        "location_check_in": active_worklog.location_check_in,
                        "duration_minutes": duration_minutes,
                    },
                    "employee_info": {
                        "employee_id": employee.id,
                        "employee_name": employee.get_full_name(),
                        "email": employee.email,
                    },
                }
            )
        else:
            return Response(
                {
                    "is_checked_in": False,
                    "current_session": None,
                    "employee_info": {
                        "employee_id": employee.id,
                        "employee_name": employee.get_full_name(),
                        "email": employee.email,
                    },
                }
            )

    except Exception:
        logger.exception("Work status check error")
        return Response(
            {
                "error": True,
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Failed to check work status",
                "details": None,
                "error_id": "status_002",
                "timestamp": timezone.now().isoformat(),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def test_endpoint(request):
    """
    Test endpoint to verify URL loading works
    """
    return Response(
        {"message": "Test endpoint is working", "timestamp": timezone.now()}
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def biometric_stats(request):
    """
    Get biometric system statistics
    """
    if not request.user.is_staff:
        return Response(
            {"error": "Admin access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        # Get MongoDB stats
        get_mongodb_service().get_statistics()

        # Get PostgreSQL stats
        total_profiles = BiometricProfile.objects.count()
        active_profiles = BiometricProfile.objects.filter(is_active=True).count()

        # Get recent logs
        recent_logs = BiometricLog.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=7)
        )

        successful_checks = recent_logs.filter(success=True).count()
        failed_checks = recent_logs.filter(success=False).count()

        # Get average confidence scores (not currently included in response)
        # try:
        #     confidence_scores = recent_logs.filter(
        #         success=True, confidence_score__isnull=False
        #     ).values_list("confidence_score", flat=True)
        #     avg_confidence = (
        #         sum(confidence_scores) / len(confidence_scores)
        #         if confidence_scores
        #         else 0
        #     )
        # except Exception:
        #     avg_confidence = 0

        return Response(
            {
                "profiles": {"total": total_profiles, "active": active_profiles},
                "recent_activity": {
                    "successful_checks": successful_checks,
                    "failed_checks": failed_checks,
                    "period_days": 7,
                },
                "system_status": "operational",
            }
        )

    except Exception:
        logger.exception("Stats error")
        return Response(
            {"error": "Failed to retrieve statistics"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@extend_schema(
    summary="Get current user's biometric registration status",
    description="Returns whether the current user has biometric data registered",
    responses={
        200: {
            "type": "object",
            "properties": {
                "has_biometric": {"type": "boolean"},
                "registration_date": {
                    "type": "string",
                    "format": "date-time",
                    "nullable": True,
                },
                "last_verification": {
                    "type": "string",
                    "format": "date-time",
                    "nullable": True,
                },
                "is_active": {"type": "boolean"},
            },
        }
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_biometric_status(request):
    """
    Get current user's biometric registration status
    """
    try:
        # Get employee associated with the user
        try:
            employee = Employee.objects.get(user=request.user)
        except Employee.DoesNotExist:
            logger.warning(f"No employee found for user {request.user.id}")
            return Response(
                {
                    "has_biometric": False,
                    "registration_date": None,
                    "last_verification": None,
                    "is_active": False,
                }
            )

        logger.info(
            f"Getting biometric status for user {request.user.id} (employee {employee.id})"
        )

        try:
            profile = BiometricProfile.objects.get(employee=employee)

            # Get the most recent successful verification
            last_verification = (
                BiometricLog.objects.filter(employee=employee, success=True)
                .order_by("-created_at")
                .first()
            )

            response_data = {
                "has_biometric": profile.is_active,  # Only True if active
                "registration_date": (
                    profile.created_at.isoformat() if profile.created_at else None
                ),
                "last_verification": (
                    last_verification.created_at.isoformat()
                    if last_verification
                    else None
                ),
                "is_active": profile.is_active,
            }

            logger.info(f"Biometric status for user {request.user.id}: {response_data}")
            return Response(response_data)

        except BiometricProfile.DoesNotExist:
            response_data = {
                "has_biometric": False,
                "registration_date": None,
                "last_verification": None,
                "is_active": False,
            }

            logger.info(f"No biometric profile found for user {request.user.id}")
            return Response(response_data)

    except Exception:
        logger.exception(f"Error getting biometric status for user {request.user.id}")
        return Response(
            {"error": "Failed to retrieve biometric status"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_face(request):
    """Simple face verification endpoint for tests"""
    try:
        image_data = request.data.get("image_data")
        if not image_data:
            return Response(
                {"error": "Image data required"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Mock verification for tests
        if getattr(settings, "BIOMETRY_TEST_MODE", False):
            # Get employee linked to user
            try:
                employee = Employee.objects.get(user=request.user)
                return Response(
                    {"success": True, "employee_id": employee.id, "confidence": 0.95}
                )
            except Employee.DoesNotExist:
                return Response(
                    {"error": "No employee profile"}, status=status.HTTP_400_BAD_REQUEST
                )

        # Real verification
        try:
            employee = Employee.objects.get(user=request.user)
        except Employee.DoesNotExist:
            return Response(
                {"error": "No employee profile"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Check if employee is active
        if not employee.is_active:
            return Response(
                {"success": False, "error": "Employee account is inactive"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # For now, simulate verification failure in real mode
        # TODO: Implement actual face verification logic
        return Response(
            {"success": False, "error": "Face verification failed"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    except Exception:
        logger.exception(f"Error in face verification")
        return Response(
            {"error": "Verification failed"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
