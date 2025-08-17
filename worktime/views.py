import logging

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.core.cache import cache
from django.utils import timezone


from .filters import WorkLogFilter
from .models import WorkLog
from .serializers import WorkLogSerializer

logger = logging.getLogger(__name__)


class WorkLogViewSet(viewsets.ModelViewSet):
    """Endpoints for tracking work time with proper security"""

    queryset = WorkLog.objects.select_related("employee").order_by("-check_in")
    serializer_class = WorkLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = WorkLogFilter

    def get_queryset(self):
        """Filter work logs to only show current user's data unless user is admin with fully optimized queries"""
        # Start with fully optimized base queryset - prefetch all related objects to avoid N+1
        queryset = (
            WorkLog.objects.select_related("employee__user")  # Employee and linked User
            .prefetch_related(
                "employee__salary_info",  # Salary information
                "employee__invitation",  # Employee invitation
                "employee__biometric_profile",  # Biometric profile (OneToOneField)
            )
            .order_by("-check_in")
        )

        # Log user info for debugging
        logger.info(
            f"WorkLog access: User {self.request.user.username} (ID: {self.request.user.id})"
        )
        logger.info(
            f"  is_staff: {self.request.user.is_staff}, is_superuser: {self.request.user.is_superuser}"
        )

        # Admins can see all logs
        if self.request.user.is_staff or self.request.user.is_superuser:
            logger.info("  Admin access granted - can see all work logs")
            return queryset

        # Regular users can only see their own logs
        # Since Employee is now ForeignKey, get first employee record for this user
        try:
            employee_profile = self.request.user.employees.first()
            if employee_profile:
                logger.info(
                    f"  Employee access: {employee_profile.get_full_name()} (ID: {employee_profile.id}, Role: {employee_profile.role})"
                )

                # Check if user has accountant or admin role - they can see all data
                if employee_profile.role in ["accountant", "admin"]:
                    logger.info("  Accountant/Admin role - can see all work logs")
                    return queryset
                else:
                    logger.info(
                        f"  Regular employee - can only see own logs (Employee ID: {employee_profile.id})"
                    )
                    return queryset.filter(employee=employee_profile)
        except AttributeError:
            pass

        # Users without employee profile see no logs
        logger.info("  No employee_profile - access denied")
        return queryset.none()

    def list(self, request, *args, **kwargs):
        """Optimized list method with enhanced query optimization for large datasets"""

        # CRITICAL DEBUG: Log authentication issue details
        employee_filter = request.query_params.get("employee")
        auth_header = request.META.get("HTTP_AUTHORIZATION", "MISSING")
        user_agent = request.META.get("HTTP_USER_AGENT", "MISSING")

        logger.debug(
            "Worktime API request",
            extra={
                "endpoint": getattr(request.resolver_match, "view_name", None),
                "has_employee_filter": bool(employee_filter),
                "filter_keys": sorted(employee_filter.keys()) if isinstance(employee_filter, dict) else None,
                "has_auth": auth_header != "MISSING",
                "is_authenticated": request.user.is_authenticated,
                "has_user_agent": user_agent != "MISSING",
                "query_param_keys": sorted(request.query_params.keys()) if request.query_params else [],
            },
        )

        # If employee filter is present but user is not authenticated, this is the bug
        if employee_filter and not request.user.is_authenticated:
            logger.error(
                f" BUG CONFIRMED: Employee filter present but user not authenticated!"
            )
            logger.error(
                f" FRONTEND FIX NEEDED: Add Authorization header to requests with employee filter"
            )

        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        """Log work session creation"""
        worklog = serializer.save()
        from hashlib import blake2b
        emp_corr = blake2b(str(worklog.employee.pk).encode(), digest_size=6).hexdigest()
        logger.info(
            "Work session started",
            extra={
                "employee_corr": emp_corr,
                "check_in_time": (
                    worklog.check_in.isoformat() if worklog.check_in else None
                ),
            },
        )

    def perform_update(self, serializer):
        """Log work session updates"""
        worklog = serializer.save()
        if worklog.check_out:
            from hashlib import blake2b
            emp_corr = blake2b(str(worklog.employee.pk).encode(), digest_size=6).hexdigest()
            logger.info(
                "Work session ended",
                extra={
                    "employee_corr": emp_corr,
                    "duration_hours": worklog.get_total_hours(),
                },
            )

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Approve work log entry"""
        worklog = self.get_object()
        worklog.is_approved = True
        worklog.save()
        from hashlib import blake2b
        actor = "employee" if hasattr(request.user, "employee") else "user"
        actor_corr = blake2b(str(request.user.pk).encode(), digest_size=6).hexdigest()
        logger.info(
            "Work log approved",
            extra={
                "actor_role": actor,
                "actor_corr": actor_corr,
                "worklog_present": True,
            },
        )
        return Response({"status": "Work log approved"})

    @action(detail=False, methods=["get"])
    def current_sessions(self, request):
        """Get all currently active work sessions with fully optimized queries"""
        active_sessions = (
            WorkLog.objects.select_related("employee__user")  # Employee and linked User
            .prefetch_related(
                "employee__salary_info",  # Salary information
                "employee__invitation",  # Employee invitation
                "employee__biometric_profile",  # Biometric profile (OneToOneField)
            )
            .filter(check_out__isnull=True)
        )
        serializer = self.get_serializer(active_sessions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def quick_checkout(self, request):
        """Quick checkout for current user (if implementing user-specific employees)"""
        employee_id = request.data.get("employee_id")
        if not employee_id:
            return Response(
                {"error": "employee_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Find open work session
            open_session = WorkLog.objects.get(
                employee_id=employee_id, check_out__isnull=True
            )
            open_session.check_out = timezone.now()
            open_session.save()

            serializer = self.get_serializer(open_session)
            return Response(serializer.data)

        except WorkLog.DoesNotExist:
            return Response(
                {"error": "No active work session found"},
                status=status.HTTP_404_NOT_FOUND,
            )
