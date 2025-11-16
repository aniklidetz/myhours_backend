"""
Analytics and summary views for payroll module.

Contains endpoints for:
- Payroll analytics and statistics
- Monthly payroll summaries
"""

import logging
from datetime import date

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.db.models import Avg, Count, DecimalField, Sum
from django.db.models.functions import Coalesce

# Import from parent module to make test mocking work correctly
from payroll import views as payroll_views

from ..models import MonthlyPayrollSummary

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payroll_analytics(request):
    """
    Get payroll analytics and statistics
    """
    try:
        # Check permissions
        employee_profile = payroll_views.get_user_employee_profile(request.user)
        if not employee_profile or employee_profile.role not in ["accountant", "admin"]:
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )

        # Get parameters
        year = request.GET.get("year", date.today().year)

        try:
            year = int(year)
        except ValueError:
            return Response(
                {"error": "Invalid year"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Get aggregated data
        monthly_stats = (
            MonthlyPayrollSummary.objects.filter(year=year)
            .values("month")
            .annotate(
                total_employees=Count("employee", distinct=True),
                total_gross_pay_sum=Coalesce(
                    Sum("total_gross_pay"), 0, output_field=DecimalField()
                ),
                avg_gross_pay=Coalesce(
                    Avg("total_gross_pay"), 0, output_field=DecimalField()
                ),
                total_hours_sum=Coalesce(
                    Sum("total_hours"), 0, output_field=DecimalField()
                ),
                avg_hours=Coalesce(Avg("total_hours"), 0, output_field=DecimalField()),
            )
            .order_by("month")
        )

        # Convert queryset to list
        stats_list = list(monthly_stats)

        # If no data exists, provide default structure with required keys
        if not stats_list:
            return Response(
                {
                    "year": year,
                    "monthly_statistics": [],
                    "total_employees": 0,
                    "total_gross_pay_sum": 0,
                    "avg_gross_pay": 0,
                    "total_hours_sum": 0,
                    "avg_hours": 0,
                }
            )

        return Response({"year": year, "monthly_statistics": stats_list})

    except Exception as e:
        logger.exception("Error in payroll_analytics")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def monthly_payroll_summary(request):
    """
    Fast endpoint for getting data from MonthlyPayrollSummary without recalculation
    """
    try:
        # Check access permissions
        employee_profile = payroll_views.get_user_employee_profile(request.user)
        if not employee_profile:
            return Response(
                {"error": "User does not have an employee profile"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get year and month
        year = request.GET.get("year")
        month = request.GET.get("month")

        if year and month:
            try:
                year = int(year)
                month = int(month)
            except (ValueError, TypeError):
                current_date = date.today()
                year = current_date.year
                month = current_date.month
        else:
            current_date = date.today()
            year = current_date.year
            month = current_date.month

        # Determine which data is being requested
        if employee_profile.role in ["accountant", "admin"] or request.user.is_staff:
            # Admin/accountant can see everyone
            summaries = (
                MonthlyPayrollSummary.objects.filter(year=year, month=month)
                .select_related("employee")
                .prefetch_related("employee__salaries")
            )
        else:
            # Regular employee can only see themselves
            summaries = (
                MonthlyPayrollSummary.objects.filter(
                    employee=employee_profile, year=year, month=month
                )
                .select_related("employee")
                .prefetch_related("employee__salaries")
            )

        # Form the response
        payroll_data = []
        for summary in summaries:
            employee = summary.employee
            salary_info = (
                employee.salary_info if hasattr(employee, "salary_info") else None
            )

            payroll_data.append(
                {
                    "id": employee.id,
                    "employee": {
                        "id": employee.id,
                        "name": employee.get_full_name(),
                        "email": employee.email,
                        "role": employee.role,
                    },
                    "period": f"{year}-{month:02d}",
                    "calculation_type": (
                        salary_info.calculation_type if salary_info else "unknown"
                    ),
                    "currency": salary_info.currency if salary_info else "ILS",
                    "month": month,
                    "year": year,
                    "total_hours": float(summary.total_hours),
                    "total_salary": float(summary.total_gross_pay),
                    "regular_hours": float(summary.regular_hours),
                    "overtime_hours": float(summary.overtime_hours),
                    "holiday_hours": float(summary.holiday_hours),
                    "shabbat_hours": float(summary.sabbath_hours),
                    "worked_days": summary.worked_days,
                    "base_salary": (
                        float(salary_info.base_salary or 0) if salary_info else 0
                    ),
                    "hourly_rate": (
                        float(salary_info.hourly_rate or 0) if salary_info else 0
                    ),
                    "compensatory_days": summary.compensatory_days_earned,
                    "bonus": 0,
                    "detailed_breakdown": summary.calculation_details or {},
                }
            )

        # If no data - return empty array (without recalculation!)
        return Response(payroll_data)

    except Exception as e:
        logger.exception("Error in monthly_payroll_summary")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
