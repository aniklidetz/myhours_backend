"""
Biometric attendance views.

This module handles check-in/check-out operations for employees:
- Biometric check-in with face recognition
- Biometric check-out with face recognition
- Work status checking (is user currently checked in?)
"""

from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.conf import settings
from django.db import transaction
from django.utils import timezone

# Import parent module for test compatibility
# Tests patch 'biometrics.views.logger', 'biometrics.views.face_processor',
# and 'biometrics.views.enhanced_biometric_service'
import biometrics.views as biometrics_views
from core.exceptions import BiometricError
from core.logging_utils import err_tag, safe_user_hash
from users.models import Employee
from users.permissions import IsEmployeeOrAbove
from worktime.models import WorkLog

from ..models import BiometricAttempt, BiometricLog, BiometricProfile, FaceQualityCheck
from ..serializers import FaceRecognitionSerializer
from ..services.enhanced_biometric_service import CriticalBiometricError
from .helpers import check_rate_limit, get_client_ip, log_biometric_attempt


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
        biometrics_views.logger.critical(
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
        all_embeddings = (
            biometrics_views.get_mongodb_service().get_all_active_embeddings()
        )

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
                biometrics_views.logger.critical(
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
                biometrics_views.logger.warning(
                    f"Using mock check-in for employee {test_employee.id} - SECURITY RISK!"
                )
            else:
                biometrics_views.logger.error(
                    "Mock mode enabled but user has no employee profile"
                )
                return Response(
                    {"error": "User has no employee profile"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            # REAL biometric processing
            biometrics_views.logger.info("Processing real biometric data for check-in")
            if biometrics_views.face_processor is None:
                return Response(
                    {"error": "Biometric processing service not available"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            match_result = biometrics_views.face_processor.find_matching_employee(
                image, all_embeddings
            )

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
        if settings.DEBUG:
            biometrics_views.logger.debug(
                "Biometrics check-in match",
                extra={"used_fallback": bool(used_fallback), "operation": "check_in"},
            )  # lgtm[py/clear-text-logging-sensitive-data]
        if not request.user.employees.exists():
            biometrics_views.logger.warning(
                "   - No employee found for authenticated user"
            )

        # IMPORTANT: Verify that the recognized face belongs to the authenticated user
        # This ensures multiple employees can check-in simultaneously
        # Skip this check if we used fallback mode (already authenticated user)
        if (
            not used_fallback
            and request.user.employees.exists()
            and request.user.employees.first() != employee
        ):
            biometrics_views.logger.warning("Face recognition mismatch detected")
            biometrics_views.logger.warning(
                f"   - Expected employee: {request.user.employees.first().id} ({request.user.employees.first().get_full_name()})"
            )
            biometrics_views.logger.warning(
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
            biometrics_views.logger.exception("Failed to create worklog")
            return Response(
                {"error": "Failed to create work log"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        biometrics_views.logger.info("Check-in successful")

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
        biometrics_views.logger.exception("Check-in error")
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
        biometrics_views.logger.critical(
            "USING BIOMETRIC MOCK MODE FOR CHECK-OUT - NOT FOR PRODUCTION!"
        )

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
            biometrics_views.logger.critical(
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
            biometrics_views.logger.warning("Using mock check-out - SECURITY RISK!")
        else:
            # REAL biometric processing using enhanced service
            biometrics_views.logger.info("Processing real biometric data for check-out")
            try:
                # Process image to get face encoding
                if biometrics_views.face_processor is None:
                    return Response(
                        {"error": "Biometric processing service not available"},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
                result = biometrics_views.face_processor.process_registration_image(
                    image
                )
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
                verification_result = (
                    biometrics_views.enhanced_biometric_service.verify_biometric(
                        face_encoding
                    )
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

                biometrics_views.logger.error(
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

                biometrics_views.logger.error(
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
            biometrics_views.logger.error(
                "Biometrics: employee not found in Django database",
                extra={
                    "user_hash": safe_user_hash(request.user),
                    "has_match": bool(match_result),
                },
            )
            biometrics_views.logger.error(
                "This indicates stale data in MongoDB - face embeddings exist for non-existent employee"
            )
            return Response(
                {"success": False, "error": "Employee record not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # DETAILED LOGGING for mismatch debugging (without PII)
        biometrics_views.logger.info("🔍 Check-out matching debug")
        biometrics_views.logger.info(
            "Biometrics: check-out match found",
            extra={
                "user_hash": safe_user_hash(request.user),
                "confidence": match_result["confidence"],
                "used_fallback": used_fallback,
            },
        )
        if not request.user.employees.exists():
            biometrics_views.logger.warning(
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
            biometrics_views.logger.warning("Face recognition mismatch detected")
            biometrics_views.logger.warning(
                f"   - Expected employee: {request.user.employees.first().id} ({request.user.employees.first().get_full_name()})"
            )
            biometrics_views.logger.warning(
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
            biometrics_views.logger.exception("Failed to update worklog")
            return Response(
                {"error": "Failed to update work log"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Calculate hours worked
        hours_worked = worklog.get_total_hours()

        biometrics_views.logger.info(
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
        biometrics_views.logger.exception("Check-out error")
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
        biometrics_views.logger.exception("Work status check error")
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
