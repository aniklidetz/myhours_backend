from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from .models import WorkLog
from .serializers import WorkLogSerializer
from .filters import WorkLogFilter
import logging
from core.logging_utils import safe_log_employee

logger = logging.getLogger(__name__)

class WorkLogViewSet(viewsets.ModelViewSet):
    """Endpoints for tracking work time with proper security"""
    queryset = WorkLog.objects.all().order_by('-check_in')
    serializer_class = WorkLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = WorkLogFilter

    def get_queryset(self):
        """Filter work logs to only show current user's data unless user is admin"""
        queryset = super().get_queryset()
        
        # Admins can see all logs
        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        
        # Regular users can only see their own logs
        if hasattr(self.request.user, 'employee_profile'):
            return queryset.filter(employee=self.request.user.employee_profile)
        
        # Users without employee profile see no logs
        return queryset.none()

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
        """Get all currently active work sessions"""
        active_sessions = WorkLog.objects.filter(check_out__isnull=True)
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