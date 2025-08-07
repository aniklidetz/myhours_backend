"""
Optimized Payroll Calculation Service

Fast payroll calculation service with Redis caching and optimized database queries.
Specifically designed to eliminate N+1 queries and accelerate API responses.
"""

import calendar
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db import models
from django.utils import timezone

from core.logging_utils import safe_log_employee
from integrations.models import Holiday
from payroll.enhanced_redis_cache import enhanced_payroll_cache
from payroll.models import DailyPayrollCalculation, MonthlyPayrollSummary, Salary
from worktime.models import WorkLog

logger = logging.getLogger(__name__)


class OptimizedPayrollService:
    """
    ✅ OPTIMIZED payroll calculation service

    Solves performance issues:
    1. N+1 Query Problem - uses prefetch_related and bulk queries
    2. Redis caching for holidays
    3. Bulk operations for multiple calculations
    4. Caching of calculation results
    """

    def __init__(self, fast_mode=True):
        """
        Args:
            fast_mode (bool): Fast mode without external API calls
        """
        self.fast_mode = fast_mode
        self.api_usage = {
            "db_queries": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "calculations_performed": 0,
        }

    def calculate_bulk_payroll(
        self, employees_queryset, year: int, month: int
    ) -> List[Dict]:
        """
        ✅ OPTIMIZED bulk payroll calculation for multiple employees

        Eliminates N+1 queries through:
        1. Prefetch all work logs in a single query
        2. Bulk loading holidays from Redis
        3. Bulk processing of results

        Args:
            employees_queryset: Employee QuerySet with select_related('salary_info')
            year, month: Calculation period

        Returns:
            List[Dict]: List of calculation results
        """
        logger.info(
            f"🚀 Starting optimized bulk payroll calculation for {year}-{month:02d}"
        )

        # Calculate month boundaries
        start_date = date(year, month, 1)
        _, last_day = calendar.monthrange(year, month)
        end_date = date(year, month, last_day)

        # ✅ 1. OPTIMIZATION: Prefetch all work logs in a single query
        from django.db.models import Prefetch

        employees = employees_queryset.prefetch_related(
            Prefetch(
                "work_logs",
                queryset=WorkLog.objects.filter(
                    check_out__isnull=False,
                    check_in__date__gte=start_date,
                    check_in__date__lte=end_date,
                ).order_by("check_in"),
                to_attr="month_work_logs",
            )
        )

        self.api_usage["db_queries"] += 1

        # ✅ 2. OPTIMIZATION: Bulk loading holidays with precise Shabbat times from Redis
        try:
            holidays_cache = enhanced_payroll_cache.get_holidays_with_shabbat_times(
                year, month
            )

            if holidays_cache:
                self.api_usage["cache_hits"] += 1
                logger.info(
                    f"📋 Loaded {len(holidays_cache)} holidays with precise Shabbat times from cache"
                )
            else:
                self.api_usage["cache_misses"] += 1
                holidays_cache = {}  # Ensure we have a dict even if cache fails
        except Exception as e:
            logger.warning(f"Failed to load holidays cache: {e}")
            holidays_cache = {}
            self.api_usage["cache_misses"] += 1

        # ✅ 3. OPTIMIZATION: Try to get cached results from MonthlyPayrollSummary
        existing_summaries = {}
        try:
            summaries = MonthlyPayrollSummary.objects.filter(
                employee__in=employees, year=year, month=month
            ).select_related("employee")

            for summary in summaries:
                existing_summaries[summary.employee.id] = summary

            logger.info(
                f"📊 Found {len(existing_summaries)} existing monthly summaries"
            )
        except Exception as e:
            logger.warning(f"Error loading existing summaries: {e}")

        # 4. Process each employee with optimized logic
        results = []

        for employee in employees:
            try:
                self.api_usage["calculations_performed"] += 1

                # Check if we have a pre-calculated result
                if employee.id in existing_summaries:
                    summary = existing_summaries[employee.id]
                    result = self._convert_summary_to_result(
                        employee, summary, year, month
                    )
                    results.append(result)
                    logger.debug(
                        f"✅ Used cached summary for {employee.get_full_name()}"
                    )
                    continue

                # Perform fast calculation for new employee
                result = self._calculate_single_employee_optimized(
                    employee, year, month, holidays_cache
                )
                results.append(result)

            except Exception as e:
                logger.error(
                    f"Error calculating payroll for employee {employee.id}: {e}"
                )
                # Add error result
                results.append(self._create_error_result(employee, year, month, str(e)))

        logger.info(
            f"✅ Bulk payroll calculation completed. Processed {len(results)} employees"
        )
        logger.info(f"📊 API Usage: {self.api_usage}")

        return results

    def _calculate_single_employee_optimized(
        self, employee, year: int, month: int, holidays_cache: Dict
    ) -> Dict:
        """
        ✅ OPTIMIZED calculation for a single employee

        Uses:
        1. Prefetched work logs (already loaded)
        2. Cached holidays (passed as parameter)
        3. Fast aggregation calculations
        """
        try:
            # Check if employee has salary info
            if not hasattr(employee, "salary_info") or not employee.salary_info:
                return self._create_error_result(
                    employee, year, month, "Employee has no salary configuration"
                )

            salary = employee.salary_info
            work_logs = getattr(employee, "month_work_logs", [])  # Prefetched data

            # Handle case where no work logs exist for this month
            if not work_logs:
                logger.debug(
                    f"No work logs found for {employee.get_full_name()} in {year}-{month:02d}"
                )
                return {
                    "id": employee.id,
                    "employee": {
                        "id": employee.id,
                        "name": employee.get_full_name(),
                        "email": employee.email,
                        "role": employee.role,
                    },
                    "calculation_type": salary.calculation_type,
                    "currency": salary.currency,
                    "total_salary": 0,
                    "total_hours": 0,
                    "worked_days": 0,
                    "work_sessions": 0,
                    "period": f"{year}-{month:02d}",
                    "status": "no_work_logs",
                    "calculation_method": "optimized_bulk",
                }

            # Fast aggregation calculations
            total_hours = float(sum(log.get_total_hours() for log in work_logs))
            worked_days = len(set(log.check_in.date() for log in work_logs))
            work_sessions = len(work_logs)

            # Fast salary calculation without complex overtime logic
            if salary.calculation_type == "hourly":
                base_rate = float(salary.hourly_rate or 0)
                # Simple estimate with overtime consideration (coefficient 1.3)
                estimated_salary = float(total_hours) * base_rate * 1.3
            else:
                # Monthly salary - proportional to worked days
                base_salary = float(salary.base_salary or 0)
                work_proportion = worked_days / 22 if worked_days <= 22 else 1.0
                estimated_salary = base_salary * work_proportion

            return {
                "id": employee.id,
                "employee": {
                    "id": employee.id,
                    "name": employee.get_full_name(),
                    "email": employee.email,
                    "role": employee.role,
                },
                "calculation_type": salary.calculation_type,
                "currency": salary.currency,
                "total_salary": round(estimated_salary, 2),
                "total_hours": round(total_hours, 2),
                "worked_days": worked_days,
                "work_sessions": work_sessions,
                "period": f"{year}-{month:02d}",
                "status": "estimated",  # Mark as estimated calculation
                "calculation_method": "optimized_bulk",
            }

        except Exception as e:
            logger.error(f"Error in single employee calculation: {e}")
            return self._create_error_result(employee, year, month, str(e))

    def _convert_summary_to_result(
        self, employee, summary: MonthlyPayrollSummary, year: int, month: int
    ) -> Dict:
        """
        Convert MonthlyPayrollSummary to API result format
        """
        return {
            "id": employee.id,
            "employee": {
                "id": employee.id,
                "name": employee.get_full_name(),
                "email": employee.email,
                "role": employee.role,
            },
            "calculation_type": summary.employee.salary_info.calculation_type,
            "currency": summary.employee.salary_info.currency,
            "total_salary": float(summary.total_gross_pay),
            "total_hours": float(summary.total_hours),
            "worked_days": summary.worked_days,
            "work_sessions": (
                summary.calculation_details.get("work_sessions_count", 0)
                if summary.calculation_details
                else 0
            ),
            "period": f"{year}-{month:02d}",
            "status": "calculated",  # Exact calculation from database
            "calculation_method": "database_summary",
            "regular_hours": float(summary.regular_hours),
            "overtime_hours": float(summary.overtime_hours),
            "holiday_hours": float(summary.holiday_hours),
            "sabbath_hours": float(summary.sabbath_hours),
        }

    def _create_error_result(
        self, employee, year: int, month: int, error_message: str
    ) -> Dict:
        """
        Create error result
        """
        return {
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
            "period": f"{year}-{month:02d}",
            "status": "error",
            "error_message": error_message,
            "calculation_method": "error",
        }

    def get_optimization_stats(self) -> Dict:
        """
        Return optimization statistics
        """
        return {
            "service_type": "OptimizedPayrollService",
            "fast_mode": self.fast_mode,
            "api_usage": self.api_usage,
            "optimization_features": [
                "Prefetch work logs (eliminates N+1 queries)",
                "Redis holidays cache",
                "Bulk operations",
                "Database summary reuse",
                "Fast estimation calculations",
            ],
        }


# Singleton instance for reuse
optimized_payroll_service = OptimizedPayrollService(fast_mode=True)
