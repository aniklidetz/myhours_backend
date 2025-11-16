"""
Earnings calculation views for payroll module.

Contains endpoints for calculating earnings, including:
- Enhanced earnings calculation
- Backward compatible earnings
- Daily earnings calculation helper
"""

import calendar
import logging
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.db import DatabaseError, OperationalError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

# Import from parent module to make test mocking work correctly
from payroll import views as payroll_views
from users.models import Employee
from worktime.models import WorkLog

from ..enhanced_serializers import EnhancedEarningsSerializer
from ..models import MonthlyPayrollSummary, Salary
from ..services.contracts import CalculationContext
from ..services.enums import CalculationStrategy, EmployeeType
from ..services.payroll_service import PayrollService

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def enhanced_earnings(request):
    """
    Enhanced earnings endpoint with stable error handling and safe parameter parsing
    """
    try:
        user = request.user

        # Safely read parameters
        qs = request.query_params
        month_str = qs.get("month")
        year_str = qs.get("year")
        employee_id = qs.get("employee_id")

        now = timezone.now()
        try:
            month = int(month_str) if month_str is not None else now.month
            year = int(year_str) if year_str is not None else now.year
            if not (1 <= month <= 12):
                return Response({"detail": "Invalid month"}, status=400)
        except (TypeError, ValueError):
            return Response({"detail": "Invalid year/month"}, status=400)

        # Select employee safely
        if employee_id:
            # Admin/accountant can view any employee
            if not (
                getattr(user, "is_staff", False)
                or getattr(user, "is_accountant", False)
            ):
                return Response({"detail": "Forbidden"}, status=403)
            employee = get_object_or_404(Employee, pk=employee_id)
        else:
            # Regular user - only themselves
            employee = payroll_views.get_user_employee_profile(user)
            if not employee:
                return Response({"detail": "No employee profile"}, status=404)

        # Check if employee has salary configuration
        salary = employee.salaries.filter(is_active=True).first()
        if not salary:
            # No salary configuration - return special response
            return Response(
                {
                    "employee": {
                        "id": employee.id,
                        "name": employee.get_full_name(),
                        "role": employee.role,
                    },
                    "calculation_type": "not_configured",
                    "currency": "ILS",
                    "month": month,
                    "year": year,
                    "total_hours": 0,
                    "total_salary": 0,
                    "regular_hours": 0,
                    "overtime_hours": 0,
                    "holiday_hours": 0,
                    "shabbat_hours": 0,
                    "worked_days": 0,
                    "compensatory_days": 0,
                    "bonus": 0,
                    "error": "No salary configuration",
                    "message": f"Employee {employee.get_full_name()} has no salary configuration",
                },
                status=200,
            )

        # Calculate through serializer
        instance = SimpleNamespace(employee=employee, year=year, month=month)
        serializer = EnhancedEarningsSerializer()
        result = serializer.to_representation(instance)

        # Ensure year and month are always in the response
        result["year"] = year
        result["month"] = month

        # If cache exists - override summary fields
        summary = (
            MonthlyPayrollSummary.objects.filter(
                employee=employee, year=year, month=month
            )
            .order_by("-id")
            .first()
        )
        if summary:
            result["total_salary"] = float(summary.total_salary or Decimal("0"))
            # This field is also sometimes needed by tests
            result["proportional_monthly"] = float(
                summary.proportional_monthly or Decimal("0")
            )

        return Response(result, status=200)

    except (DatabaseError, OperationalError) as e:
        logger.exception("enhanced_earnings database error", exc_info=e)
        return Response({"detail": "database error"}, status=500)
    except Employee.DoesNotExist:
        return Response({"detail": "Employee not found"}, status=404)
    except Exception as e:
        from django.http import Http404

        if isinstance(e, Http404):
            return Response({"detail": "Not found"}, status=404)
        logger.exception("enhanced_earnings failed", exc_info=e)
        return Response({"detail": "internal server error"}, status=500)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def backward_compatible_earnings(request):
    """
    Backward compatible endpoint for earnings with correct calculations
    """
    # Get employee data
    employee_id = request.GET.get("employee_id")

    if employee_id:
        # Admin/accountant requests specific employee
        if not payroll_views.check_admin_or_accountant_role(request.user):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )

        try:
            target_employee = Employee.objects.get(id=employee_id)
        except Employee.DoesNotExist:
            return Response(
                {"error": "Employee not found"}, status=status.HTTP_404_NOT_FOUND
            )
    else:
        # User requests their own data
        target_employee = payroll_views.get_user_employee_profile(request.user)
        if not target_employee:
            return Response(
                {"error": "User does not have an employee profile"},
                status=status.HTTP_404_NOT_FOUND,
            )

    # Get monthly calculations based on request parameters
    try:
        # Parse year and month from request parameters
        year = request.GET.get("year")
        month = request.GET.get("month")

        if year and month:
            try:
                year = int(year)
                month = int(month)
                current_date = date(year, month, 1)  # First day of requested month
            except (ValueError, TypeError):
                # Invalid year/month, return to current date
                current_date = date.today()
        else:
            # No parameters, use current date
            current_date = date.today()

        salary = target_employee.salary_info
        if salary is None:
            # No active salary configuration - return data with zero salary but show hours
            start_date = date(current_date.year, current_date.month, 1)
            _, last_day = calendar.monthrange(current_date.year, current_date.month)
            end_date = date(current_date.year, current_date.month, last_day)

            # Correct work log filtering
            work_logs = WorkLog.objects.filter(
                employee=target_employee, check_out__isnull=False
            ).filter(
                Q(check_in__date__lte=end_date) & Q(check_out__date__gte=start_date)
            )

            total_hours = sum(log.get_total_hours() for log in work_logs)
            worked_days = work_logs.values("check_in__date").distinct().count()

            return Response(
                {
                    "employee": {
                        "id": target_employee.id,
                        "name": target_employee.get_full_name(),
                        "role": target_employee.role,
                    },
                    "calculation_type": "not_configured",
                    "currency": "ILS",
                    "date": current_date.isoformat(),
                    "month": current_date.month,
                    "year": current_date.year,
                    "period": "monthly",
                    "total_hours": float(total_hours),
                    "total_salary": 0,
                    "regular_hours": float(total_hours),
                    "overtime_hours": 0,
                    "holiday_hours": 0,
                    "shabbat_hours": 0,
                    "worked_days": worked_days,
                    "compensatory_days": 0,
                    "bonus": 0,
                    "error": "No salary configuration",
                    "message": "Employee has no salary configuration. Please contact HR.",
                }
            )

        # Using new service for correct overtime calculation
        logger.info(f"USING ENHANCED SERVICE for employee {target_employee.id}")
        try:
            # Use PayrollService directly instead of adapter
            active_salary = target_employee.salaries.filter(is_active=True).first()
            employee_type = (
                EmployeeType.HOURLY
                if active_salary and active_salary.calculation_type == "hourly"
                else EmployeeType.MONTHLY
            )

            context = CalculationContext(
                employee_id=target_employee.id,
                year=current_date.year,
                month=current_date.month,
                user_id=1,  # System user
                employee_type=employee_type,
                fast_mode=False,
            )
            service = PayrollService()
            enhanced_result = service.calculate(context, CalculationStrategy.ENHANCED)
            enhanced_breakdown = enhanced_result  # Direct access to calculated data

            return Response(
                {
                    "employee": {
                        "id": target_employee.id,
                        "name": target_employee.get_full_name(),
                        "role": target_employee.role,
                    },
                    "calculation_type": salary.calculation_type,
                    "currency": salary.currency,
                    "date": current_date.isoformat(),
                    "month": current_date.month,
                    "year": current_date.year,
                    "period": "monthly",
                    "regular_hours": float(enhanced_result.get("regular_hours", 0)),
                    "overtime_hours": float(enhanced_result.get("overtime_hours", 0)),
                    "holiday_hours": float(enhanced_result.get("holiday_hours", 0)),
                    "shabbat_hours": float(enhanced_result.get("sabbath_hours", 0)),
                    "total_salary": float(enhanced_result.get("total_gross_pay", 0)),
                    "worked_days": enhanced_result.get("worked_days", 0),
                    "compensatory_days": enhanced_result.get(
                        "compensatory_days_earned", 0
                    ),
                    "bonus": 0.0,
                    "enhanced_breakdown": {
                        "regular_pay": enhanced_breakdown.get("regular_pay", 0),
                        "overtime_breakdown": {
                            "overtime_125_hours": enhanced_breakdown.get(
                                "overtime_125_hours", 0
                            ),
                            "overtime_125_pay": enhanced_breakdown.get(
                                "overtime_125_pay", 0
                            ),
                            "overtime_150_hours": enhanced_breakdown.get(
                                "overtime_150_hours", 0
                            ),
                            "overtime_150_pay": enhanced_breakdown.get(
                                "overtime_150_pay", 0
                            ),
                        },
                        "special_days": {
                            "sabbath_pay": enhanced_breakdown.get(
                                "sabbath_regular_pay", 0
                            )
                            + enhanced_breakdown.get("sabbath_overtime_pay", 0),
                            "holiday_pay": enhanced_breakdown.get(
                                "holiday_regular_pay", 0
                            )
                            + enhanced_breakdown.get("holiday_overtime_pay", 0),
                        },
                        "rates": {
                            "base_hourly": float(salary.hourly_rate),
                            "overtime_125": float(salary.hourly_rate * 1.25),
                            "overtime_150": float(salary.hourly_rate * 1.50),
                            "sabbath_rate": float(salary.hourly_rate * 1.50),
                            "holiday_rate": float(salary.hourly_rate * 1.50),
                        },
                    },
                }
            )
        except Exception:
            logger.exception(
                "Error using enhanced service",
                extra={
                    "employee_id": getattr(target_employee, "id", None),
                    "action": "enhanced_service_error",
                },
            )
            # Fallback to old logic
            pass

        if salary.calculation_type == "hourly":
            # Check hourly rate
            if not salary.hourly_rate or salary.hourly_rate <= 0:
                return Response(
                    {
                        "error": "Invalid hourly rate configuration",
                        "details": f"Employee {target_employee.get_full_name()} has no valid hourly rate",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Using PayrollService with new architecture
            try:
                active_salary = target_employee.salaries.filter(is_active=True).first()
                employee_type = (
                    EmployeeType.HOURLY
                    if active_salary and active_salary.calculation_type == "hourly"
                    else EmployeeType.MONTHLY
                )

                context = CalculationContext(
                    employee_id=target_employee.id,
                    year=current_date.year,
                    month=current_date.month,
                    user_id=1,  # System user
                    employee_type=employee_type,
                    fast_mode=True,
                )
                service = PayrollService()
                service_result = service.calculate(
                    context, CalculationStrategy.ENHANCED
                )

                # Use result directly (no separate detailed_breakdown method needed)
                detailed_breakdown = service_result

            except Exception as calc_error:
                logger.exception(
                    "Error in backward_compatible_earnings calculation",
                    extra={
                        "employee_id": getattr(target_employee, "id", None),
                        "action": "backward_calc_error",
                    },
                )
                # Return safe fallback
                return Response(
                    {
                        "detail": "Unable to calculate enhanced earnings",
                        "fallback": True,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Enhanced breakdown with correct data
            hourly_rate = salary.hourly_rate or Decimal("0")

            # Extract data from service_result
            regular_hours = Decimal(str(service_result.get("regular_hours", 0)))
            regular_pay = regular_hours * hourly_rate

            overtime_hours = Decimal(str(service_result.get("overtime_hours", 0)))
            sabbath_hours = Decimal(str(service_result.get("sabbath_hours", 0)))
            holiday_hours = Decimal(str(service_result.get("holiday_hours", 0)))
            worked_days = service_result.get("worked_days", 0)

            # Correct overtime breakdown calculation (125% and 150%)
            overtime_125_hours = detailed_breakdown.get("overtime_125_hours", 0)
            overtime_150_hours = detailed_breakdown.get("overtime_150_hours", 0)
            overtime_125_pay = detailed_breakdown.get("overtime_125_pay", 0)
            overtime_150_pay = detailed_breakdown.get("overtime_150_pay", 0)

            sabbath_pay = detailed_breakdown.get(
                "sabbath_regular_pay", 0
            ) + detailed_breakdown.get("sabbath_overtime_pay", 0)
            holiday_pay = detailed_breakdown.get(
                "holiday_regular_pay", 0
            ) + detailed_breakdown.get("holiday_overtime_pay", 0)

            # Structure matching React Native expectations
            enhanced_response = {
                "calculation_type": salary.calculation_type,
                "compensatory_days": service_result.get("compensatory_days_earned", 0),
                "currency": salary.currency,
                "date": current_date.isoformat(),
                "employee": {
                    "email": target_employee.email,
                    "id": target_employee.id,
                    "name": target_employee.get_full_name(),
                    "role": target_employee.role,
                },
                "holiday_hours": float(holiday_hours),
                "legal_violations": service_result.get("legal_violations", []),
                "minimum_wage_applied": service_result.get(
                    "minimum_wage_applied", False
                ),
                "month": current_date.month,
                "overtime_hours": float(overtime_hours),
                "period": "monthly",
                "regular_hours": float(regular_hours),
                "shabbat_hours": float(sabbath_hours),
                "total_hours": float(service_result.get("total_hours", 0)),
                "total_salary": float(service_result.get("total_gross_pay", 0)),
                "warnings": service_result.get("warnings", []),
                "worked_days": worked_days,
                "year": current_date.year,
                # Enhanced breakdown with detailed Sabbath breakdown
                "enhanced_breakdown": {
                    "regular_pay": float(regular_pay),
                    "work_sessions": service_result.get("work_sessions_count", 0),
                    "overtime_breakdown": {
                        "overtime_125_hours": float(overtime_125_hours),
                        "overtime_125_pay": float(overtime_125_pay),
                        "overtime_150_hours": float(overtime_150_hours),
                        "overtime_150_pay": float(overtime_150_pay),
                    },
                    "special_days": {
                        "sabbath_regular_hours": detailed_breakdown.get(
                            "sabbath_regular_hours", 0
                        ),
                        "sabbath_regular_pay": detailed_breakdown.get(
                            "sabbath_regular_pay", 0
                        ),
                        "sabbath_overtime_hours": detailed_breakdown.get(
                            "sabbath_overtime_hours", 0
                        ),
                        "sabbath_overtime_pay": detailed_breakdown.get(
                            "sabbath_overtime_pay", 0
                        ),
                        "sabbath_pay": float(sabbath_pay),
                        "holiday_pay": float(holiday_pay),
                    },
                    "rates": {
                        "base_hourly": float(salary.hourly_rate),
                        "overtime_125": float(salary.hourly_rate * Decimal("1.25")),
                        "overtime_150": float(salary.hourly_rate * Decimal("1.5")),
                        "sabbath_rate": float(salary.hourly_rate * Decimal("1.5")),
                        "holiday_rate": float(salary.hourly_rate * Decimal("1.5")),
                    },
                },
                # Detailed breakdown for transparency
                "detailed_breakdown": detailed_breakdown,
                # Bonus information (legacy field expected by UI)
                "bonus": float(
                    overtime_125_pay + overtime_150_pay + sabbath_pay + holiday_pay
                ),
                # Additional fields for UI
                "hourly_rate": float(salary.hourly_rate),
                "regular_pay_amount": float(regular_pay),
                "work_sessions_count": service_result.get("work_sessions_count", 0),
            }

        else:
            # Employee on monthly salary - use PayrollService
            try:
                active_salary = target_employee.salaries.filter(is_active=True).first()
                employee_type = (
                    EmployeeType.HOURLY
                    if active_salary and active_salary.calculation_type == "hourly"
                    else EmployeeType.MONTHLY
                )

                context = CalculationContext(
                    employee_id=target_employee.id,
                    year=current_date.year,
                    month=current_date.month,
                    user_id=1,  # System user
                    employee_type=employee_type,
                    fast_mode=True,
                )
                service = PayrollService()
                service_result = service.calculate(
                    context, CalculationStrategy.ENHANCED
                )
            except Exception as calc_error:
                logger.exception(
                    "Error in backward_compatible_earnings for monthly employee",
                    extra={
                        "employee_id": getattr(target_employee, "id", None),
                        "action": "monthly_calc_error",
                    },
                )
                # Return safe fallback for monthly employees
                from core.logging_utils import err_tag

                return Response(
                    {
                        "detail": "Unable to calculate monthly salary",
                        "error": err_tag(calc_error),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Calculate actual worked hours for monthly employees
            # Calculate exact month boundaries
            start_date = date(current_date.year, current_date.month, 1)
            _, last_day = calendar.monthrange(current_date.year, current_date.month)
            end_date = date(current_date.year, current_date.month, last_day)

            # Get work logs for month with correct filtering
            work_logs = WorkLog.objects.filter(
                employee=target_employee, check_out__isnull=False
            ).filter(
                Q(check_in__date__lte=end_date) & Q(check_out__date__gte=start_date)
            )

            # Calculate total worked hours
            total_hours = sum(log.get_total_hours() for log in work_logs)

            enhanced_response = {
                "base_salary": float(
                    service_result.get("base_salary", salary.base_salary or 0)
                ),
                "calculation_type": salary.calculation_type,
                "compensatory_days": service_result.get("compensatory_days_earned", 0),
                "currency": salary.currency,
                "date": current_date.isoformat(),
                "employee": {
                    "email": target_employee.email,
                    "id": target_employee.id,
                    "name": target_employee.get_full_name(),
                    "role": target_employee.role,
                },
                "holiday_hours": float(service_result.get("holiday_hours", 0)),
                "month": current_date.month,
                "overtime_hours": float(service_result.get("overtime_hours", 0)),
                "period": "monthly",
                "shabbat_hours": float(service_result.get("sabbath_hours", 0)),
                "total_extra": float(service_result.get("total_extra", 0)),
                "total_hours": float(total_hours),
                "total_salary": float(service_result.get("total_gross_pay", 0)),
                "total_working_days": service_result.get("total_working_days", 0),
                "work_proportion": float(service_result.get("work_proportion", 0)),
                "worked_days": work_logs.filter(check_out__isnull=False)
                .values("check_in__date")
                .distinct()
                .count()
                or work_logs.values("check_in__date").distinct().count(),
                "year": current_date.year,
                # Bonus information (extras for monthly employees)
                "bonus": float(service_result.get("total_extra", 0)),
                # Additional fields for UI
                "work_sessions_count": work_logs.count(),
                "attendance_percentage": (
                    (
                        (
                            work_logs.filter(check_out__isnull=False)
                            .values("check_in__date")
                            .distinct()
                            .count()
                            or work_logs.values("check_in__date").distinct().count()
                        )
                        / service_result.get("total_working_days", 1)
                    )
                    * 100
                    if service_result.get("total_working_days", 0) > 0
                    else 0
                ),
            }

        # Return as array if frontend expects a list
        if request.GET.get("format") == "list":
            return Response([enhanced_response])

        return Response(enhanced_response)

    except Exception as e:
        from core.logging_utils import err_tag

        logger.error(f"Error in backward_compatible_earnings: {err_tag(e)}")
        return Response(
            {"detail": "Unable to process the request"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def _calculate_hourly_daily_earnings(salary, work_logs, target_date, total_hours):
    """
    Daily earnings calculation for hourly employees with correct coefficients
    """
    from integrations.models import Holiday

    # Convert total_hours to Decimal for precise calculations
    total_hours = Decimal(str(total_hours))

    # Check if this is a holiday or Sabbath
    holiday = Holiday.objects.filter(date=target_date).first()

    breakdown = {
        "regular_hours": 0,
        "overtime_hours": 0,
        "holiday_hours": 0,
        "shabbat_hours": 0,
    }

    total_earnings = Decimal("0.00")

    if holiday and holiday.is_shabbat:
        # Sabbath work - 150% for regular hours, 175% for overtime
        # Check if any work log for this day is a night shift
        is_night_shift = False
        for work_log in work_logs:
            if work_log.check_in.date() == target_date:
                # Check if this is a night shift (simple check based on start time)
                check_in_hour = work_log.check_in.hour
                # Night shift: starts between 18:00-06:00 of next day
                if check_in_hour >= 18 or check_in_hour <= 6:
                    is_night_shift = True
                    break

        # Get daily norm based on shift type
        if is_night_shift:
            daily_norm = Decimal("7")  # Night shift: max 7 regular hours
        else:
            daily_norm = Decimal("8.6")  # Regular daily norm

        sabbath_breakdown = {}
        if total_hours <= daily_norm:
            # All Sabbath hours at 150%
            sabbath_150_pay = total_hours * (salary.hourly_rate * Decimal("1.5"))
            total_earnings = sabbath_150_pay
            sabbath_breakdown["sabbath_150_hours"] = float(total_hours)
            sabbath_breakdown["sabbath_150_pay"] = float(sabbath_150_pay)
            sabbath_breakdown["rate_150"] = float(salary.hourly_rate * Decimal("1.5"))
        else:
            # Regular Sabbath hours (150%) + Overtime Sabbath hours (175%)
            regular_sabbath = daily_norm
            overtime_sabbath = total_hours - daily_norm

            sabbath_150_pay = regular_sabbath * (salary.hourly_rate * Decimal("1.5"))
            sabbath_175_pay = overtime_sabbath * (salary.hourly_rate * Decimal("1.75"))
            total_earnings += sabbath_150_pay + sabbath_175_pay

            sabbath_breakdown["sabbath_150_hours"] = float(regular_sabbath)
            sabbath_breakdown["sabbath_150_pay"] = float(sabbath_150_pay)
            sabbath_breakdown["rate_150"] = float(salary.hourly_rate * Decimal("1.5"))
            sabbath_breakdown["sabbath_175_hours"] = float(overtime_sabbath)
            sabbath_breakdown["sabbath_175_pay"] = float(sabbath_175_pay)
            sabbath_breakdown["rate_175"] = float(salary.hourly_rate * Decimal("1.75"))

        breakdown["shabbat_hours"] = float(total_hours)
        breakdown["shabbat_breakdown"] = sabbath_breakdown
    elif holiday and holiday.is_holiday:
        # Holiday work - 150%
        total_earnings = total_hours * (salary.hourly_rate * Decimal("1.5"))
        breakdown["holiday_hours"] = float(total_hours)
    else:
        # Regular day - use correct daily norm based on weekday and shift type
        # Check if any work log for this day is a night shift
        is_night_shift = False
        for work_log in work_logs:
            if work_log.check_in.date() == target_date:
                # Check if this is a night shift (simple check based on start time)
                check_in_hour = work_log.check_in.hour
                # Night shift: starts between 18:00-06:00 of next day
                if check_in_hour >= 18 or check_in_hour <= 6:
                    is_night_shift = True
                    break

        # Get daily norm based on shift type
        if is_night_shift:
            daily_norm = Decimal("7")  # Night shift: max 7 regular hours
        else:
            # Friday has shortened hours
            if target_date.weekday() == 4:
                daily_norm = Decimal("7.6")
            else:
                daily_norm = Decimal("8.6")

        if total_hours <= daily_norm:
            # Regular hours
            total_earnings = total_hours * salary.hourly_rate
            breakdown["regular_hours"] = float(total_hours)
        else:
            # Regular + overtime hours
            regular_hours = daily_norm
            overtime_hours = total_hours - daily_norm

            # Regular hours at base rate
            total_earnings += regular_hours * salary.hourly_rate
            breakdown["regular_hours"] = float(regular_hours)

            # Overtime calculation with detailed breakdown
            overtime_earnings = Decimal("0")
            overtime_breakdown = {}

            if overtime_hours <= Decimal("2"):
                # First 2 hours at 125%
                overtime_125 = overtime_hours
                overtime_125_pay = overtime_125 * (salary.hourly_rate * Decimal("1.25"))
                overtime_earnings += overtime_125_pay
                overtime_breakdown["overtime_125_hours"] = float(overtime_125)
                overtime_breakdown["overtime_125_pay"] = float(overtime_125_pay)
                overtime_breakdown["rate_125"] = float(
                    salary.hourly_rate * Decimal("1.25")
                )
            else:
                # First 2 hours at 125%, rest at 150%
                overtime_125 = Decimal("2")
                overtime_150 = overtime_hours - Decimal("2")
                overtime_125_pay = overtime_125 * (salary.hourly_rate * Decimal("1.25"))
                overtime_150_pay = overtime_150 * (salary.hourly_rate * Decimal("1.5"))
                overtime_earnings += overtime_125_pay + overtime_150_pay
                overtime_breakdown["overtime_125_hours"] = float(overtime_125)
                overtime_breakdown["overtime_125_pay"] = float(overtime_125_pay)
                overtime_breakdown["rate_125"] = float(
                    salary.hourly_rate * Decimal("1.25")
                )
                overtime_breakdown["overtime_150_hours"] = float(overtime_150)
                overtime_breakdown["overtime_150_pay"] = float(overtime_150_pay)
                overtime_breakdown["rate_150"] = float(
                    salary.hourly_rate * Decimal("1.5")
                )

            total_earnings += overtime_earnings
            breakdown["overtime_hours"] = float(overtime_hours)
            breakdown["overtime_breakdown"] = overtime_breakdown

    return {
        "total_earnings": round(total_earnings, 2),
        "hours_worked": float(total_hours),
        "breakdown": breakdown,
        "base_rate": salary.hourly_rate,
        "rates_applied": {
            "regular": salary.hourly_rate,
            "overtime_125": salary.hourly_rate * Decimal("1.25"),
            "overtime_150": salary.hourly_rate * Decimal("1.5"),
            "holiday": salary.hourly_rate * Decimal("1.5"),
            "sabbath_150": salary.hourly_rate * Decimal("1.5"),
            "sabbath_175": salary.hourly_rate * Decimal("1.75"),
        },
    }
