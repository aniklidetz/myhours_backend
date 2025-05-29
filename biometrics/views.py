from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework import viewsets
from django.utils import timezone
from django.core.exceptions import ValidationError
import logging

from users.models import Employee
from worktime.models import WorkLog
from .services.face_recognition_service import FaceRecognitionService
from .services.biometrics import BiometricService
from .serializers import (
    FaceRegistrationSerializer,
    FaceRecognitionSerializer,
    BiometricResponseSerializer,
    BiometricStatsSerializer
)

logger = logging.getLogger('biometrics')

class FaceRegistrationView(APIView):
    """API for employee face registration with proper security"""
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # Validate input data
        serializer = FaceRegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Face registration validation failed: {serializer.errors}")
            return Response(
                {"error": "Invalid input data", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        employee_id = serializer.validated_data['employee_id']
        base64_image = serializer.validated_data['image']

        try:
            employee = Employee.objects.get(id=employee_id, is_active=True)
        except Employee.DoesNotExist:
            logger.warning(f"Face registration attempt for non-existent employee {employee_id} by user {request.user}")
            return Response(
                {"error": f"Active employee with id {employee_id} does not exist"},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            document_id = FaceRecognitionService.save_employee_face(employee_id, base64_image)

            if not document_id:
                logger.error(f"Face registration failed for employee {employee_id} - no face detected")
                return Response(
                    {"error": "Failed to register face. No face detected in the image."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            logger.info(f"Face registered successfully for employee {employee.get_full_name()} by user {request.user}")
            
            response_data = {
                "success": True,
                "message": f"Face registered for employee {employee.get_full_name()}",
                "document_id": document_id,
                "employee_id": employee_id,
                "employee_name": employee.get_full_name()
            }
            
            return Response(response_data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Unexpected error during face registration: {e}")
            return Response(
                {"error": "An unexpected error occurred during face registration"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class FaceRecognitionCheckInView(APIView):
    """API for employee check-in using face recognition with security"""
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # Validate input data
        serializer = FaceRecognitionSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Check-in validation failed: {serializer.errors}")
            return Response(
                {"error": "Invalid input data", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        base64_image = serializer.validated_data['image']
        location = serializer.validated_data.get('location', '')

        try:
            employee_id = FaceRecognitionService.recognize_employee(base64_image)
            if not employee_id:
                logger.warning(f"Check-in attempt with unrecognized face by user {request.user}")
                return Response(
                    {"error": "Face not recognized or not found in database"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            employee = Employee.objects.get(id=employee_id, is_active=True)
            
            # Check for existing open worklog
            open_worklog = WorkLog.objects.filter(employee=employee, check_out__isnull=True).first()
            if open_worklog:
                logger.warning(f"Check-in attempt for employee {employee.get_full_name()} who already has an open shift")
                return Response(
                    {
                        "error": f"Employee {employee.get_full_name()} already has an open shift",
                        "existing_worklog_id": open_worklog.id,
                        "check_in_time": open_worklog.check_in.isoformat()
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Create new worklog
            worklog = WorkLog.objects.create(
                employee=employee,
                check_in=timezone.now(),
                location_check_in=location
            )
            
            logger.info(f"Check-in successful for {employee.get_full_name()}")
            
            response_data = {
                "success": True,
                "message": f"Check-in successful for {employee.get_full_name()}",
                "worklog_id": worklog.id,
                "employee_id": employee.id,
                "employee_name": employee.get_full_name(),
                "check_in_time": worklog.check_in.isoformat()
            }
            
            return Response(response_data, status=status.HTTP_201_CREATED)

        except Employee.DoesNotExist:
            logger.error(f"Check-in attempt for inactive/non-existent employee {employee_id}")
            return Response(
                {"error": f"Active employee with id {employee_id} not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValidationError as e:
            logger.error(f"Validation error during check-in: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error during check-in: {e}")
            return Response(
                {"error": "An unexpected error occurred during check-in"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class FaceRecognitionCheckOutView(APIView):
    """API for employee check-out using face recognition with security"""
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # Validate input data
        serializer = FaceRecognitionSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Check-out validation failed: {serializer.errors}")
            return Response(
                {"error": "Invalid input data", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        base64_image = serializer.validated_data['image']
        location = serializer.validated_data.get('location', '')

        try:
            employee_id = FaceRecognitionService.recognize_employee(base64_image)
            if not employee_id:
                logger.warning(f"Check-out attempt with unrecognized face by user {request.user}")
                return Response(
                    {"error": "Face not recognized or not found in database"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            employee = Employee.objects.get(id=employee_id, is_active=True)
            
            # Find open worklog
            open_worklog = WorkLog.objects.filter(employee=employee, check_out__isnull=True).first()
            if not open_worklog:
                logger.warning(f"Check-out attempt for {employee.get_full_name()} with no open shift")
                return Response(
                    {"error": f"No open shift found for employee {employee.get_full_name()}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Update worklog
            open_worklog.check_out = timezone.now()
            open_worklog.location_check_out = location
            open_worklog.save()
            
            hours_worked = open_worklog.get_total_hours()

            logger.info(f"Check-out successful for {employee.get_full_name()}, worked {hours_worked}h")
            
            response_data = {
                "success": True,
                "message": f"Check-out successful for {employee.get_full_name()}",
                "worklog_id": open_worklog.id,
                "employee_id": employee.id,
                "employee_name": employee.get_full_name(),
                "check_in_time": open_worklog.check_in.isoformat(),
                "check_out_time": open_worklog.check_out.isoformat(),
                "hours_worked": hours_worked
            }
            
            return Response(response_data, status=status.HTTP_200_OK)

        except Employee.DoesNotExist:
            logger.error(f"Check-out attempt for inactive/non-existent employee {employee_id}")
            return Response(
                {"error": f"Active employee with id {employee_id} not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValidationError as e:
            logger.error(f"Validation error during check-out: {e}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error during check-out: {e}")
            return Response(
                {"error": "An unexpected error occurred during check-out"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class BiometricManagementViewSet(viewsets.ViewSet):
    """ViewSet for biometric data management"""
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get biometric system statistics"""
        try:
            stats = BiometricService.get_stats()
            serializer = BiometricStatsSerializer(data=stats)
            
            if serializer.is_valid():
                return Response(serializer.validated_data, status=status.HTTP_200_OK)
            else:
                return Response(stats, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error getting biometric stats: {e}")
            return Response(
                {"error": "Failed to retrieve biometric statistics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['delete'])
    def delete_employee_faces(self, request, pk=None):
        """Delete all face encodings for a specific employee"""
        try:
            employee_id = int(pk)
            
            # Verify employee exists
            try:
                employee = Employee.objects.get(id=employee_id)
            except Employee.DoesNotExist:
                return Response(
                    {"error": f"Employee with id {employee_id} does not exist"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Delete face encodings
            deleted_count = BiometricService.delete_employee_face_encodings(employee_id)
            
            logger.info(f"Deleted {deleted_count} face encodings for employee {employee.get_full_name()} by user {request.user}")
            
            return Response(
                {
                    "success": True,
                    "message": f"Deleted {deleted_count} face encodings for {employee.get_full_name()}",
                    "deleted_count": deleted_count
                },
                status=status.HTTP_200_OK
            )
            
        except ValueError:
            return Response(
                {"error": "Invalid employee ID"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error deleting face encodings for employee {pk}: {e}")
            return Response(
                {"error": "Failed to delete face encodings"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def employee_faces(self, request, pk=None):
        """Get face encoding information for a specific employee"""
        try:
            employee_id = int(pk)
            
            # Verify employee exists
            try:
                employee = Employee.objects.get(id=employee_id)
            except Employee.DoesNotExist:
                return Response(
                    {"error": f"Employee with id {employee_id} does not exist"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Get face encodings (without the actual encoding data for security)
            faces = BiometricService.get_employee_face_encodings(employee_id)
            
            # Remove actual face encoding data from response
            safe_faces = []
            for face in faces:
                safe_face = {
                    "_id": face.get("_id"),
                    "employee_id": face.get("employee_id"),
                    "created_at": face.get("created_at").isoformat() if face.get("created_at") else None,
                    "version": face.get("version"),
                    "has_encoding": bool(face.get("face_encoding") is not None)
                }
                safe_faces.append(safe_face)
            
            return Response(
                {
                    "employee_id": employee_id,
                    "employee_name": employee.get_full_name(),
                    "face_encodings": safe_faces,
                    "total_count": len(safe_faces)
                },
                status=status.HTTP_200_OK
            )
            
        except ValueError:
            return Response(
                {"error": "Invalid employee ID"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error getting face encodings for employee {pk}: {e}")
            return Response(
                {"error": "Failed to retrieve face encodings"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )