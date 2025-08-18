import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger(__name__)


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def debug_auth(request):
    """
    Debug endpoint to analyze authentication issues
    """
    auth_info = {
        "timestamp": (
            str(request._start_time) if hasattr(request, "_start_time") else "not_set"
        ),
        "method": request.method,
        "path": request.path,
        "query_params": dict(request.GET),
        "user": {
            "is_authenticated": request.user.is_authenticated,
            "username": (
                request.user.username
                if request.user.is_authenticated
                else "AnonymousUser"
            ),
            "id": request.user.id if request.user.is_authenticated else None,
        },
        "headers": {
            "authorization": request.META.get("HTTP_AUTHORIZATION", "NOT_SET"),
            "user_agent": request.META.get("HTTP_USER_AGENT", "NOT_SET"),
            "content_type": request.META.get("CONTENT_TYPE", "NOT_SET"),
        },
        "ip": request.META.get("REMOTE_ADDR", "NOT_SET"),
        "device_token": None,
        "employee_profile": None,
    }

    # Check for device token
    if hasattr(request, "device_token"):
        device_token = request.device_token
        auth_info["device_token"] = {
            "device_id": (
                device_token.device_id[:8] + "..."
                if device_token.device_id
                else "NOT_SET"
            ),
            "is_active": device_token.is_active,
            "biometric_verified": device_token.biometric_verified,
            "created_at": str(device_token.created_at),
        }

    # Check for employee profile
    if request.user.is_authenticated and hasattr(request.user, "employee_profile"):
        emp = request.user.employee_profile
        auth_info["employee_profile"] = {
            "id": emp.id,
            "name": emp.get_full_name(),
            "role": emp.role,
            "is_active": emp.is_active,
        }

    # Log the debug info
    logger.info(f"Debug Auth: {auth_info}")

    return Response(
        {"success": True, "message": "Authentication debug info", "data": auth_info},
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def debug_worktime_auth(request):
    """
    Debug endpoint specifically for worktime authentication issues
    """
    # Simulate the exact request that's failing
    employee_param = request.GET.get("employee")

    debug_info = {
        "request_info": {
            "has_employee_param": bool(employee_param),
            "employee_param": employee_param,
            "query_params": dict(request.GET),
            "authorization_header": request.META.get("HTTP_AUTHORIZATION", "MISSING"),
        },
        "authentication": {
            "is_authenticated": request.user.is_authenticated,
            "user": (
                request.user.username
                if request.user.is_authenticated
                else "AnonymousUser"
            ),
            "user_id": request.user.id if request.user.is_authenticated else None,
        },
        "permissions": {},
        "recommendations": [],
    }

    # Check permissions like in WorkLogViewSet
    if request.user.is_authenticated:
        debug_info["permissions"]["is_staff"] = request.user.is_staff
        debug_info["permissions"]["is_superuser"] = request.user.is_superuser

        if hasattr(request.user, "employee_profile"):
            emp = request.user.employee_profile
            debug_info["permissions"]["employee_role"] = emp.role
            debug_info["permissions"]["can_see_all"] = (
                emp.role in ["accountant", "admin"] or request.user.is_staff
            )
            debug_info["permissions"]["employee_id"] = emp.id
        else:
            debug_info["permissions"]["has_employee_profile"] = False
            debug_info["recommendations"].append("User has no employee_profile")
    else:
        debug_info["recommendations"].append(
            "User is not authenticated - check Authorization header"
        )

        # Check if header exists but is malformed
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header:
            debug_info["recommendations"].append(
                f"Authorization header exists but authentication failed: {auth_header[:20]}..."
            )
        else:
            debug_info["recommendations"].append("No Authorization header found")

    # Log for debugging (sanitized)
    from django.conf import settings

    from core.logging_utils import redact_dict

    if settings.DEBUG:
        # Create safe debug structure without sensitive data
        safe_debug = {
            "endpoint": getattr(request.resolver_match, "view_name", None),
            "has_employee_param": bool(employee_param),
            "has_auth_header": "HTTP_AUTHORIZATION" in request.META,
            "is_authenticated": bool(getattr(request.user, "is_authenticated", False)),
            "has_user_agent": bool(request.META.get("HTTP_USER_AGENT")),
            "query_param_keys_count": len((request.GET or {}).keys()),
            "recommendations_count": len(debug_info.get("recommendations", [])),
            "user_permissions": {
                "is_staff": debug_info.get("permissions", {}).get("is_staff", False),
                "is_superuser": debug_info.get("permissions", {}).get(
                    "is_superuser", False
                ),
            },
        }
        logger.info(
            "Worktime Auth Debug (safe)", extra={"meta": safe_debug}
        )  # lgtm[py/clear-text-logging-sensitive-data]

    return Response(
        {
            "success": True,
            "message": "Worktime authentication debug",
            "data": debug_info,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def debug_headers(request):
    """
    Debug endpoint to show all request headers
    """
    headers = {}
    for key, value in request.META.items():
        if key.startswith("HTTP_"):
            header_name = key[5:].replace("_", "-").title()
            headers[header_name] = value

    debug_info = {
        "all_headers": headers,
        "important_headers": {
            "authorization": request.META.get("HTTP_AUTHORIZATION", "MISSING"),
            "user_agent": request.META.get("HTTP_USER_AGENT", "MISSING"),
            "content_type": request.META.get("CONTENT_TYPE", "MISSING"),
            "x_requested_with": request.META.get("HTTP_X_REQUESTED_WITH", "MISSING"),
        },
        "query_params": dict(request.GET),
        "path": request.path,
        "method": request.method,
        "remote_addr": request.META.get("REMOTE_ADDR", "MISSING"),
    }

    return Response(
        {"success": True, "message": "Headers debug info", "data": debug_info},
        status=status.HTTP_200_OK,
    )
