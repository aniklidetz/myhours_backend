from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from .models import Salary
from .serializers import SalarySerializer
from django.utils import timezone

class SalaryViewSet(viewsets.ModelViewSet):
    """Endpoints for employee salaries"""
    queryset = Salary.objects.all().order_by('id')
    serializer_class = SalarySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['employee', 'currency']

    @action(detail=True, methods=['post'])
    def calculate(self, request, pk=None):
        """Endpoint for salary recalculation"""
        salary = self.get_object()
        now = timezone.now()
        result = salary.calculate_monthly_salary(now.month, now.year)
        
        # If the result is a dictionary and contains total_salary
        if isinstance(result, dict) and 'total_salary' in result:
            calculated_salary = result['total_salary']
        else:
            calculated_salary = result
            
        return Response({
            "message": "Salary recalculated", 
            "salary": calculated_salary,
            "details": result if isinstance(result, dict) else {}
        })