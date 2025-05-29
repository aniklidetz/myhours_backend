from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from .models import Employee
from .serializers import EmployeeSerializer
import logging

logger = logging.getLogger(__name__)

class EmployeeViewSet(viewsets.ModelViewSet):
    """Endpoints for employee management with proper security"""
    queryset = Employee.objects.all().order_by('last_name', 'first_name')
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]  # Требует аутентификации
    filter_backends = [SearchFilter, DjangoFilterBackend]
    search_fields = ['first_name', 'last_name', 'email']
    filterset_fields = ['employment_type', 'is_active']

    def perform_create(self, serializer):
        """Log employee creation"""
        employee = serializer.save()
        logger.info(f"New employee created: {employee.get_full_name()} by user {self.request.user}")

    def perform_update(self, serializer):
        """Log employee updates"""
        employee = serializer.save()
        logger.info(f"Employee updated: {employee.get_full_name()} by user {self.request.user}")

    def perform_destroy(self, instance):
        """Soft delete instead of hard delete"""
        instance.is_active = False
        instance.save()
        logger.info(f"Employee deactivated: {instance.get_full_name()} by user {self.request.user}")

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate deactivated employee"""
        employee = self.get_object()
        employee.is_active = True
        employee.save()
        logger.info(f"Employee activated: {employee.get_full_name()} by user {request.user}")
        return Response({'status': 'Employee activated'})

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate employee"""
        employee = self.get_object()
        employee.is_active = False
        employee.save()
        logger.info(f"Employee deactivated: {employee.get_full_name()} by user {request.user}")
        return Response({'status': 'Employee deactivated'})