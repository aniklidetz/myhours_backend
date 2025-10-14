"""
Biometric status and utility views.

This module handles status checking and utility endpoints:
- Test endpoint for system verification
- Biometric statistics for administrators
- User biometric registration status checking
- Face verification endpoint for testing
"""

from datetime import timedelta

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.conf import settings
from django.utils import timezone

# Import parent module for test compatibility
import biometrics.views as biometrics_views
from users.models import Employee

from ..models import BiometricLog, BiometricProfile


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
        biometrics_views.get_mongodb_service().get_statistics()

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
        biometrics_views.logger.exception("Stats error")
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
            biometrics_views.logger.warning(
                f"No employee found for user {request.user.id}"
            )
            return Response(
                {
                    "has_biometric": False,
                    "registration_date": None,
                    "last_verification": None,
                    "is_active": False,
                }
            )

        biometrics_views.logger.info(
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

            biometrics_views.logger.info(
                f"Biometric status for user {request.user.id}: {response_data}"
            )
            return Response(response_data)

        except BiometricProfile.DoesNotExist:
            response_data = {
                "has_biometric": False,
                "registration_date": None,
                "last_verification": None,
                "is_active": False,
            }

            biometrics_views.logger.info(
                f"No biometric profile found for user {request.user.id}"
            )
            return Response(response_data)

    except Exception:
        biometrics_views.logger.exception(
            f"Error getting biometric status for user {request.user.id}"
        )
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
        biometrics_views.logger.exception(f"Error in face verification")
        return Response(
            {"error": "Verification failed"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
