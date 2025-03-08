from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import Salary
from .serializers import SalarySerializer

class SalaryViewSet(viewsets.ModelViewSet):
    """Endpoints для зарплат сотрудников"""
    queryset = Salary.objects.all().order_by('id')
    serializer_class = SalarySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['employee', 'currency']

    @action(detail=True, methods=['post'])
    def calculate(self, request, pk=None):
        """Endpoint для пересчета зарплаты"""
        salary = self.get_object()
        salary.calculate_salary()
        return Response({"message": "Salary recalculated", "salary": salary.calculated_salary})