"""
AI Assistant Views - REST API endpoints for salary explanations.

This module provides endpoints for the mobile app to request
AI-powered explanations of salary components.
"""

import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.shortcuts import render

from .services.bedrock_api_service import invoke_ai_explainer_lambda

logger = logging.getLogger(__name__)


class SalaryExplanationView(APIView):
    """
    API endpoint for AI-powered salary explanations.

    POST /api/ai-assistant/explain/

    Request body:
    {
        "query": "Why is my Shabbat pay calculated this way?",
        "period": "October 2025",
        "language": "en"  // optional, defaults to "en"
    }

    Response:
    {
        "status": "success",
        "message": "AI explanation retrieved successfully.",
        "data": {
            "explanation": "Your Shabbat work on October 11th...",
            "citations": [
                {
                    "law": "Hours of Work and Rest Law",
                    "section": "Section 17",
                    "description": "..."
                }
            ]
        }
    }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Handle POST request for salary explanation.

        Extracts query parameters, calls AI service, and returns
        formatted response for the mobile app.
        """
        # 1. Extract request data
        user_query = request.data.get("query", "").strip()
        period = request.data.get("period", "Current Month")
        language = request.data.get("language", "en")

        # Validate required fields
        if not user_query:
            return Response(
                {
                    "status": "error",
                    "message": "Query is required",
                    "error_code": "MISSING_QUERY",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. Get employee ID from authenticated user
        # In production, this comes from the User-Employee relationship
        employee_id = self._get_employee_id(request.user)

        if not employee_id:
            return Response(
                {
                    "status": "error",
                    "message": "Employee profile not found",
                    "error_code": "EMPLOYEE_NOT_FOUND",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # 3. Log the request
        logger.info(
            f"AI explanation requested",
            extra={
                "user_id": request.user.id,
                "employee_id": employee_id,
                "query_preview": user_query[:50],
                "language": language,
            },
        )

        # 4. Call AI service
        ai_response = invoke_ai_explainer_lambda(
            employee_id=employee_id,
            query_text=user_query,
            period=period,
            language=language,
        )

        # 5. Return response based on AI service result
        if ai_response["status"] == "success":
            return Response(
                {
                    "status": "success",
                    "message": "AI explanation retrieved successfully.",
                    "data": {
                        "explanation": ai_response["explanation_text"],
                    },
                },
                status=status.HTTP_200_OK,
            )
        else:
            # Return error with appropriate status code
            return Response(
                {
                    "status": "error",
                    "message": ai_response["explanation_text"],
                    "error_code": ai_response.get("error_code", "AI_SERVICE_ERROR"),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    def _get_employee_id(self, user) -> int | None:
        """
        Get employee ID from authenticated user.

        In production, this retrieves the Employee record linked to the User.
        For MVP, we use a fallback to user.id or check for employee attribute.

        Args:
            user: Authenticated Django user

        Returns:
            Employee ID or None if not found
        """
        # Try to get employee_id from user's employee profile
        # This assumes User has a OneToOne relationship with Employee

        # Option 1: Direct attribute (if Employee has user FK)
        if hasattr(user, "employee"):
            return user.employee.id

        # Option 2: Check for employee_id attribute
        if hasattr(user, "employee_id"):
            return user.employee_id

        # Option 3: Query Employee model
        try:
            from users.models import Employee

            employee = Employee.objects.filter(user=user).first()
            if employee:
                return employee.id
        except Exception:
            pass

        # Fallback for MVP: use user.id
        # This allows testing without full Employee setup
        logger.warning(
            f"No Employee found for user {user.id}, using user.id as fallback"
        )
        return user.id


class SalaryExplanationHealthView(APIView):
    """
    Health check endpoint for AI Assistant service.

    GET /api/ai-assistant/health/

    Returns service status and configuration info.
    """

    permission_classes = []  # Public endpoint for health checks

    def get(self, request):
        """Return health status of AI Assistant service."""
        from django.conf import settings

        api_url = getattr(
            settings,
            "BEDROCK_API_GATEWAY_URL",
            "https://pxddvm9n35.execute-api.us-east-1.amazonaws.com/prod",
        )

        return Response(
            {
                "status": "healthy",
                "service": "AI Assistant",
                "version": "1.0.0",
                "config": {
                    "api_gateway_configured": bool(api_url),
                    "endpoint": f"{api_url}/explain",
                },
            },
            status=status.HTTP_200_OK,
        )


def test_page(request):
    """
    Test page for AI Assistant demo.

    GET /api/v1/ai-assistant/test/
    """
    return render(request, "ai_assistant/test.html")
