from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from core.filters import WorkLogFilter
from payroll.models import Salary
from users.models import Employee
from worktime.models import WorkLog

from .serializers import EmployeeSerializer, SalarySerializer, WorkLogSerializer


class EmployeeViewSet(viewsets.ModelViewSet):
    """Endpoints for employees"""

    queryset = Employee.objects.all().order_by("id")
    serializer_class = EmployeeSerializer
    filter_backends = [SearchFilter]
    search_fields = ["first_name", "last_name", "email"]


class SalaryViewSet(viewsets.ModelViewSet):
    """Endpoints for employee salaries"""

    queryset = Salary.objects.all().order_by("id")
    serializer_class = SalarySerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["employee", "currency"]

    @action(detail=True, methods=["post"])
    def calculate(self, request, pk=None):
        """Endpoint for recalculating salary"""
        salary = self.get_object()

        # Check which calculation method is available in the updated model
        if hasattr(salary, "calculate_salary") and callable(salary.calculate_salary):
            salary.calculate_salary()
        elif hasattr(salary, "calculate_monthly_salary") and callable(
            salary.calculate_monthly_salary
        ):
            # Use the new method from the updated model
            from django.utils import timezone

            now = timezone.now()
            result = salary.calculate_monthly_salary(now.month, now.year)
            salary.save()
            return Response({"message": "Salary recalculated", "result": result})

        salary.save()
        return Response({"message": "Salary recalculated"})


class WorkLogViewSet(viewsets.ModelViewSet):
    """Endpoints for work time logs"""

    queryset = WorkLog.objects.all().order_by("-check_in")
    serializer_class = WorkLogSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = WorkLogFilter
