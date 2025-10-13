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

        # Use PayrollService for salary calculation
        try:
            from django.utils import timezone

            from payroll.services.contracts import CalculationContext
            from payroll.services.payroll_service import PayrollService

            now = timezone.now()
            context = CalculationContext(
                employee_id=salary.employee.id,
                year=now.year,
                month=now.month,
                user_id=(
                    self.request.user.id if self.request.user.is_authenticated else None
                ),
                fast_mode=False,  # Full calculation for manual recalculation
            )
            service = PayrollService(context)
            result = service.calculate()

            salary.save()
            return Response(
                {
                    "message": "Salary recalculated",
                    "result": {
                        "total_salary": float(result.total_salary),
                        "total_hours": float(result.total_hours),
                        "regular_hours": float(result.regular_hours),
                        "overtime_hours": float(result.overtime_hours),
                    },
                }
            )
        except Exception as e:
            # Fallback behavior
            salary.save()
            return Response({"message": "Salary recalculated", "error": str(e)})

        salary.save()
        return Response({"message": "Salary recalculated"})


class WorkLogViewSet(viewsets.ModelViewSet):
    """Endpoints for work time logs"""

    queryset = WorkLog.objects.all().order_by("-check_in")
    serializer_class = WorkLogSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = WorkLogFilter
