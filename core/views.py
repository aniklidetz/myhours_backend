from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Employee, Salary, WorkLog
from .serializers import EmployeeSerializer, SalarySerializer, WorkLogSerializer
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from core.filters import WorkLogFilter

class EmployeeViewSet(viewsets.ModelViewSet):
    """Endpoints for employees"""
    queryset = Employee.objects.all().order_by('id')
    serializer_class = EmployeeSerializer
    # Add search functionality
    filter_backends = [SearchFilter]
    search_fields = ['first_name', 'last_name', 'email']  # Search by name, surname and email


class SalaryViewSet(viewsets.ModelViewSet):
    """Endpoints for employee salaries"""
    queryset = Salary.objects.all().order_by('id')
    serializer_class = SalarySerializer
    # Add filtering
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['employee', 'currency']  # Filter by employee and currency

    @action(detail=True, methods=['post'])
    def calculate(self, request, pk=None):
        """Endpoint for recalculating salary"""
        salary = self.get_object()
        salary.calculate_salary()
        salary.save()
        return Response({"message": "Salary recalculated", "salary": salary.calculated_salary})


class WorkLogViewSet(viewsets.ModelViewSet):
    """Endpoints for work time logs"""
    queryset = WorkLog.objects.all().order_by('-check_in')
    serializer_class = WorkLogSerializer
    # Configure filtering
    filter_backends = [DjangoFilterBackend]  
    filterset_class = WorkLogFilter  # Use our custom filter