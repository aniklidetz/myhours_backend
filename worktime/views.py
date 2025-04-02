from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend
from .models import WorkLog
from .serializers import WorkLogSerializer
from .filters import WorkLogFilter

class WorkLogViewSet(viewsets.ModelViewSet):
    """Endpoints for tracking work time"""
    queryset = WorkLog.objects.all().order_by('-check_in')
    serializer_class = WorkLogSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = WorkLogFilter