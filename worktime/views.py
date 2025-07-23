from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.core.cache import cache
from .models import WorkLog
from .serializers import WorkLogSerializer
from .filters import WorkLogFilter
import logging
from core.logging_utils import safe_log_employee

logger = logging.getLogger(__name__)

class WorkLogViewSet(viewsets.ModelViewSet):
    """Endpoints for tracking work time with proper security"""
    queryset = WorkLog.objects.select_related('employee').order_by('-check_in')
    serializer_class = WorkLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = WorkLogFilter

    def get_queryset(self):
        """Filter work logs to only show current user's data unless user is admin with fully optimized queries"""        
        # Start with fully optimized base queryset - prefetch all related objects to avoid N+1
        queryset = WorkLog.objects.select_related(
            'employee__user'  # Employee and linked User
        ).prefetch_related(
            'employee__salary_info',        # Salary information  
            'employee__invitation',         # Employee invitation
            'employee__biometric_profile'   # Biometric profile (OneToOneField)
        ).order_by('-check_in')
        
        # Log user info for debugging
        logger.info(f"WorkLog access: User {self.request.user.username} (ID: {self.request.user.id})")
        logger.info(f"  is_staff: {self.request.user.is_staff}, is_superuser: {self.request.user.is_superuser}")
        
        # Admins can see all logs
        if self.request.user.is_staff or self.request.user.is_superuser:
            logger.info("  Admin access granted - can see all work logs")
            return queryset
        
        # Regular users can only see their own logs
        if hasattr(self.request.user, 'employee_profile'):
            employee_profile = self.request.user.employee_profile
            logger.info(f"  Employee access: {employee_profile.get_full_name()} (ID: {employee_profile.id}, Role: {employee_profile.role})")
            
            # Check if user has accountant or admin role - they can see all data
            if employee_profile.role in ['accountant', 'admin']:
                logger.info("  Accountant/Admin role - can see all work logs")
                return queryset
            else:
                logger.info(f"  Regular employee - can only see own logs (Employee ID: {employee_profile.id})")
                return queryset.filter(employee=self.request.user.employee_profile)
        
        # Users without employee profile see no logs
        logger.info("  No employee_profile - access denied")
        return queryset.none()

    def list(self, request, *args, **kwargs):
        """Optimized list method with enhanced query optimization for large datasets"""
        
        # CRITICAL DEBUG: Log authentication issue details
        employee_filter = request.query_params.get('employee')
        auth_header = request.META.get('HTTP_AUTHORIZATION', 'MISSING')
        user_agent = request.META.get('HTTP_USER_AGENT', 'MISSING')
        
        logger.error(f" WORKTIME API DEBUG:")
        logger.error(f"  Path: {request.path}")
        logger.error(f"  Employee filter: {employee_filter}")
        logger.error(f"  Auth header: {auth_header[:50]}..." if auth_header != 'MISSING' else "  Auth header: MISSING")
        logger.error(f"  User: {request.user}")
        logger.error(f"  Is authenticated: {request.user.is_authenticated}")
        logger.error(f"  User agent: {user_agent[:100]}...")
        logger.error(f"  Query params: {dict(request.query_params)}")
        
        # If employee filter is present but user is not authenticated, this is the bug
        if employee_filter and not request.user.is_authenticated:
            logger.error(f" BUG CONFIRMED: Employee filter present but user not authenticated!")
            logger.error(f" FRONTEND FIX NEEDED: Add Authorization header to requests with employee filter")
        
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
        logger.info("Work session started", extra={
            **safe_log_employee(worklog.employee, "work_session"),
            "check_in_time": worklog.check_in.isoformat() if worklog.check_in else None
        })

    def perform_update(self, serializer):
        """Log work session updates"""
        worklog = serializer.save()
        if worklog.check_out:
            logger.info("Work session ended", extra={
                **safe_log_employee(worklog.employee, "work_session"),
                "duration_hours": worklog.get_total_hours()
            })

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve work log entry"""
        worklog = self.get_object()
        worklog.is_approved = True
        worklog.save()
        logger.info("Work log approved", extra={
            "worklog_id": str(worklog.id)[:8],
            "approved_by": safe_log_employee(request.user, "approver") if hasattr(request.user, 'employee') else str(request.user.id)[:8]
        })
        return Response({'status': 'Work log approved'})

    @action(detail=False, methods=['get'])
    def current_sessions(self, request):
        """Get all currently active work sessions with fully optimized queries"""
        active_sessions = WorkLog.objects.select_related(
            'employee__user'  # Employee and linked User
        ).prefetch_related(
            'employee__salary_info',        # Salary information
            'employee__invitation',         # Employee invitation
            'employee__biometric_profile'   # Biometric profile (OneToOneField)
        ).filter(check_out__isnull=True)
        serializer = self.get_serializer(active_sessions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def quick_checkout(self, request):
        """Quick checkout for current user (if implementing user-specific employees)"""
        employee_id = request.data.get('employee_id')
        if not employee_id:
            return Response(
                {'error': 'employee_id is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Find open work session
            open_session = WorkLog.objects.get(
                employee_id=employee_id,
                check_out__isnull=True
            )
            open_session.check_out = timezone.now()
            open_session.save()

            serializer = self.get_serializer(open_session)
            return Response(serializer.data)

        except WorkLog.DoesNotExist:
            return Response(
                {'error': 'No active work session found'}, 
                status=status.HTTP_404_NOT_FOUND
            )