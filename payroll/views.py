import calendar
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from django.db.models import Q, Sum
from django.utils import timezone

from users.models import Employee
from users.permissions import IsEmployeeOrAbove
from worktime.models import WorkLog

from .enhanced_serializers import (
    CompensatoryDayDetailSerializer,
    EnhancedEarningsSerializer,
)
from .models import (
    CompensatoryDay,
    DailyPayrollCalculation,
    MonthlyPayrollSummary,
    Salary,
)
from .serializers import SalarySerializer

logger = logging.getLogger(__name__)


def get_user_employee_profile(user):
    """Helper function to get employee profile"""
    try:
        return user.employees.first()
    except AttributeError:
        return None


def check_admin_or_accountant_role(user):
    """Helper function to check if user has admin or accountant role"""
    employee = get_user_employee_profile(user)
    return employee and employee.role in ["accountant", "admin"]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payroll_list(request):
    """
    ОПТИМИЗИРОВАННЫЙ список зарплат с минимальными данными для быстрой загрузки
    """
    try:
        # Check if user is active
        if not request.user.is_active:
            return Response(
                {"error": "User account is inactive"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check access rights
        from core.logging_utils import hash_user_id

        logger.info(
            "Payroll request received",
            extra={
                "user_hash": hash_user_id(request.user.id),
                "has_profile": hasattr(request.user, "employee_profile"),
            },
        )

        employee_profile = get_user_employee_profile(request.user)
        if not employee_profile:
            logger.warning(f"User {request.user.username} has no employee profile")
            return Response(
                {"error": "User does not have an employee profile"},
                status=status.HTTP_404_NOT_FOUND,
            )

        user_role = employee_profile.role
        logger.info("User role checked", extra={"role": user_role})

        if user_role in ["admin", "accountant"]:
            # Админ - получаем всех сотрудников с зарплатами
            employees = (
                Employee.objects.filter(salaries__is_active=True)
                .prefetch_related("salaries")
                .distinct()
            )
            logger.info(
                "Admin payroll view", extra={"employees_count": employees.count()}
            )
        else:
            # Обычный сотрудник - видит только свои данные
            employees = (
                Employee.objects.filter(
                    id=employee_profile.id, salaries__is_active=True
                )
                .prefetch_related("salaries")
                .distinct()
            )
            logger.info(
                "Employee payroll view", extra={"employee_id": employee_profile.id}
            )

        # Получаем год и месяц из параметров
        year = request.GET.get("year")
        month = request.GET.get("month")

        if year and month:
            try:
                year = int(year)
                month = int(month)
                current_date = date(year, month, 1)
            except (ValueError, TypeError):
                current_date = date.today()
        else:
            current_date = date.today()

        payroll_data = []

        # Получаем все рабочие логи за месяц одним запросом
        import calendar

        from django.db.models import Count, Q, Sum

        start_date = date(current_date.year, current_date.month, 1)
        _, last_day = calendar.monthrange(current_date.year, current_date.month)
        end_date = date(current_date.year, current_date.month, last_day)

        # ✅ НОВОЕ: Сначала пытаемся получить данные из БД, затем рассчитываем
        from .models import MonthlyPayrollSummary

        # Получаем предварительно рассчитанные данные из БД
        existing_summaries = (
            MonthlyPayrollSummary.objects.filter(
                employee__in=employees, year=current_date.year, month=current_date.month
            )
            .select_related("employee")
            .prefetch_related("employee__salaries")
        )

        # Создаем словарь для быстрого доступа
        summary_dict = {summary.employee_id: summary for summary in existing_summaries}

        # Если есть готовые данные для всех сотрудников - используем их
        employees_count = (
            len(employees) if isinstance(employees, list) else employees.count()
        )
        if len(summary_dict) == employees_count:
            logger.info("Using cached payroll data for all employees")
            payroll_data = []
            for summary in existing_summaries:
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
                        "calculation_type": (
                            salary_info.calculation_type if salary_info else "unknown"
                        ),
                        "currency": salary_info.currency if salary_info else "ILS",
                        "total_salary": float(summary.total_gross_pay),
                        "total_hours": float(summary.total_hours),
                        "worked_days": summary.worked_days,
                        "work_sessions": (
                            summary.calculation_details.get("work_sessions_count", 0)
                            if summary.calculation_details
                            else 0
                        ),
                        "period": f"{current_date.year}-{current_date.month:02d}",
                        "status": "calculated",
                    }
                )
        else:
            # Используем оптимизированный сервис только если нет готовых данных
            from .optimized_service import optimized_payroll_service

            try:
                # Преобразуем в QuerySet если это список
                if isinstance(employees, list):
                    employee_ids = [emp.id for emp in employees]
                    employees_queryset = Employee.objects.filter(
                        id__in=employee_ids
                    ).prefetch_related("salaries")
                else:
                    employees_queryset = employees

                # Оптимизированный bulk-расчет для всех сотрудников
                payroll_data = optimized_payroll_service.calculate_bulk_payroll(
                    employees_queryset, current_date.year, current_date.month
                )

                # Логируем статистику оптимизации
                optimization_stats = optimized_payroll_service.get_optimization_stats()
                logger.info(
                    "Payroll optimization stats",
                    extra={
                        "user_hash": hash_user_id(request.user.id),
                        "optimization_stats": optimization_stats,
                    },
                )

            except Exception as e:
                logger.error(
                    f"Optimized service failed, falling back to legacy calculation: {e}"
                )
                # Fallback to legacy logic
                payroll_data = _legacy_payroll_calculation(
                    employees, current_date, start_date, end_date
                )

        logger.info(
            "Payroll list completed",
            extra={
                "user_hash": hash_user_id(request.user.id),
                "records_count": len(payroll_data),
            },
        )
        return Response(payroll_data)

    except Exception as e:
        from core.logging_utils import err_tag

        logger.error(f"Error in payroll_list: {err_tag(e)}")
        return Response(
            {"detail": "Unable to process the request"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def _legacy_payroll_calculation(employees, current_date, start_date, end_date):
    """
    Legacy fallback calculation (original logic)
    """
    from django.db.models import Prefetch

    # Prefetch всех рабочих логов для всех сотрудников одним запросом
    employees = employees.prefetch_related(
        Prefetch(
            "work_logs",
            queryset=WorkLog.objects.filter(
                check_out__isnull=False,
                check_in__date__gte=start_date,
                check_in__date__lte=end_date,
            ),
            to_attr="filtered_work_logs",
        )
    )

    payroll_data = []

    # Быстрый расчёт без внешних API
    for employee in employees:
        try:
            salary = employee.salary_info
            logger.info(
                "Processing employee",
                extra={
                    "employee_id": getattr(employee, "id", None),
                    "action": "payroll_processing",
                },
            )

            # Используем prefetched данные вместо отдельного запроса
            work_logs = employee.filtered_work_logs

            # Быстрый подсчёт
            total_hours = float(sum(log.get_total_hours() for log in work_logs))
            worked_days = work_logs.values("check_in__date").distinct().count()
            work_sessions = work_logs.count()

            logger.info(
                f"  Work logs: {work_sessions}, Hours: {total_hours}, Days: {worked_days}"
            )

            # Быстрый расчёт зарплаты без внешних API для списочного view
            if salary.calculation_type == "hourly":
                # Используем enhanced service в быстром режиме
                from .services import PayrollCalculationService

                try:
                    payroll_service = PayrollCalculationService(
                        employee, current_date.year, current_date.month, fast_mode=True
                    )
                    result = payroll_service.calculate_monthly_salary_enhanced()
                    estimated_salary = float(result.get("total_gross_pay", 0))
                    logger.info(
                        "Enhanced calculation completed",
                        extra={
                            "employee_id": getattr(employee, "id", None),
                            "action": "enhanced_calc",
                            "calculation_type": "enhanced_fast",
                        },
                    )
                except Exception as e:
                    logger.warning(
                        "Enhanced calculation failed, using fallback",
                        extra={
                            "employee_id": getattr(employee, "id", None),
                            "action": "calc_fallback",
                            "error_type": type(e).__name__,
                        },
                    )
                    base_rate = float(salary.hourly_rate or 0)
                    estimated_salary = (
                        total_hours * base_rate * 1.3
                    )  # Примерная оценка с премиями
            else:
                # For monthly employees, use proportional calculation
                try:
                    result = salary.calculate_monthly_salary(
                        current_date.month, current_date.year
                    )
                    estimated_salary = float(result.get("total_salary", 0))
                    logger.info(
                        "Monthly calculation completed",
                        extra={
                            "employee_id": getattr(employee, "id", None),
                            "action": "monthly_calc",
                            "calculation_type": "monthly_proportional",
                        },
                    )
                except Exception as e:
                    logger.warning(
                        "Monthly calculation failed, using base salary",
                        extra={
                            "employee_id": getattr(employee, "id", None),
                            "action": "monthly_fallback",
                            "error_type": type(e).__name__,
                        },
                    )
                    estimated_salary = float(salary.base_salary or 0)

            employee_data = {
                "id": employee.id,
                "employee": {
                    "id": employee.id,
                    "name": employee.get_full_name(),
                    "email": employee.email,
                    "role": employee.role,
                },
                "calculation_type": salary.calculation_type,
                "currency": salary.currency,
                "total_salary": estimated_salary,
                "total_hours": total_hours,
                "worked_days": worked_days,
                "work_sessions": work_sessions,
                "period": f"{current_date.year}-{current_date.month:02d}",
                "status": "active",
            }

            payroll_data.append(employee_data)
            logger.info(
                "Employee added to payroll data",
                extra={
                    "employee_id": getattr(employee, "id", None),
                    "action": "payroll_added",
                },
            )

        except Exception as e:
            logger.error(
                "Error calculating payroll for employee",
                extra={
                    "employee_id": getattr(employee, "id", None),
                    "action": "payroll_error",
                    "error_type": type(e).__name__,
                },
            )
            continue

    return payroll_data


# ИСПРАВЛЕНО: Используем исправленный PayrollCalculationService
from .services import EnhancedPayrollCalculationService


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def enhanced_earnings(request):
    """
    Enhanced earnings endpoint with correct 125%/150% overtime calculations
    """
    # Remove the decorator from backward_compatible_earnings call since we already have DRF context
    # Import the actual function logic instead of calling decorated function
    employee_id = request.GET.get("employee_id")

    if employee_id:
        # Admin/accountant requesting specific employee
        if not check_admin_or_accountant_role(request.user):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )

        try:
            from users.models import Employee

            target_employee = Employee.objects.get(id=employee_id)
        except Employee.DoesNotExist:
            return Response(
                {"error": "Employee not found"}, status=status.HTTP_404_NOT_FOUND
            )
    else:
        # User requesting their own data
        target_employee = get_user_employee_profile(request.user)
        if not target_employee:
            return Response(
                {"error": "User does not have an employee profile"},
                status=status.HTTP_404_NOT_FOUND,
            )

    # Get calculations for the specified month/year
    try:
        from datetime import date

        # Parse year and month from request parameters
        year = request.GET.get("year")
        month = request.GET.get("month")

        if year and month:
            try:
                year = int(year)
                month = int(month)
                current_date = date(year, month, 1)
            except (ValueError, TypeError):
                current_date = date.today()
        else:
            current_date = date.today()

        salary = target_employee.salary_info
        if salary is None:
            # No active salary configuration - return data with zero salary but show hours
            import calendar

            from worktime.models import WorkLog

            start_date = date(current_date.year, current_date.month, 1)
            _, last_day = calendar.monthrange(current_date.year, current_date.month)
            end_date = date(current_date.year, current_date.month, last_day)

            # Get work logs properly filtered
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
                    "message": f"Employee {target_employee.get_full_name()} has no salary configuration",
                }
            )

        # First check if we have cached data in MonthlyPayrollSummary
        try:
            monthly_summary = MonthlyPayrollSummary.objects.filter(
                employee=target_employee,
                year=current_date.year,
                month=current_date.month,
            ).first()

            if monthly_summary:
                # Use cached data from database
                # Calculate total working days for the month
                from calendar import monthrange

                _, total_working_days = monthrange(
                    current_date.year, current_date.month
                )
                work_proportion = (
                    (monthly_summary.worked_days / total_working_days) * 100
                    if total_working_days > 0
                    else 0
                )

                service_result = {
                    "total_gross_pay": monthly_summary.total_gross_pay,
                    "total_hours": monthly_summary.total_hours,
                    "regular_hours": monthly_summary.regular_hours,
                    "overtime_hours": monthly_summary.overtime_hours,
                    "holiday_hours": monthly_summary.holiday_hours,
                    "shabbat_hours": monthly_summary.sabbath_hours,
                    "worked_days": monthly_summary.worked_days,
                    "compensatory_days_earned": monthly_summary.compensatory_days_earned,
                    "base_pay": monthly_summary.base_pay,
                    "overtime_pay": monthly_summary.overtime_pay,
                    "holiday_pay": monthly_summary.holiday_pay,
                    "sabbath_pay": monthly_summary.sabbath_pay,
                    "calculation_type": salary.calculation_type,
                    "currency": salary.currency,
                    "work_sessions_count": (
                        monthly_summary.calculation_details.get(
                            "work_sessions_count", 0
                        )
                        if monthly_summary.calculation_details
                        else 0
                    ),
                    "total_working_days": total_working_days,
                    "work_proportion": work_proportion,
                }
                detailed_breakdown = monthly_summary.calculation_details or {}
                logger.info(
                    f"Using cached payroll data for {target_employee.get_full_name()} {current_date.year}-{current_date.month}"
                )
            else:
                # Handle different calculation types as fallback
                if salary.calculation_type == "monthly":
                    # For monthly employees, use the models.py calculation with proportional logic
                    service_result = salary.calculate_monthly_salary(
                        current_date.month, current_date.year
                    )
                    detailed_breakdown = {
                        "regular_hours": 0,
                        "overtime_125_hours": 0,
                        "overtime_150_hours": 0,
                        "holiday_regular_hours": 0,
                        "sabbath_regular_hours": service_result.get("shabbat_hours", 0),
                    }
                else:
                    # For hourly employees, use EnhancedPayrollCalculationService
                    from .services import EnhancedPayrollCalculationService

                    service = EnhancedPayrollCalculationService(
                        target_employee,
                        current_date.year,
                        current_date.month,
                        fast_mode=True,
                    )
                    service_result = service.calculate_monthly_salary()

                    # Get detailed breakdown for better transparency
                    detailed_breakdown = service.get_detailed_breakdown()

        except Exception:
            logger.exception(
                "Error in enhanced_earnings calculation",
                extra={
                    "employee_id": getattr(target_employee, "id", None),
                    "action": "calc_error",
                },
            )
            return Response(
                {
                    "error": "Calculation failed",
                    "details": "An internal error occurred during salary calculation. Please contact support.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Prepare enhanced response structure with different field mapping for monthly vs hourly
        if salary.calculation_type == "monthly":
            # Monthly employee response uses different field names
            response_data = {
                "employee": {
                    "id": target_employee.id,
                    "name": target_employee.get_full_name(),
                    "email": target_employee.email,
                    "role": target_employee.role,
                },
                "period": f"{current_date.year}-{current_date.month:02d}",
                "calculation_type": salary.calculation_type,
                "currency": salary.currency,
                "month": current_date.month,
                "year": current_date.year,
                "total_hours": float(service_result.get("total_hours", 0)),
                "total_salary": float(service_result.get("total_gross_pay", 0)),
                "regular_hours": float(service_result.get("regular_hours", 0)),
                "overtime_hours": float(service_result.get("overtime_hours", 0)),
                "holiday_hours": float(service_result.get("holiday_hours", 0)),
                "shabbat_hours": float(service_result.get("shabbat_hours", 0)),
                "worked_days": service_result.get("worked_days", 0),
                "base_salary": float(
                    service_result.get("base_pay", salary.base_salary or 0)
                ),
                "hourly_rate": 0,
                "total_working_days": service_result.get("total_working_days", 22),
                "work_proportion": float(service_result.get("work_proportion", 0.0)),
                "compensatory_days": service_result.get("compensatory_days_earned", 0),
                "bonus": 0,
                "detailed_breakdown": detailed_breakdown,
            }
        else:
            # Hourly employee response - get actual breakdown from daily calculations

            # Get detailed breakdown from daily calculations
            daily_calcs = DailyPayrollCalculation.objects.filter(
                employee=target_employee,
                work_date__year=current_date.year,
                work_date__month=current_date.month,
            ).aggregate(
                total_regular=Sum("regular_hours"),
                total_overtime_1=Sum("overtime_hours_1"),
                total_overtime_2=Sum("overtime_hours_2"),
                sabbath_regular=Sum("regular_hours", filter=Q(is_sabbath=True)),
                sabbath_overtime_1=Sum("overtime_hours_1", filter=Q(is_sabbath=True)),
                sabbath_overtime_2=Sum("overtime_hours_2", filter=Q(is_sabbath=True)),
                holiday_regular=Sum("regular_hours", filter=Q(is_holiday=True)),
                holiday_overtime_1=Sum("overtime_hours_1", filter=Q(is_holiday=True)),
                holiday_overtime_2=Sum("overtime_hours_2", filter=Q(is_holiday=True)),
            )

            # Convert None values to 0 and calculate totals
            regular_hours = float(daily_calcs["total_regular"] or 0)
            overtime_125_hours = float(daily_calcs["total_overtime_1"] or 0)
            overtime_150_hours = float(daily_calcs["total_overtime_2"] or 0)
            sabbath_regular_hours = float(daily_calcs["sabbath_regular"] or 0)
            sabbath_overtime_125 = float(daily_calcs["sabbath_overtime_1"] or 0)
            sabbath_overtime_150 = float(daily_calcs["sabbath_overtime_2"] or 0)
            holiday_regular_hours = float(daily_calcs["holiday_regular"] or 0)
            holiday_overtime_125 = float(daily_calcs["holiday_overtime_1"] or 0)
            holiday_overtime_150 = float(daily_calcs["holiday_overtime_2"] or 0)

            total_overtime_hours = overtime_125_hours + overtime_150_hours
            total_sabbath_hours = (
                sabbath_regular_hours + sabbath_overtime_125 + sabbath_overtime_150
            )
            total_holiday_hours = (
                holiday_regular_hours + holiday_overtime_125 + holiday_overtime_150
            )

            # Build enhanced breakdown with actual data
            enhanced_breakdown = {
                "regular_hours": regular_hours,
                "overtime_breakdown": {
                    "overtime_125_hours": overtime_125_hours,
                    "overtime_150_hours": overtime_150_hours,
                    "total_overtime": total_overtime_hours,
                },
                "sabbath_breakdown": {
                    "sabbath_regular_hours": sabbath_regular_hours,
                    "sabbath_overtime_125": sabbath_overtime_125,
                    "sabbath_overtime_150": sabbath_overtime_150,
                    "total_sabbath": total_sabbath_hours,
                },
                "holiday_breakdown": {
                    "holiday_regular_hours": holiday_regular_hours,
                    "holiday_overtime_125": holiday_overtime_125,
                    "holiday_overtime_150": holiday_overtime_150,
                    "total_holiday": total_holiday_hours,
                },
                "rates": {
                    "base_hourly": float(salary.hourly_rate),
                    "overtime_125": float(salary.hourly_rate * Decimal("1.25")),
                    "overtime_150": float(salary.hourly_rate * Decimal("1.50")),
                    "sabbath_150": float(salary.hourly_rate * Decimal("1.50")),
                    "sabbath_175": float(salary.hourly_rate * Decimal("1.75")),
                    "holiday_150": float(salary.hourly_rate * Decimal("1.50")),
                },
            }

            response_data = {
                "employee": {
                    "id": target_employee.id,
                    "name": target_employee.get_full_name(),
                    "email": target_employee.email,
                    "role": target_employee.role,
                },
                "period": f"{current_date.year}-{current_date.month:02d}",
                "calculation_type": salary.calculation_type,
                "currency": salary.currency,
                "month": current_date.month,
                "year": current_date.year,
                "total_hours": float(service_result.get("total_hours", 0)),
                "total_salary": float(service_result.get("total_gross_pay", 0)),
                "regular_hours": regular_hours,
                "overtime_hours": total_overtime_hours,
                "holiday_hours": total_holiday_hours,
                "shabbat_hours": total_sabbath_hours,
                "worked_days": service_result.get("worked_days", 0),
                "base_salary": float(salary.base_salary or 0),
                "hourly_rate": float(salary.hourly_rate or 0),
                "total_working_days": service_result.get("total_working_days", 0),
                "work_proportion": service_result.get("work_proportion", 0.0),
                "compensatory_days": service_result.get("compensatory_days_earned", 0),
                "bonus": 0,
                "detailed_breakdown": enhanced_breakdown,
            }

        return Response(response_data)

    except Exception as e:
        from core.logging_utils import err_tag

        logger.error(f"Error in enhanced_earnings: {err_tag(e)}")
        return Response(
            {"detail": "Unable to process the request"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def daily_payroll_calculations(request):
    """
    Get daily payroll calculations for a specific employee or all employees
    """
    try:
        employee_profile = get_user_employee_profile(request.user)
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
        employee_profile = get_user_employee_profile(request.user)
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
        from .services import EnhancedPayrollCalculationService

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
                service = EnhancedPayrollCalculationService(
                    target_employee, year, month
                )
                result = service.calculate_monthly_salary_enhanced()

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
                    service = EnhancedPayrollCalculationService(employee, year, month)
                    service.calculate_monthly_salary_enhanced()
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payroll_analytics(request):
    """
    Get payroll analytics and statistics
    """
    try:
        # Check permissions
        employee_profile = get_user_employee_profile(request.user)
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
        from django.db.models import Avg, Count, DecimalField, Sum
        from django.db.models.functions import Coalesce

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
    БЫСТРЫЙ endpoint для получения данных из MonthlyPayrollSummary без пересчета
    """
    try:
        # Проверяем права доступа
        employee_profile = get_user_employee_profile(request.user)
        if not employee_profile:
            return Response(
                {"error": "User does not have an employee profile"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Получаем год и месяц
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

        # Определяем какие данные запрашиваются
        if employee_profile.role in ["accountant", "admin"] or request.user.is_staff:
            # Админ/бухгалтер может видеть всех
            summaries = (
                MonthlyPayrollSummary.objects.filter(year=year, month=month)
                .select_related("employee")
                .prefetch_related("employee__salaries")
            )
        else:
            # Обычный сотрудник видит только себя
            summaries = (
                MonthlyPayrollSummary.objects.filter(
                    employee=employee_profile, year=year, month=month
                )
                .select_related("employee")
                .prefetch_related("employee__salaries")
            )

        # Формируем ответ
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

        # Если данных нет - возвращаем пустой массив (без пересчета!)
        return Response(payroll_data)

    except Exception as e:
        logger.exception("Error in monthly_payroll_summary")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def backward_compatible_earnings(request):
    """
    ИСПРАВЛЕНО: Обратно совместимый endpoint для earnings с корректными расчётами
    """
    # Получение данных сотрудника
    employee_id = request.GET.get("employee_id")

    if employee_id:
        # Админ/бухгалтер запрашивает конкретного сотрудника
        if not check_admin_or_accountant_role(request.user):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )

        try:
            from users.models import Employee

            target_employee = Employee.objects.get(id=employee_id)
        except Employee.DoesNotExist:
            return Response(
                {"error": "Employee not found"}, status=status.HTTP_404_NOT_FOUND
            )
    else:
        # Пользователь запрашивает свои данные
        target_employee = get_user_employee_profile(request.user)
        if not target_employee:
            return Response(
                {"error": "User does not have an employee profile"},
                status=status.HTTP_404_NOT_FOUND,
            )

    # Получение расчётов по месяцам на основе параметров запроса
    try:
        from datetime import date

        # Парсим год и месяц из параметров запроса
        year = request.GET.get("year")
        month = request.GET.get("month")

        if year and month:
            try:
                year = int(year)
                month = int(month)
                current_date = date(year, month, 1)  # Первый день запрашиваемого месяца
            except (ValueError, TypeError):
                # Неверный год/месяц, возвращаемся к текущей дате
                current_date = date.today()
        else:
            # Нет параметров, используем текущую дату
            current_date = date.today()

        salary = target_employee.salary_info
        if salary is None:
            # Нет активной конфигурации зарплаты - возвращаем данные с нулевой зарплатой, но показываем часы
            import calendar

            from worktime.models import WorkLog

            start_date = date(current_date.year, current_date.month, 1)
            _, last_day = calendar.monthrange(current_date.year, current_date.month)
            end_date = date(current_date.year, current_date.month, last_day)

            # ИСПРАВЛЕНО: Правильная фильтрация рабочих логов
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

        # ИСПРАВЛЕНИЕ: Используем новый сервис для правильного расчета overtime
        logger.info(f"🔍 USING ENHANCED SERVICE for employee {target_employee.id}")
        try:
            from .services import PayrollCalculationService

            service = PayrollCalculationService(
                target_employee, current_date.year, current_date.month
            )
            enhanced_result = service.calculate_monthly_salary()
            enhanced_breakdown = service.get_detailed_breakdown()

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
            # Проверяем часовую ставку
            if not salary.hourly_rate or salary.hourly_rate <= 0:
                return Response(
                    {
                        "error": "Invalid hourly rate configuration",
                        "details": f"Employee {target_employee.get_full_name()} has no valid hourly rate",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # ИСПРАВЛЕНО: Используем исправленный PayrollCalculationService в быстром режиме
            try:
                from .services import EnhancedPayrollCalculationService

                service = EnhancedPayrollCalculationService(
                    target_employee,
                    current_date.year,
                    current_date.month,
                    fast_mode=True,
                )
                service_result = service.calculate_monthly_salary()

                # Получаем детализированный разбор для большей прозрачности
                detailed_breakdown = service.get_detailed_breakdown()

            except Exception as calc_error:
                logger.exception(
                    "Error in backward_compatible_earnings calculation",
                    extra={
                        "employee_id": getattr(target_employee, "id", None),
                        "action": "backward_calc_error",
                    },
                )
                # Возвращаем безопасный fallback
                return Response(
                    {
                        "detail": "Unable to calculate enhanced earnings",
                        "fallback": True,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # ИСПРАВЛЕНО: Улучшенный breakdown с корректными данными
            hourly_rate = salary.hourly_rate or Decimal("0")

            # Извлекаем данные из service_result
            regular_hours = Decimal(str(service_result.get("regular_hours", 0)))
            regular_pay = regular_hours * hourly_rate

            overtime_hours = Decimal(str(service_result.get("overtime_hours", 0)))
            sabbath_hours = Decimal(str(service_result.get("sabbath_hours", 0)))
            holiday_hours = Decimal(str(service_result.get("holiday_hours", 0)))
            worked_days = service_result.get("worked_days", 0)

            # ИСПРАВЛЕНО: Правильный расчёт breakdown сверхурочных (125% и 150%)
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

            # Структура, соответствующая ожиданиям React Native
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
                # ИСПРАВЛЕНО: Улучшенный breakdown с детализированным разбором по шабату
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
                # Детализированный breakdown для прозрачности
                "detailed_breakdown": detailed_breakdown,
                # Bonus информация (legacy поле, которое ожидает UI)
                "bonus": float(
                    overtime_125_pay + overtime_150_pay + sabbath_pay + holiday_pay
                ),
                # Дополнительные поля для UI
                "hourly_rate": float(salary.hourly_rate),
                "regular_pay_amount": float(regular_pay),
                "work_sessions_count": service_result.get("work_sessions_count", 0),
            }

        else:
            # Сотрудник на месячном окладе - упрощённая структура
            try:
                service = PayrollCalculationService(
                    target_employee,
                    current_date.year,
                    current_date.month,
                    fast_mode=True,
                )
                service_result = service.calculate_monthly_salary()
            except Exception as calc_error:
                logger.exception(
                    "Error in backward_compatible_earnings for monthly employee",
                    extra={
                        "employee_id": getattr(target_employee, "id", None),
                        "action": "monthly_calc_error",
                    },
                )
                # Возвращаем безопасный fallback для месячных сотрудников
                from core.logging_utils import err_tag

                return Response(
                    {
                        "detail": "Unable to calculate monthly salary",
                        "error": err_tag(calc_error),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # ИСПРАВЛЕНО: Вычисляем реальные отработанные часы для месячных сотрудников
            import calendar

            from worktime.models import WorkLog

            # Вычисляем точные границы месяца
            start_date = date(current_date.year, current_date.month, 1)
            _, last_day = calendar.monthrange(current_date.year, current_date.month)
            end_date = date(current_date.year, current_date.month, last_day)

            # ИСПРАВЛЕНО: Получаем рабочие логи для месяца с правильной фильтрацией
            work_logs = WorkLog.objects.filter(
                employee=target_employee, check_out__isnull=False
            ).filter(
                Q(check_in__date__lte=end_date) & Q(check_out__date__gte=start_date)
            )

            # Вычисляем общее количество отработанных часов
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
                "total_hours": float(
                    total_hours
                ),  # ← ИСПРАВЛЕНО: теперь считаем реальные часы
                "total_salary": float(service_result.get("total_gross_pay", 0)),
                "total_working_days": service_result.get("total_working_days", 0),
                "work_proportion": float(service_result.get("work_proportion", 0)),
                "worked_days": work_logs.filter(check_out__isnull=False)
                .values("check_in__date")
                .distinct()
                .count()
                or work_logs.values("check_in__date").distinct().count(),
                "year": current_date.year,
                # Bonus информация (extras для месячных сотрудников)
                "bonus": float(service_result.get("total_extra", 0)),
                # Дополнительные поля для UI
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

        # Возвращаем как массив, если фронтенд ожидает список
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


# ИСПРАВЛЕНО: Improved function for calculating daily earnings with fixed PayrollCalculationService
def _calculate_hourly_daily_earnings(salary, work_logs, target_date, total_hours):
    """
    ИСПРАВЛЕНО: Расчёт дневных earnings для почасовых сотрудников с правильными коэффициентами
    """

    from integrations.models import Holiday

    # Конвертируем total_hours в Decimal для точных вычислений
    total_hours = Decimal(str(total_hours))

    # Проверяем, является ли это праздником или шабатом
    holiday = Holiday.objects.filter(date=target_date).first()

    breakdown = {
        "regular_hours": 0,
        "overtime_hours": 0,
        "holiday_hours": 0,
        "shabbat_hours": 0,
    }

    total_earnings = Decimal("0.00")

    if holiday and holiday.is_shabbat:
        # ИСПРАВЛЕНО: Работа в шабат - 150% для обычных часов, 175% для сверхурочных
        # Проверяем, является ли какой-либо рабочий лог для этого дня ночной сменой
        is_night_shift = False
        for work_log in work_logs:
            if work_log.check_in.date() == target_date:
                # Проверяем, является ли это ночной сменой (простая проверка на основе времени начала)
                check_in_hour = work_log.check_in.hour
                # Ночная смена: начинается между 18:00-06:00 следующего дня
                if check_in_hour >= 18 or check_in_hour <= 6:
                    is_night_shift = True
                    break

        # Получаем дневную норму на основе типа смены
        if is_night_shift:
            daily_norm = Decimal("7")  # Ночная смена: макс. 7 обычных часов
        else:
            daily_norm = Decimal("8.6")  # Обычная дневная норма

        sabbath_breakdown = {}
        if total_hours <= daily_norm:
            # Все шабатные часы по 150%
            sabbath_150_pay = total_hours * (salary.hourly_rate * Decimal("1.5"))
            total_earnings = sabbath_150_pay
            sabbath_breakdown["sabbath_150_hours"] = float(total_hours)
            sabbath_breakdown["sabbath_150_pay"] = float(sabbath_150_pay)
            sabbath_breakdown["rate_150"] = float(salary.hourly_rate * Decimal("1.5"))
        else:
            # ИСПРАВЛЕНО: Обычные шабатные часы (150%) + Сверхурочные шабатные часы (175%)
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
        # Работа в праздник - 150%
        total_earnings = total_hours * (salary.hourly_rate * Decimal("1.5"))
        breakdown["holiday_hours"] = float(total_hours)
    else:
        # ИСПРАВЛЕНО: Обычный день - используем правильную дневную норму на основе дня недели и типа смены
        # Проверяем, является ли какой-либо рабочий лог для этого дня ночной сменой
        is_night_shift = False
        for work_log in work_logs:
            if work_log.check_in.date() == target_date:
                # Проверяем, является ли это ночной сменой (простая проверка на основе времени начала)
                check_in_hour = work_log.check_in.hour
                # Ночная смена: начинается между 18:00-06:00 следующего дня
                if check_in_hour >= 18 or check_in_hour <= 6:
                    is_night_shift = True
                    break

        # ИСПРАВЛЕНО: Получаем дневную норму на основе типа смены
        if is_night_shift:
            daily_norm = Decimal("7")  # Ночная смена: макс. 7 обычных часов
        else:
            # Пятница имеет сокращённые часы
            if target_date.weekday() == 4:
                daily_norm = Decimal("7.6")
            else:
                daily_norm = Decimal("8.6")

        if total_hours <= daily_norm:
            # Обычные часы
            total_earnings = total_hours * salary.hourly_rate
            breakdown["regular_hours"] = float(total_hours)
        else:
            # ИСПРАВЛЕНО: Обычные + сверхурочные часы
            regular_hours = daily_norm
            overtime_hours = total_hours - daily_norm

            # Обычные часы по базовой ставке
            total_earnings += regular_hours * salary.hourly_rate
            breakdown["regular_hours"] = float(regular_hours)

            # ИСПРАВЛЕНО: Расчёт сверхурочных с детализированным breakdown
            overtime_earnings = Decimal("0")
            overtime_breakdown = {}

            if overtime_hours <= Decimal("2"):
                # Первые 2 часа по 125%
                overtime_125 = overtime_hours
                overtime_125_pay = overtime_125 * (salary.hourly_rate * Decimal("1.25"))
                overtime_earnings += overtime_125_pay
                overtime_breakdown["overtime_125_hours"] = float(overtime_125)
                overtime_breakdown["overtime_125_pay"] = float(overtime_125_pay)
                overtime_breakdown["rate_125"] = float(
                    salary.hourly_rate * Decimal("1.25")
                )
            else:
                # Первые 2 часа по 125%, остальные по 150%
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
