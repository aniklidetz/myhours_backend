from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
import logging
from users.models import Employee
from worktime.models import WorkLog
from .services.face_recognition_service import FaceRecognitionService

logger = logging.getLogger(__name__)

class FaceRegistrationView(APIView):
    """API for employee face registration"""
    
    def post(self, request, *args, **kwargs):
        employee_id = request.data.get('employee_id')
        base64_image = request.data.get('image')
        
        # Check if required data is provided
        if not employee_id or not base64_image:
            return Response(
                {"error": "employee_id and image are required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verify employee existence
        try:
            employee = Employee.objects.get(id=employee_id)
        except Employee.DoesNotExist:
            return Response(
                {"error": f"Employee with id {employee_id} does not exist"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Save face encoding
        document_id = FaceRecognitionService.save_employee_face(employee_id, base64_image)
        
        if not document_id:
            return Response(
                {"error": "Failed to register face. No face detected in the image."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(
            {
                "success": True,
                "message": f"Face registered for employee {employee.first_name} {employee.last_name}",
                "document_id": document_id
            },
            status=status.HTTP_201_CREATED
        )


class FaceRecognitionCheckInView(APIView):
    """API for employee check-in using face recognition"""
    
    def post(self, request, *args, **kwargs):
        base64_image = request.data.get('image')
        location = request.data.get('location', '')
        
        if not base64_image:
            return Response(
                {"error": "image is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Recognize employee by face
        employee_id = FaceRecognitionService.recognize_employee(base64_image)
        
        if not employee_id:
            return Response(
                {"error": "Face not recognized or not found in database"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Retrieve employee
            employee = Employee.objects.get(id=employee_id)
            
            # Check for an already open shift
            open_worklog = WorkLog.objects.filter(
                employee=employee,
                check_out__isnull=True
            ).first()
            
            if open_worklog:
                return Response(
                    {"error": f"Employee {employee.first_name} {employee.last_name} already has an open shift"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create a new work log entry
            worklog = WorkLog.objects.create(
                employee=employee,
                check_in=timezone.now(),
                location_check_in=location
            )
            
            return Response(
                {
                    "success": True,
                    "message": f"Check-in successful for {employee.first_name} {employee.last_name}",
                    "worklog_id": worklog.id,
                    "check_in_time": worklog.check_in
                },
                status=status.HTTP_201_CREATED
            )
            
        except Employee.DoesNotExist:
            return Response(
                {"error": f"Employee with id {employee_id} not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error during check-in: {e}")
            return Response(
                {"error": f"An error occurred during check-in: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class FaceRecognitionCheckOutView(APIView):
    """API for employee check-out using face recognition"""
    
    def post(self, request, *args, **kwargs):
        base64_image = request.data.get('image')
        location = request.data.get('location', '')
        
        if not base64_image:
            return Response(
                {"error": "image is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Recognize employee by face
        employee_id = FaceRecognitionService.recognize_employee(base64_image)
        
        if not employee_id:
            return Response(
                {"error": "Face not recognized or not found in database"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Retrieve employee
            employee = Employee.objects.get(id=employee_id)
            
            # Find an open shift for this employee
            open_worklog = WorkLog.objects.filter(
                employee=employee,
                check_out__isnull=True
            ).first()
            
            if not open_worklog:
                return Response(
                    {"error": f"No open shift found for employee {employee.first_name} {employee.last_name}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Record check-out time
            open_worklog.check_out = timezone.now()
            open_worklog.location_check_out = location
            open_worklog.save()
            
            # Calculate worked hours
            hours_worked = open_worklog.get_total_hours()
            
            return Response(
                {
                    "success": True,
                    "message": f"Check-out successful for {employee.first_name} {employee.last_name}",
                    "worklog_id": open_worklog.id,
                    "check_in_time": open_worklog.check_in,
                    "check_out_time": open_worklog.check_out,
                    "hours_worked": hours_worked
                },
                status=status.HTTP_200_OK
            )
            
        except Employee.DoesNotExist:
            return Response(
                {"error": f"Employee with id {employee_id} not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error during check-out: {e}")
            return Response(
                {"error": f"An error occurred during check-out: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
