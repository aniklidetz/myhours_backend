"""
Calculation and recalculation views for payroll module.

Contains endpoints for:
- Daily payroll calculations
- Payroll recalculation triggers
"""

import calendar
import logging
from datetime import date, datetime

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# Import from parent module to make test mocking work correctly
from payroll import views as payroll_views
from users.models import Employee

from ..models import DailyPayrollCalculation
from ..services.contracts import CalculationContext
from ..services.enums import CalculationStrategy, EmployeeType
from ..services.payroll_service import PayrollService

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def daily_payroll_calculations(request):
    """
    Get daily payroll calculations for a specific employee or all employees
    """
    try:
        employee_profile = payroll_views.get_user_employee_profile(request.user)
        if not employee_profile:
            return Response(
                {"error": "User does not have an employee profile"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Parse date range
        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")

        if start_date and end_date:
            try:
                start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
                end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                return Response(
                    {"error": "Invalid date format. Use YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            # Default to current month
            today = date.today()
            start_date = date(today.year, today.month, 1)
            _, last_day = calendar.monthrange(today.year, today.month)
            end_date = date(today.year, today.month, last_day)

        # Determine what data to fetch
        if employee_profile.role in ["accountant", "admin"] or request.user.is_staff:
            # Admin can see all
            calculations = (
                DailyPayrollCalculation.objects.filter(
                    work_date__gte=start_date, work_date__lte=end_date
                )
                .select_related("employee")
                .order_by("-work_date")
            )
        else:
            # Regular employees see only their data
            calculations = DailyPayrollCalculation.objects.filter(
                employee=employee_profile,
                work_date__gte=start_date,
                work_date__lte=end_date,
            ).order_by("-work_date")

        # Serialize data
        data = []
        for calc in calculations:
            data.append(
                {
                    "id": calc.id,
                    "employee": {
                        "id": calc.employee.id,
                        "name": calc.employee.get_full_name(),
                        "email": calc.employee.email,
                    },
                    "work_date": calc.work_date.isoformat(),
                    "total_hours": float(
                        calc.regular_hours
                        + calc.overtime_hours_1
                        + calc.overtime_hours_2
                        + calc.sabbath_regular_hours
                        + calc.sabbath_overtime_hours_1
                        + calc.sabbath_overtime_hours_2
                    ),
                    "base_pay": float(calc.base_pay),
                    "bonus_pay": float(calc.bonus_pay),
                    "total_gross_pay": float(calc.total_gross_pay),
                    "is_holiday": calc.is_holiday,
                    "is_sabbath": calc.is_sabbath,
                    "holiday_name": calc.holiday_name or "",
                }
            )

        return Response(data)

    except Exception as e:
        logger.exception("Error in daily_payroll_calculations")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def recalculate_payroll(request):
    """
    Trigger payroll recalculation for a specific period
    """
    try:
        # Check permissions
        employee_profile = payroll_views.get_user_employee_profile(request.user)
        if not employee_profile or employee_profile.role not in ["accountant", "admin"]:
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )

        # Get parameters
        year = request.data.get("year")
        month = request.data.get("month")
        employee_id = request.data.get("employee_id")

        if not year or not month:
            return Response(
                {"error": "Year and month are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            year = int(year)
            month = int(month)
        except ValueError:
            return Response(
                {"error": "Invalid year or month"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Trigger recalculation
        if employee_id:
            # Recalculate for specific employee
            # Validate employee_id is a valid integer
            try:
                employee_id = int(employee_id)
            except (ValueError, TypeError):
                return Response(
                    {"error": "Invalid employee_id"}, status=status.HTTP_400_BAD_REQUEST
                )

            try:
                target_employee = Employee.objects.get(id=employee_id)

                # Use PayrollService with new architecture
                active_salary = target_employee.salaries.filter(is_active=True).first()
                employee_type = (
                    EmployeeType.HOURLY
                    if active_salary and active_salary.calculation_type == "hourly"
                    else EmployeeType.MONTHLY
                )

                context = CalculationContext(
                    employee_id=target_employee.id,
                    year=year,
                    month=month,
                    user_id=1,  # System user
                    employee_type=employee_type,
                    force_recalculate=True,
                )
                service = PayrollService()
                result = service.calculate(context, CalculationStrategy.ENHANCED)

                return Response(
                    {
                        "status": "success",
                        "message": f"Payroll recalculated for {target_employee.get_full_name()}",
                        "result": result,
                    }
                )
            except Employee.DoesNotExist:
                return Response(
                    {"error": "Employee not found"}, status=status.HTTP_404_NOT_FOUND
                )
        else:
            # Recalculate for all employees
            employees = Employee.objects.filter(is_active=True)
            success_count = 0

            for employee in employees:
                try:
                    # Use PayrollService with new architecture
                    active_salary = employee.salaries.filter(is_active=True).first()
                    employee_type = (
                        EmployeeType.HOURLY
                        if active_salary and active_salary.calculation_type == "hourly"
                        else EmployeeType.MONTHLY
                    )

                    context = CalculationContext(
                        employee_id=employee.id,
                        year=year,
                        month=month,
                        user_id=1,  # System user
                        employee_type=employee_type,
                        force_recalculate=True,
                    )
                    service = PayrollService()
                    service.calculate(context, CalculationStrategy.ENHANCED)
                    success_count += 1
                except Exception as e:
                    from core.logging_utils import err_tag

                    logger.error(
                        "Failed to recalculate",
                        extra={"err": err_tag(e), "employee_id": employee.id},
                    )

            return Response(
                {
                    "status": "success",
                    "message": f"Payroll recalculated for {success_count} employees",
                }
            )

    except Exception as e:
        logger.exception("Error in recalculate_payroll")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
