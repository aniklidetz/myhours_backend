"""
Real data service for AI Assistant.

This module fetches actual salary data from the database
for AI explanations.
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Optional

from django.db.models import Sum

from payroll.models import DailyPayrollCalculation, Salary
from users.models import Employee
from worktime.models import WorkLog

logger = logging.getLogger(__name__)


def get_real_salary_data(employee_id: int, period: str) -> Dict[str, Any]:
    """
    Get real salary data from database for AI explanation.

    Args:
        employee_id: ID of the employee
        period: Period string (e.g., "October 2025")

    Returns:
        Dictionary with salary breakdown from actual database
    """
    try:
        # Parse period
        year, month, day = _parse_period(period)

        # Get employee
        employee = Employee.objects.select_related("user").get(id=employee_id)

        # Get active salary configuration
        salary_config = Salary.objects.filter(employee=employee, is_active=True).first()

        # Get daily calculations for the period
        if day:
            # Specific day
            daily_calcs = DailyPayrollCalculation.objects.filter(
                employee=employee,
                work_date=date(year, month, day),
            ).order_by("work_date")
        else:
            # Full month
            daily_calcs = DailyPayrollCalculation.objects.filter(
                employee=employee,
                work_date__year=year,
                work_date__month=month,
            ).order_by("work_date")

        # Get work logs for the period
        work_logs = WorkLog.objects.filter(
            employee=employee,
            check_in__year=year,
            check_in__month=month,
        )

        # Aggregate data (using actual field names from DailyPayrollCalculation)
        aggregated = daily_calcs.aggregate(
            total_regular=Sum("regular_hours"),
            total_ot_125=Sum("overtime_hours_1"),  # First 2 hours OT (125%)
            total_ot_150=Sum("overtime_hours_2"),  # Beyond 2 hours OT (150%)
            total_shabbat=Sum("sabbath_regular_hours"),  # Shabbat hours
            total_night=Sum("night_hours"),
            total_base_pay=Sum("base_pay"),
            total_bonus_pay=Sum("bonus_pay"),
            total_gross=Sum("total_gross_pay"),
        )

        # Build response
        base_rate = Decimal("0")
        monthly_salary = Decimal("0")
        calculation_type = "hourly"

        if salary_config:
            calculation_type = salary_config.calculation_type
            if calculation_type == "hourly":
                base_rate = salary_config.hourly_rate or Decimal("0")
            else:
                # Monthly employee - calculate effective hourly rate
                monthly_salary = salary_config.base_salary or Decimal("0")
                # Standard work month in Israel: 182 hours
                base_rate = (
                    monthly_salary / Decimal("182") if monthly_salary else Decimal("0")
                )

        # Get Shabbat work details
        shabbat_details = _get_shabbat_details(daily_calcs)

        # Get overtime details
        overtime_details = _get_overtime_details(daily_calcs, base_rate)

        return {
            "employee_info": {
                "id": employee.id,
                "name": f"{employee.first_name} {employee.last_name}",
                "employment_type": employee.employment_type,
                "calculation_type": calculation_type,
            },
            "period": period,
            "summary": {
                "total_hours_worked": _sum_hours(aggregated),
                "regular_hours": aggregated.get("total_regular") or Decimal("0"),
                "overtime_125_hours": aggregated.get("total_ot_125") or Decimal("0"),
                "overtime_150_hours": aggregated.get("total_ot_150") or Decimal("0"),
                "shabbat_hours": aggregated.get("total_shabbat") or Decimal("0"),
                "night_hours": aggregated.get("total_night") or Decimal("0"),
            },
            "rates": {
                "calculation_type": calculation_type,
                "monthly_salary": (
                    monthly_salary if calculation_type == "monthly" else Decimal("0")
                ),
                "base_hourly_rate": base_rate,
                "overtime_125_rate": base_rate * Decimal("1.25"),
                "overtime_150_rate": base_rate * Decimal("1.50"),
                "shabbat_rate": base_rate * Decimal("1.50"),
                "holiday_rate": base_rate * Decimal("1.50"),
            },
            "earnings": {
                "base_pay": aggregated.get("total_base_pay") or Decimal("0"),
                "bonus_pay": aggregated.get("total_bonus_pay") or Decimal("0"),
                "total_gross": aggregated.get("total_gross") or Decimal("0"),
            },
            "work_days": {
                "total_work_days": _get_work_days_in_month(year, month),
                "actual_worked_days": daily_calcs.count(),
            },
            "components_detail": {
                "shabbat_work": shabbat_details,
                "overtime": overtime_details,
            },
            "daily_breakdown": _get_daily_breakdown(daily_calcs),
            "legal_references": [
                {
                    "law": "Hours of Work and Rest Law, 5711-1951",
                    "section": "Section 16",
                    "description": "Overtime pay: 125% for first 2 hours, 150% beyond",
                },
                {
                    "law": "Hours of Work and Rest Law, 5711-1951",
                    "section": "Section 17",
                    "description": "Shabbat and holiday work: 150% premium",
                },
            ],
        }

    except Employee.DoesNotExist:
        logger.error(f"Employee {employee_id} not found")
        return _get_error_response(employee_id, period, "Employee not found")

    except Exception as e:
        logger.error(f"Error fetching salary data: {e}", exc_info=True)
        return _get_error_response(employee_id, period, str(e))


def _parse_period(period: str) -> tuple[int, int, Optional[int]]:
    """
    Parse period string to year, month, and optional day.

    Returns:
        tuple: (year, month, day) where day is None for month-only periods
    """
    import calendar

    # Try to parse "2025-11-15" format (specific day)
    if "-" in period and len(period) == 10:
        try:
            parts = period.split("-")
            if len(parts) == 3:
                year = int(parts[0])
                month = int(parts[1])
                day = int(parts[2])
                return year, month, day
        except (ValueError, IndexError):
            pass

    # Try to parse "October 2025" format (month)
    parts = period.split()
    if len(parts) == 2:
        month_name, year_str = parts
        try:
            month_names = {
                name: num for num, name in enumerate(calendar.month_name) if num
            }
            month = month_names.get(month_name, 1)
            year = int(year_str)
            return year, month, None
        except (ValueError, KeyError):
            pass

    # Default to current month
    today = date.today()
    return today.year, today.month, None


def _sum_hours(aggregated: dict) -> Decimal:
    """Sum all hour types."""
    total = Decimal("0")
    for key in ["total_regular", "total_ot_125", "total_ot_150", "total_shabbat"]:
        if aggregated.get(key):
            total += aggregated[key]
    return total


def _get_work_days_in_month(year: int, month: int) -> int:
    """Get number of work days (excluding weekends) in a month."""
    import calendar

    cal = calendar.Calendar()
    work_days = 0
    for day in cal.itermonthdays2(year, month):
        if day[0] != 0 and day[1] < 5:  # Not weekend (Mon-Fri)
            work_days += 1
    return work_days


def _get_shabbat_details(daily_calcs) -> Dict[str, Any]:
    """Get Shabbat work details."""
    shabbat_days = daily_calcs.filter(sabbath_regular_hours__gt=0)

    if not shabbat_days.exists():
        return {"worked": False, "message": "No Shabbat work in this period"}

    total_hours = sum(d.sabbath_regular_hours or 0 for d in shabbat_days)
    total_pay = sum(d.bonus_pay or 0 for d in shabbat_days)

    dates = [d.work_date.strftime("%Y-%m-%d") for d in shabbat_days]

    return {
        "worked": True,
        "dates": dates,
        "total_hours": float(total_hours),
        "total_pay": float(total_pay),
        "multiplier": "x1.50",
        "reason": "Standard Shabbat premium per Israeli labor law",
    }


def _get_overtime_details(daily_calcs, base_rate: Decimal) -> Dict[str, Any]:
    """Get overtime work details."""
    ot_125_total = sum(d.overtime_hours_1 or 0 for d in daily_calcs)
    ot_150_total = sum(d.overtime_hours_2 or 0 for d in daily_calcs)

    return {
        "first_2_hours": {
            "hours": float(ot_125_total),
            "multiplier": "x1.25",
            "rate": float(base_rate * Decimal("1.25")),
        },
        "beyond_2_hours": {
            "hours": float(ot_150_total),
            "multiplier": "x1.50",
            "rate": float(base_rate * Decimal("1.50")),
        },
    }


def _get_daily_breakdown(daily_calcs) -> list:
    """Get daily breakdown for detailed view."""
    breakdown = []
    for calc in daily_calcs[:10]:  # Limit to 10 days for API response size
        breakdown.append(
            {
                "date": calc.work_date.strftime("%Y-%m-%d"),
                "regular_hours": float(calc.regular_hours or 0),
                "overtime_125": float(calc.overtime_hours_1 or 0),
                "overtime_150": float(calc.overtime_hours_2 or 0),
                "shabbat_hours": float(calc.sabbath_regular_hours or 0),
                "is_holiday": calc.is_holiday,
                "is_sabbath": calc.is_sabbath,
                "base_pay": float(calc.base_pay or 0),
                "bonus_pay": float(calc.bonus_pay or 0),
                "total": float(calc.total_gross_pay or 0),
            }
        )
    return breakdown


def _get_error_response(employee_id: int, period: str, error: str) -> Dict[str, Any]:
    """Return error response structure."""
    return {
        "employee_info": {
            "id": employee_id,
            "name": "Unknown",
            "error": error,
        },
        "period": period,
        "summary": {},
        "earnings": {},
        "error": error,
    }
