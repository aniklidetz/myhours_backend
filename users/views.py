from rest_framework import viewsets
from rest_framework.filters import SearchFilter
from .models import Employee
from .serializers import EmployeeSerializer

class EmployeeViewSet(viewsets.ModelViewSet):
    """Endpoints for employee management"""
    queryset = Employee.objects.all().order_by('id')
    serializer_class = EmployeeSerializer
    filter_backends = [SearchFilter]
    search_fields = ['first_name', 'last_name', 'email']