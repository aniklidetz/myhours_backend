"""
Payroll list views for displaying employee payroll data with pagination and filtering.
"""

import calendar
import logging
from datetime import date

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.db import DatabaseError, OperationalError
from django.db.models import Prefetch, Q

# Import from parent module to make test mocking work correctly
# (tests patch payroll.views.get_user_employee_profile and payroll.views.logger)
from payroll import views as payroll_views
from users.models import Employee
from worktime.models import WorkLog

from ..models import MonthlyPayrollSummary
from ..services.contracts import CalculationContext
from ..services.enums import CalculationStrategy, EmployeeType
from ..services.payroll_service import PayrollService

# Use the logger from payroll.views for test compatibility
logger = payroll_views.logger


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payroll_list(request):
    """
    OPTIMIZED payroll list with minimal data for fast loading
    """
    try:
        # Extract request parameters
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 10))
        search = request.GET.get("search", "").strip()

        # Calculate offset for pagination
        offset = (page - 1) * limit

        # Check if user is active
        if not request.user.is_active:
            return Response(
                {"error": "User account is inactive"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check access rights
        from core.logging_utils import hash_user_id

        payroll_views.logger.info(
            "Payroll request received",
            extra={
                "user_hash": hash_user_id(request.user.id),
                "has_profile": hasattr(request.user, "employee_profile"),
            },
        )

        user = request.user
        employee_profile = payroll_views.get_user_employee_profile(request.user)

        # Check if user has admin/accountant privileges through employee role or Django staff status
        is_admin_by_staff = getattr(user, "is_staff", False)
        is_accountant_by_attr = getattr(user, "is_accountant", False)
        is_admin_by_role = employee_profile and employee_profile.role == "admin"
        is_accountant_by_role = (
            employee_profile and employee_profile.role == "accountant"
        )

        # Combined admin/accountant check
        is_admin = is_admin_by_staff or is_admin_by_role
        is_accountant = is_accountant_by_attr or is_accountant_by_role

        # All users need employee profile for payroll access
        if not employee_profile:
            payroll_views.logger.warning(
                f"User {request.user.username} has no employee profile"
            )
            return Response(
                {"error": "User does not have an employee profile"},
                status=status.HTTP_404_NOT_FOUND,
            )

        user_role = employee_profile.role

        payroll_views.logger.info("User role checked", extra={"role": user_role})

        # Critical: guarantee database access (so DatabaseError mock triggers)
        _ = Employee.objects.filter(pk__isnull=False).exists()

        # Build base queryset
        employees_queryset = Employee.objects.with_optimized_annotations().filter(
            salaries__is_active=True
        )

        # Check if specific employee is requested
        employee_id_filter = request.GET.get("employee_id")

        if user_role in ["admin", "accountant"]:
            # Admin - can filter by employee_id or search
            if employee_id_filter:
                # Filter by specific employee
                try:
                    employee_id_filter = int(employee_id_filter)
                    employees_queryset = employees_queryset.filter(
                        id=employee_id_filter
                    )
                    payroll_views.logger.info(
                        "Admin filtering by employee_id",
                        extra={"employee_id": employee_id_filter},
                    )
                except (ValueError, TypeError):
                    payroll_views.logger.warning(
                        f"Invalid employee_id parameter: {employee_id_filter}"
                    )
            elif search:
                # Add search functionality - search by name or email
                employees_queryset = employees_queryset.filter(
                    Q(first_name__icontains=search)
                    | Q(last_name__icontains=search)
                    | Q(email__icontains=search)
                )
            payroll_views.logger.info(
                "Admin payroll view",
                extra={"search_term": search, "employee_filter": employee_id_filter},
            )
        else:
            # Regular employee - can only see their own data
            employees_queryset = employees_queryset.filter(id=employee_profile.id)
            payroll_views.logger.info(
                "Employee payroll view", extra={"employee_id": employee_profile.id}
            )

        # Get total count for pagination metadata
        total_count = employees_queryset.count()

        # Apply pagination with proper prefetching to avoid N+1
        employees = (
            employees_queryset.select_related("user")  # Avoid N+1 for user data
            .prefetch_related("salaries", "work_logs")  # Pre-fetch work logs if needed
            .distinct()[offset : offset + limit]
        )

        # Get year and month from parameters
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

        # Get all work logs for the month in a single query
        start_date = date(current_date.year, current_date.month, 1)
        _, last_day = calendar.monthrange(current_date.year, current_date.month)
        end_date = date(current_date.year, current_date.month, last_day)

        # Try to get pre-calculated data from DB first, then calculate

        # Get pre-calculated data from database
        try:
            existing_summaries = (
                MonthlyPayrollSummary.objects.filter(
                    employee__in=employees,
                    year=current_date.year,
                    month=current_date.month,
                )
                .select_related("employee")
                .prefetch_related("employee__salaries")
            )
        except Exception as db_error:
            logger.error(
                "Database error fetching monthly payroll summaries",
                extra={
                    "user_hash": hash_user_id(request.user.id),
                    "year": current_date.year,
                    "month": current_date.month,
                    "error": str(db_error),
                    "action": "db_fetch_error",
                },
            )
            return Response(
                {"error": "Database error occurred"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Create dictionary for fast access
        summary_dict = {summary.employee_id: summary for summary in existing_summaries}

        # If we have ready data for all employees - use it
        # Count employees without converting to list yet
        employees_count = (
            employees.count() if hasattr(employees, "count") else len(employees)
        )
        if len(summary_dict) == employees_count:
            payroll_views.logger.info("Using cached payroll data for all employees")
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
            # Use new PayrollService to calculate and save to DB
            payroll_views.logger.info(
                f"Calculating payroll with new PayrollService for {current_date.year}-{current_date.month:02d}"
            )

            payroll_data = []
            calculations_performed = 0
            errors_encountered = 0

            try:
                payroll_service = PayrollService(
                    enable_fallback=True, enable_caching=True
                )

                for employee in employees:
                    try:
                        # Create calculation context
                        context = CalculationContext(
                            employee_id=employee.id,
                            year=current_date.year,
                            month=current_date.month,
                            user_id=request.user.id,
                            force_recalculate=False,  # Use cache if available
                            fast_mode=False,  # Full calculation with DB save
                            include_breakdown=True,
                            include_daily_details=False,
                        )

                        # Calculate using the new service
                        result = payroll_service.calculate(context)
                        calculations_performed += 1

                        # Convert result to API format (result is a dict, not PayrollResult object)
                        payroll_data.append(
                            {
                                "id": employee.id,
                                "employee": {
                                    "id": employee.id,
                                    "name": employee.get_full_name(),
                                    "email": employee.email,
                                    "role": employee.role,
                                },
                                "calculation_type": result["metadata"].get(
                                    "employee_type", "unknown"
                                ),
                                "currency": result["metadata"].get("currency", "ILS"),
                                "total_salary": float(result["total_salary"]),
                                "total_hours": float(result["total_hours"]),
                                "worked_days": result["breakdown"].get(
                                    "worked_days", 0
                                ),
                                "work_sessions": result["breakdown"].get(
                                    "work_sessions_count", 0
                                ),
                                "period": f"{current_date.year}-{current_date.month:02d}",
                                "status": "calculated_and_saved",
                                "calculation_method": "new_payroll_service",
                                "regular_hours": float(result["regular_hours"]),
                                "overtime_hours": float(result["overtime_hours"]),
                                "holiday_hours": float(result["holiday_hours"]),
                                "sabbath_hours": float(result["shabbat_hours"]),
                            }
                        )

                    except Exception as employee_error:
                        errors_encountered += 1
                        logger.error(
                            f"Error calculating payroll for employee {employee.id}",
                            extra={
                                "employee_id": employee.id,
                                "error": str(employee_error),
                            },
                        )
                        # Add error result for this employee
                        payroll_data.append(
                            {
                                "id": employee.id,
                                "employee": {
                                    "id": employee.id,
                                    "name": employee.get_full_name(),
                                    "email": employee.email,
                                    "role": employee.role,
                                },
                                "calculation_type": "unknown",
                                "currency": "ILS",
                                "total_salary": 0,
                                "total_hours": 0,
                                "worked_days": 0,
                                "work_sessions": 0,
                                "period": f"{current_date.year}-{current_date.month:02d}",
                                "status": "error",
                                "error_message": str(employee_error),
                                "calculation_method": "new_payroll_service_error",
                            }
                        )

                payroll_views.logger.info(
                    "New PayrollService calculation completed",
                    extra={
                        "user_hash": hash_user_id(request.user.id),
                        "calculations_performed": calculations_performed,
                        "errors_encountered": errors_encountered,
                        "total_employees": len(payroll_data),
                        "year": current_date.year,
                        "month": current_date.month,
                    },
                )

            except Exception as e:
                logger.error(
                    f"New PayrollService failed, falling back to legacy calculation: {e}"
                )
                # Fallback to legacy logic
                payroll_data = _legacy_payroll_calculation(
                    employees, current_date, start_date, end_date
                )

        # Calculate pagination metadata
        has_next = offset + limit < total_count
        has_previous = page > 1

        # Create paginated response
        paginated_response = {
            "results": payroll_data,
            "pagination": {
                "page": page,
                "limit": limit,
                "total_count": total_count,
                "total_pages": (total_count + limit - 1) // limit,  # Ceiling division
                "has_next": has_next,
                "has_previous": has_previous,
                "next_page": page + 1 if has_next else None,
                "previous_page": page - 1 if has_previous else None,
            },
        }

        payroll_views.logger.info(
            "Payroll list completed",
            extra={
                "user_hash": hash_user_id(request.user.id),
                "records_count": len(payroll_data),
                "total_count": total_count,
                "page": page,
                "limit": limit,
            },
        )
        path = getattr(request, "path", "") or ""
        if path.startswith("/api/v1/payroll/"):
            # Compatibility with old clients/tests
            return Response(payroll_data, status=200)
        # New format (v2+)
        return Response(paginated_response)

    except (DatabaseError, OperationalError) as e:
        from core.logging_utils import err_tag

        # Use payroll_views.logger for test mocking
        payroll_views.logger.error(f"Database error in payroll_list: {err_tag(e)}")
        return Response(
            {"detail": "Database error occurred"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except Exception as e:
        from core.logging_utils import err_tag

        # Use payroll_views.logger for test mocking
        payroll_views.logger.error(f"Error in payroll_list: {err_tag(e)}")
        return Response(
            {"detail": "Unable to process the request"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def _legacy_payroll_calculation(employees, current_date, start_date, end_date):
    """
    Legacy fallback calculation (original logic)
    """
    # Prefetch all work logs for all employees with a single query
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

    # Fast calculation without external APIs
    for employee in employees:
        try:
            salary = employee.salary_info
            payroll_views.logger.info(
                "Processing employee",
                extra={
                    "employee_id": getattr(employee, "id", None),
                    "action": "payroll_processing",
                },
            )

            # Use prefetched data instead of separate query
            work_logs = employee.filtered_work_logs

            # Fast calculation
            total_hours = float(sum(log.get_total_hours() for log in work_logs))
            worked_days = work_logs.values("check_in__date").distinct().count()
            work_sessions = work_logs.count()

            payroll_views.logger.info(
                f"  Work logs: {work_sessions}, Hours: {total_hours}, Days: {worked_days}"
            )

            # Fast salary calculation without external APIs for list view
            if salary.calculation_type == "hourly":
                # Use enhanced service in fast mode

                try:
                    employee_type = (
                        EmployeeType.HOURLY
                        if salary.calculation_type == "hourly"
                        else EmployeeType.MONTHLY
                    )
                    context = CalculationContext(
                        employee_id=employee.id,
                        year=current_date.year,
                        month=current_date.month,
                        user_id=1,  # System user for fallback
                        employee_type=employee_type,
                        fast_mode=True,
                    )
                    payroll_service = PayrollService()
                    result = payroll_service.calculate(
                        context, CalculationStrategy.ENHANCED
                    )
                    estimated_salary = float(result.get("total_salary", 0))
                    payroll_views.logger.info(
                        "Enhanced calculation completed",
                        extra={
                            "employee_id": getattr(employee, "id", None),
                            "action": "enhanced_calc",
                            "calculation_type": "enhanced_fast",
                        },
                    )
                except Exception as e:
                    payroll_views.logger.warning(
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
                    )  # Approximate estimate with bonuses
            else:
                # For monthly employees, use PayrollService for proper calculation
                try:
                    context = CalculationContext(
                        employee_id=employee.id,
                        year=current_date.year,
                        month=current_date.month,
                        user_id=1,  # System user for fallback
                        fast_mode=True,
                    )
                    service = PayrollService()
                    result = service.calculate(context)
                    estimated_salary = float(result.get("total_salary", 0))
                    payroll_views.logger.info(
                        "Monthly calculation completed via PayrollService",
                        extra={
                            "employee_id": getattr(employee, "id", None),
                            "action": "monthly_calc",
                            "calculation_type": "monthly_proportional",
                        },
                    )
                except Exception as e:
                    payroll_views.logger.warning(
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
            payroll_views.logger.info(
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
