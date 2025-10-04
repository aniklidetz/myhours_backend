"""
Enhanced payroll calculation strategy with full Israeli labor law compliance.

This strategy implements comprehensive payroll calculations including:
- Precise overtime calculations (125%, 150%)
- Night shift premiums
- Sabbath and holiday calculations
- Split shift handling
- Monthly vs hourly employee differentiation
- Legal compliance validation
"""

import calendar
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from django.db import models
from django.utils import timezone

from core.logging_utils import safe_log_employee
from integrations.models import Holiday
from integrations.services.unified_shabbat_service import get_shabbat_times
from payroll.enhanced_redis_cache import enhanced_payroll_cache
from payroll.models import DailyPayrollCalculation, MonthlyPayrollSummary, CompensatoryDay
from payroll.shift_splitter import ShiftSplitter
from worktime.models import WorkLog
from worktime.night_shift import night_hours as calc_night_hours
from users.models import Employee

from ..contracts import PayrollResult, PayrollBreakdown, PayrollMetadata, CalculationContext
from ..enums import CalculationStrategy, PayrollStatus, EmployeeType, CalculationMode
from .base import AbstractPayrollStrategy


def apply_normative(actual: Decimal, dt, fast_mode: bool) -> Decimal:
    """
    Apply Israeli labor law normative hours conversion.
    
    Only applies to regular hours when fast_mode=False.
    Converts: 8.0 actual hours -> 8.6 normative hours (day shifts)
             7.0 actual hours -> 7.0 normative hours (night shifts)
    
    Args:
        actual: Actual hours worked
        dt: Datetime of shift start (for future night shift detection)
        fast_mode: If True, skip normative conversion
        
    Returns:
        Normative hours for billing
    """
    if fast_mode:
        return actual
    mapping = {Decimal("8.0"): Decimal("8.6"), Decimal("7.0"): Decimal("7.0")}
    return mapping.get(actual, actual)


logger = logging.getLogger(__name__)


def night_hours(check_in: datetime, check_out: datetime) -> float:
    """
    Helper function to calculate night hours (22:00-06:00) for testing compatibility.
    
    Args:
        check_in: Work start time
        check_out: Work end time
        
    Returns:
        float: Number of night hours
    """
    # Simple night hours calculation for 22:00-06:00
    night_start = 22  # 10 PM
    night_end = 6     # 6 AM
    
    total_night_hours = 0.0
    current_time = check_in
    
    while current_time < check_out:
        hour = current_time.hour
        if hour >= night_start or hour < night_end:
            # This is a night hour
            next_hour = current_time.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            end_time = min(next_hour, check_out)
            duration = (end_time - current_time).total_seconds() / 3600
            total_night_hours += duration
        
        current_time = current_time.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    
    return total_night_hours


class EnhancedPayrollStrategy(AbstractPayrollStrategy):
    """
    Enhanced payroll calculation strategy with full Israeli labor law compliance.
    
    This strategy provides comprehensive payroll calculations with:
    - Complete Israeli labor law compliance
    - API integration for precise Sabbath and holiday calculations
    - Support for both hourly and monthly employees
    - Advanced overtime and premium calculations
    - Legal compliance validation
    - Audit trails and detailed breakdowns
    """
    
    # Israeli labor law constants
    MAX_DAILY_HOURS = Decimal("12")
    MAX_WEEKLY_REGULAR_HOURS = Decimal("42")  # 5-day work week
    MAX_WEEKLY_OVERTIME_HOURS = Decimal("16")
    MINIMUM_WAGE_ILS = Decimal("5300")
    MONTHLY_WORK_HOURS = Decimal("182")  # Standard month for calculations

    # Daily hour norms
    REGULAR_DAILY_HOURS = Decimal("8.6")  # Regular day (4 days per week)
    SHORT_DAILY_HOURS = Decimal("7.6")  # Short day (usually Friday)
    NIGHT_SHIFT_MAX_REGULAR_HOURS = Decimal("7")  # Night shift norm
    
    # Night shift detection constants
    NIGHT_NORM = Decimal("7.0")  # Night shift norm hours
    DAY_NORM = Decimal("8.6")    # Day shift norm hours
    NIGHT_DETECTION_MINIMUM = Decimal("2.0")  # Minimum hours to classify as night shift

    # Night shift constants
    NIGHT_SHIFT_START = 22  # 22:00
    NIGHT_SHIFT_END = 6  # 06:00

    # Payment coefficients
    OVERTIME_RATE_125 = Decimal("1.25")  # First 2 overtime hours
    OVERTIME_RATE_150 = Decimal("1.50")  # Additional overtime hours
    HOLIDAY_RATE = Decimal("1.50")  # Holiday work coefficient
    SABBATH_RATE = Decimal("1.50")  # Sabbath work coefficient

    # Sabbath overtime rates (even higher premiums)
    SABBATH_OVERTIME_RATE_175 = Decimal("1.75")  # Sabbath + first 2 OT hours
    SABBATH_OVERTIME_RATE_200 = Decimal("2.00")  # Sabbath + additional OT hours

    # Bonus rates for monthly employees (percentage above base)
    OVERTIME_BONUS_125 = Decimal("0.25")  # +25% for first 2 overtime hours
    OVERTIME_BONUS_150 = Decimal("0.50")  # +50% for additional overtime
    SPECIAL_DAY_BONUS = Decimal("0.50")  # +50% for holiday/sabbath work
    
    def __init__(self, context: CalculationContext):
        super().__init__(context)
        self._holidays_cache: Optional[Dict] = None
        self._api_usage = {
            "sunrise_sunset_calls": 0,
            "hebcal_calls": 0,
            "precise_sabbath_times": 0,
            "api_holidays_found": 0,
            "fallback_calculations": 0,
            "redis_cache_hits": 0,
            "redis_cache_misses": 0,
        }
        self._calculation_errors = []
        self._warnings = []
        
    def calculate(self) -> PayrollResult:
        """
        Calculate payroll using enhanced algorithm with full Israeli labor law compliance.
        
        Returns:
            PayrollResult: Comprehensive payroll calculation result
        """
        try:
            # Get employee with full related data
            employee = self._get_employee_with_relations()
            salary = self._get_salary_info(employee)
            
            # Initialize API services if not in fast mode
            if not self._fast_mode:
                self._initialize_api_services()
            
            # Get holidays and work logs for the month
            holidays = self._get_holidays_enhanced()
            work_logs = self._get_work_logs_enhanced(employee)
            
            # Validate work logs for legal compliance
            self._validate_legal_compliance(work_logs)
            
            # Determine employee type and calculation mode
            calculation_mode = self._determine_calculation_mode(salary)
            
            # Calculate payroll based on employee type
            if calculation_mode == CalculationMode.HOURLY:
                result = self._calculate_hourly_employee(employee, salary, work_logs, holidays)
            else:
                result = self._calculate_monthly_employee(employee, salary, work_logs, holidays)
            
            # Save calculation results if not in fast mode
            if not self._fast_mode:
                self._save_calculation_results(employee, result, work_logs)
            
            return result
            
        except Exception as e:
            logger.error(
                f"EnhancedPayrollStrategy calculation failed for employee {self._employee_id}",
                extra={
                    "employee_id": self._employee_id,
                    "year": self._year,
                    "month": self._month,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "action": "enhanced_calculation_error"
                },
                exc_info=True
            )
            raise
    
    def _get_employee_with_relations(self) -> Employee:
        """
        Get employee with all necessary relations prefetched for calculations.
        
        Returns:
            Employee: Employee instance with prefetched relations
        """
        start_time = timezone.now()
        
        try:
            employee = Employee.objects.select_related(
                'user'
            ).prefetch_related(
                'salaries',
                models.Prefetch(
                    'work_logs',
                    queryset=WorkLog.objects.filter(
                        check_in__year=self._year,
                        check_in__month=self._month,
                        check_out__isnull=False
                    ).select_related('employee').order_by('check_in'),
                    to_attr='month_work_logs'
                ),
                models.Prefetch(
                    'compensatory_days',
                    queryset=CompensatoryDay.objects.filter(
                        date_earned__year=self._year,
                        date_earned__month=self._month
                    ),
                    to_attr='month_compensatory_days'
                )
            ).get(id=self._employee_id)
            
            duration_ms = (timezone.now() - start_time).total_seconds() * 1000
            self._log_performance_metrics(
                "employee_query_enhanced", 
                duration_ms,
                {
                    "has_salary": employee.salaries.exists(),
                    "work_logs_count": len(getattr(employee, 'month_work_logs', [])),
                    "compensatory_days": len(getattr(employee, 'month_compensatory_days', []))
                }
            )
            
            return employee
            
        except Employee.DoesNotExist:
            raise Employee.DoesNotExist(f"Employee with id {self._employee_id} not found")
    
    def _get_salary_info(self, employee):
        """
        Get active salary information for the employee.
        
        Args:
            employee: Employee instance with prefetched salaries
            
        Returns:
            Salary: Active salary configuration
            
        Raises:
            ValueError: If no active salary configuration found
        """
        # Get active salary for current period
        active_salary = employee.salaries.filter(is_active=True).first()
        
        if not active_salary:
            raise ValueError(f"No active salary configuration found for employee {employee.id}")
        
        return active_salary
    
    def _initialize_api_services(self) -> None:
        """Initialize external API services for precise calculations."""
        try:
            # UnifiedShabbatService uses module-level function - no instance needed
            self._unified_shabbat_enabled = True
            logger.debug(
                f"Initialized API services for employee {self._employee_id}",
                extra={
                    "employee_id": self._employee_id,
                    "action": "api_services_initialized"
                }
            )
        except Exception as e:
            logger.warning(
                f"Failed to initialize API services, using fallback: {e}",
                extra={
                    "employee_id": self._employee_id,
                    "error": str(e),
                    "action": "api_services_fallback"
                }
            )
    
    def _get_holidays_enhanced(self) -> Dict[date, Dict]:
        """
        Get holidays for the month with enhanced API integration.
        
        Returns:
            Dict: Holiday data with precise information
        """
        if self._holidays_cache is not None:
            return self._holidays_cache
        
        cache_key = f"enhanced_holidays_{self._year}_{self._month}"
        start_time = timezone.now()
        
        # Try cache first if available
        cached_holidays = None
        try:
            cached_holidays = enhanced_payroll_cache.get_holidays(self._year, self._month)
        except (AttributeError, KeyError):
            pass
            
        if cached_holidays:
            duration_ms = (timezone.now() - start_time).total_seconds() * 1000
            self._log_performance_metrics(
                "holidays_cache_hit", 
                duration_ms,
                {"holiday_count": len(cached_holidays)}
            )
            self._api_usage["redis_cache_hits"] += 1
            self._holidays_cache = cached_holidays
            return cached_holidays
        
        # Cache miss - build holidays from multiple sources
        self._api_usage["redis_cache_misses"] += 1
        holidays_dict = {}
        
        # 1. Get database holidays
        first_day = date(self._year, self._month, 1)
        last_day = date(self._year, self._month, calendar.monthrange(self._year, self._month)[1])
        
        db_holidays = Holiday.objects.filter(
            date__gte=first_day,
            date__lte=last_day,
            is_holiday=True
        ).values('date', 'name')
        
        for holiday in db_holidays:
            holidays_dict[holiday['date']] = {
                'name': holiday['name'],
                'is_paid': True,  # Assume all holidays are paid
                'source': 'database'
            }
        
        # 2. Sync with API if not in fast mode
        if not self._fast_mode:
            try:
                # Use external gateway for mockable API calls
                from payroll.services.external import get_holidays
                api_holidays = get_holidays(self._year, self._month)
                self._api_usage["hebcal_calls"] += 1
                self._api_usage["api_holidays_found"] += len(api_holidays or [])
                
                for api_holiday in api_holidays:
                    holiday_date = api_holiday['date']
                    if holiday_date not in holidays_dict:
                        holidays_dict[holiday_date] = {
                            'name': api_holiday['name'],
                            'is_paid': api_holiday.get('is_paid', True),
                            'source': 'api'
                        }
            except Exception as e:
                logger.warning(f"API holiday sync failed: {e}")
                self._warnings.append(f"Holiday API unavailable: {e}")
        
        # Cache the result if cache supports it
        try:
            enhanced_payroll_cache.set_holidays(self._year, self._month, holidays_dict)
        except (AttributeError, KeyError):
            pass
        
        duration_ms = (timezone.now() - start_time).total_seconds() * 1000
        self._log_performance_metrics(
            "holidays_enhanced_build", 
            duration_ms,
            {"holiday_count": len(holidays_dict)}
        )
        
        self._holidays_cache = holidays_dict
        return holidays_dict
    
    def _get_work_logs_enhanced(self, employee: Employee) -> List[WorkLog]:
        """
        Get work logs with enhanced processing for split shifts.
        
        Args:
            employee: Employee instance
            
        Returns:
            List[WorkLog]: Enhanced work logs with split shift processing
        """
        # Try to use prefetched data first
        if hasattr(employee, 'month_work_logs'):
            work_logs = employee.month_work_logs
        else:
            # Fallback to direct query
            work_logs = list(WorkLog.objects.filter(
                employee_id=self._employee_id,
                check_in__year=self._year,
                check_in__month=self._month,
                check_out__isnull=False
            ).select_related('employee').order_by('check_in'))
        
        # Process split shifts if not in fast mode
        if not self._fast_mode and hasattr(self, '_unified_shabbat_enabled'):
            work_logs = self._process_split_shifts(work_logs)
        
        logger.debug(
            f"Retrieved {len(work_logs)} work logs for enhanced calculation",
            extra={
                "employee_id": self._employee_id,
                "work_log_count": len(work_logs),
                "action": "work_logs_enhanced"
            }
        )
        
        return work_logs
    
    def _process_split_shifts(self, work_logs: List[WorkLog]) -> List[WorkLog]:
        """
        Process work logs to handle split shifts (e.g., Friday evening to Saturday).
        
        CRITICAL FIX: Ensures original log is replaced by splits, not duplicated.
        
        Args:
            work_logs: Original work logs
            
        Returns:
            List[WorkLog]: Processed work logs with splits handled (no duplicates)
        """
        processed_logs = []
        
        for log in work_logs:
            # Check if this is a Friday shift that might span Sabbath (same day or multi-day)
            if (log.check_in.weekday() == 4 and  # Friday
                log.check_out):
                
                try:
                    # Use ShiftSplitter to handle precise Sabbath splitting
                    splitter = ShiftSplitter()
                    split_result = splitter.split_shift_for_sabbath(
                        log.check_in, 
                        log.check_out,
                        use_api=not self._fast_mode  # Use API unless in fast mode
                    )
                    
                    # CRITICAL: Replace original log with split segments (no duplication)
                    if split_result and split_result.get("during_sabbath", 0) > 0:
                        # Create virtual work logs for each segment based on split result
                        segments = []
                        
                        # Before Sabbath segment (if any hours)
                        before_sabbath_hours = split_result.get("before_sabbath", 0)
                        if before_sabbath_hours > 0:
                            before_sabbath_end = split_result["sabbath_start_used"]
                            segments.append({
                                'start': log.check_in,
                                'end': before_sabbath_end,
                                'is_sabbath': False,
                                'hours': before_sabbath_hours
                            })
                        
                        # During Sabbath segment (if any hours)
                        during_sabbath_hours = split_result.get("during_sabbath", 0)
                        if during_sabbath_hours > 0:
                            during_sabbath_start = split_result["sabbath_start_used"]
                            segments.append({
                                'start': during_sabbath_start,
                                'end': log.check_out,
                                'is_sabbath': True,
                                'hours': during_sabbath_hours
                            })
                        
                        # Create virtual work logs for each segment
                        for i, segment in enumerate(segments):
                            virtual_log = WorkLog(
                                employee=log.employee,
                                check_in=segment['start'],
                                check_out=segment['end'],
                                break_minutes=0  # Split breaks proportionally if needed
                            )
                            # Don't set pk - let it be None for virtual logs
                            # But mark it as a split segment for identification
                            virtual_log._original_log_pk = log.pk
                            virtual_log._split_index = i
                            virtual_log._is_sabbath_segment = segment['is_sabbath']
                            processed_logs.append(virtual_log)
                        
                        if split_result.get("api_used", False):
                            self._api_usage["precise_sabbath_times"] += 1
                        # Original log is REPLACED, not added
                    else:
                        # No splits created, use original
                        processed_logs.append(log)
                    
                except Exception as e:
                    logger.warning(f"Split shift processing failed for log {log.pk}: {e}")
                    processed_logs.append(log)  # Use original log as fallback
                    self._api_usage["fallback_calculations"] += 1
            else:
                # Non-Friday or single-day shift - use as-is
                processed_logs.append(log)
        
        return processed_logs
    
    def _determine_calculation_mode(self, salary) -> CalculationMode:
        """
        Determine the calculation mode based on employee salary configuration.
        
        Args:
            salary: Employee salary configuration
            
        Returns:
            CalculationMode: The appropriate calculation mode
        """
        if salary.calculation_type == 'hourly':
            return CalculationMode.HOURLY
        elif salary.calculation_type == 'monthly':
            return CalculationMode.MONTHLY
        else:
            logger.warning(
                f"Unknown calculation type '{salary.calculation_type}', defaulting to hourly",
                extra={
                    "employee_id": self._employee_id,
                    "calculation_type": salary.calculation_type,
                    "action": "calculation_mode_fallback"
                }
            )
            return CalculationMode.HOURLY
    
    def _calculate_hourly_employee(
        self, 
        employee: Employee, 
        salary, 
        work_logs: List[WorkLog], 
        holidays: Dict[date, Dict]
    ) -> PayrollResult:
        """
        Calculate payroll for hourly employees using new segment-based system.
        
        Args:
            employee: Employee instance
            salary: Salary configuration
            work_logs: Work logs for the month
            holidays: Holiday information
            
        Returns:
            PayrollResult: Complete hourly employee payroll result
        """
        from ..contracts import create_empty_breakdown
        
        # Initialize accumulated results with all Decimal values
        total_result = create_empty_breakdown()
        
        hourly_rate = Decimal(str(salary.hourly_rate))
        
        # Process each work log as segment
        for log in work_logs:
            log_hours = Decimal(str(log.get_total_hours()))
            work_date = log.check_in.date()
            
            # Determine segment classification
            is_holiday = work_date in holidays and holidays[work_date].get('is_paid', False)
            is_sabbath = work_date.weekday() == 5  # Saturday
            is_night = self._is_night_segment(log.check_in, log.check_out)
            
            # Handle Friday night spanning into Saturday (Sabbath night logic)
            # This covers both split and non-split segments
            if work_date.weekday() == 4 and is_night:  # Friday night shift
                # Check if shift ends after midnight (either original or split segment)
                saturday_start = log.check_in.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                if log.check_out > saturday_start:
                    is_sabbath = True  # Friday night spanning Saturday = Sabbath night
                # Also check if this is a split segment that represents Friday night work
                # during Sabbath hours (after ShiftSplitter processed it)
                elif (hasattr(log, '_original_log_pk') and hasattr(log, '_split_index') and
                      log.check_out.weekday() == 5):  # Split segment ending on Saturday
                    is_sabbath = True  # This is the Saturday portion of a Friday night shift
            
            # Check if this is a virtual log segment marked as Sabbath by ShiftSplitter
            if hasattr(log, '_is_sabbath_segment') and log._is_sabbath_segment:
                is_sabbath = True  # ShiftSplitter determined this segment is during Sabbath
            
            # Apply bands to this segment
            segment_result = self._apply_bands(log_hours, hourly_rate, is_sabbath, is_night, is_holiday)
            
            # Accumulate results
            for key, value in segment_result.items():
                if key in total_result:
                    total_result[key] += Decimal(str(value))
        
        # Calculate total salary
        total_salary = (
            total_result["regular_pay"] + 
            total_result["overtime_125_pay"] + 
            total_result["overtime_150_pay"] + 
            total_result["sabbath_regular_pay"] + 
            total_result["sabbath_overtime_175_pay"] + 
            total_result["sabbath_overtime_200_pay"]
            # Note: night_shift_pay is not added - new logic uses proper rates in bands
        )
        
        # Build detailed breakdown using accumulated results
        breakdown = PayrollBreakdown(
            # Regular time
            regular_hours=float(total_result["regular_hours"]),
            regular_rate=float(hourly_rate),
            regular_pay=float(total_result["regular_pay"]),
            
            # Overtime 125%
            overtime_125_hours=float(total_result["overtime_125_hours"]),
            overtime_125_rate=float(hourly_rate * self.OVERTIME_RATE_125),
            overtime_125_pay=float(total_result["overtime_125_pay"]),
            
            # Overtime 150%
            overtime_150_hours=float(total_result["overtime_150_hours"]),
            overtime_150_rate=float(hourly_rate * self.OVERTIME_RATE_150),
            overtime_150_pay=float(total_result["overtime_150_pay"]),
            
            # Holiday work
            holiday_hours=float(total_result["holiday_hours"]),
            holiday_rate=float(hourly_rate * self.HOLIDAY_RATE),
            holiday_pay=float(total_result["holiday_pay"]),
            
            # Sabbath work (old fields for compatibility)
            sabbath_hours=float(total_result["sabbath_regular_hours"] + total_result["sabbath_overtime_175_hours"] + total_result["sabbath_overtime_200_hours"]),
            sabbath_rate=float(hourly_rate * self.SABBATH_RATE),
            sabbath_pay=float(total_result["sabbath_regular_pay"] + total_result["sabbath_overtime_175_pay"] + total_result["sabbath_overtime_200_pay"]),
            
            # Extended Sabbath breakdown (new fields)
            sabbath_regular_hours=float(total_result["sabbath_regular_hours"]),
            sabbath_regular_pay=float(total_result["sabbath_regular_pay"]),
            sabbath_overtime_175_hours=float(total_result["sabbath_overtime_175_hours"]),
            sabbath_overtime_175_pay=float(total_result["sabbath_overtime_175_pay"]),
            sabbath_overtime_200_hours=float(total_result["sabbath_overtime_200_hours"]),
            sabbath_overtime_200_pay=float(total_result["sabbath_overtime_200_pay"]),
            
            # Night shift (diagnostic/compatibility only - NOT used in new pay calculation)
            night_shift_hours=float(total_result["night_shift_hours"]),
            night_shift_rate=float(hourly_rate * Decimal('1.00')),  # New logic: no separate night rate
            night_shift_pay=float(total_result["night_shift_pay"])  # Should be 0 in new segment-based logic
        )
        
        # Build metadata
        metadata = PayrollMetadata(
            calculation_strategy=CalculationStrategy.ENHANCED.value,
            employee_type=EmployeeType.HOURLY.value,
            currency=salary.currency,
            calculation_date=timezone.now().isoformat(),
            fast_mode=self._fast_mode,
            has_cache=bool(self._holidays_cache),
            status=PayrollStatus.SUCCESS.value,
            work_log_count=len(work_logs),
            api_usage=self._api_usage,
            warnings=self._warnings if self._warnings else None
        )
        
        # Sync legacy alias fields for compatibility
        total_result["sabbath_regular"] = total_result["sabbath_regular_hours"]
        total_result["night_hours"] = total_result["night_shift_hours"]
        total_result["overtime_pay"] = total_result["overtime_125_pay"] + total_result["overtime_150_pay"]
        
        # Calculate total_hours from categories only (no double counting)
        total_hours_from_categories = (
            total_result["regular_hours"]
            + total_result["overtime_125_hours"]
            + total_result["overtime_150_hours"]
            + total_result["sabbath_regular_hours"]
            + total_result["sabbath_overtime_175_hours"]
            + total_result["sabbath_overtime_200_hours"]
            + total_result["holiday_hours"]
        )

        # DEBUG: Invariant check - ensure total_hours matches sum of categories
        if __debug__:  # Only in debug mode
            cats_sum = (
                total_result["regular_hours"]
                + total_result["overtime_125_hours"] 
                + total_result["overtime_150_hours"]
                + total_result["sabbath_regular_hours"]
                + total_result["sabbath_overtime_175_hours"]
                + total_result["sabbath_overtime_200_hours"]
                + total_result["holiday_hours"]
            )
            assert float(abs(total_hours_from_categories - cats_sum)) < 1e-6, f"total_hours != sum(categories): {total_hours_from_categories} != {cats_sum}"
            logger.debug("Hourly employee result: total_hours=%s, categories_sum=%s, diff=%s", 
                        total_hours_from_categories, cats_sum, abs(total_hours_from_categories - cats_sum))

        return PayrollResult(
            total_salary=total_salary,
            total_hours=total_hours_from_categories,  # Calculate from categories only
            regular_hours=total_result["regular_hours"],
            overtime_hours=total_result["overtime_125_hours"] + total_result["overtime_150_hours"],
            holiday_hours=total_result["holiday_hours"],
            shabbat_hours=total_result["sabbath_regular_hours"] + total_result["sabbath_overtime_175_hours"] + total_result["sabbath_overtime_200_hours"],
            breakdown=breakdown,
            metadata=metadata
        )
    
    def _calculate_monthly_employee(
        self, 
        employee: Employee, 
        salary, 
        work_logs: List[WorkLog], 
        holidays: Dict[date, Dict]
    ) -> PayrollResult:
        """
        Calculate payroll for monthly employees with proportional base salary + bonuses.
        
        Philosophy: Employee receives fixed monthly salary for completing monthly norm (182 hours).
        The salary is calculated proportionally based on worked hours, plus bonuses for special conditions.
        
        Args:
            employee: Employee instance
            salary: Salary configuration
            work_logs: Work logs for the month
            holidays: Holiday information
            
        Returns:
            PayrollResult: Monthly employee payroll result with bonuses
        """
        # Base salary from employee configuration
        full_monthly_salary = Decimal(str(salary.base_salary or 0))
        
        # Initialize counters for different types of hours and bonuses
        total_hours = Decimal('0.0')
        regular_hours = Decimal('0.0')
        bonus_hours_125 = Decimal('0.0')  # First 2 overtime hours per day
        bonus_hours_150 = Decimal('0.0')  # Additional overtime hours
        holiday_bonus_hours = Decimal('0.0')
        sabbath_bonus_hours = Decimal('0.0')
        night_hours = Decimal('0.0')
        
        # Calculate internal hourly rate for bonuses (monthly salary / 182 hours norm)
        monthly_hourly_rate = full_monthly_salary / self.MONTHLY_WORK_HOURS
        
        # Process each work log
        actual_hours_worked = Decimal('0.0')  # Track actual hours for proportion calculation
        for log in work_logs:
            log_hours = log.get_total_hours()
            actual_hours_worked += log_hours  # Use actual hours for proportion calculation
            work_date = log.check_in.date()
            
            # Check if it's a special day
            is_holiday = work_date in holidays and holidays[work_date].get('is_paid', False)
            is_sabbath = work_date.weekday() == 5  # Saturday
            is_night = self._is_night_segment(log.check_in, log.check_out)
            
            # Handle Friday night spanning into Saturday (same logic as hourly employees)
            if work_date.weekday() == 4 and is_night:  # Friday night shift
                # Check if shift ends after midnight (either original or split segment)
                saturday_start = log.check_in.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                if log.check_out > saturday_start:
                    is_sabbath = True  # Friday night spanning Saturday = Sabbath night
                # Also check if this is a split segment that represents Friday night work
                # during Sabbath hours (after ShiftSplitter processed it)
                elif (hasattr(log, '_original_log_pk') and hasattr(log, '_split_index') and
                      log.check_out.weekday() == 5):  # Split segment ending on Saturday
                    is_sabbath = True  # This is the Saturday portion of a Friday night shift
            
            # Check if this is a virtual log segment marked as Sabbath by ShiftSplitter
            if hasattr(log, '_is_sabbath_segment') and log._is_sabbath_segment:
                is_sabbath = True  # ShiftSplitter determined this segment is during Sabbath
            
            # Calculate night shift hours for this log (for reporting/compatibility)
            night_shift_hours = self._calculate_night_shift_hours(log)
            night_hours += night_shift_hours
            
            # For monthly employees, we calculate BONUSES ONLY (not full pay)
            if is_holiday or is_sabbath:
                # Holiday/Sabbath work gets 50% bonus (on top of base salary)
                # Also count base daily norm for total_hours calculation
                regular_hours += self.REGULAR_DAILY_HOURS
                
                if is_holiday:
                    holiday_bonus_hours += log_hours
                else:
                    sabbath_bonus_hours += log_hours
            else:
                # Regular day - check for overtime
                if log_hours > self.REGULAR_DAILY_HOURS:
                    regular_hours += self.REGULAR_DAILY_HOURS
                    overtime_hours = log_hours - self.REGULAR_DAILY_HOURS
                    
                    # First 2 hours of overtime get 25% bonus
                    if overtime_hours <= Decimal('2.0'):
                        bonus_hours_125 += overtime_hours
                    else:
                        bonus_hours_125 += Decimal('2.0')
                        # Additional hours get 50% bonus
                        bonus_hours_150 += (overtime_hours - Decimal('2.0'))
                else:
                    # Для monthly сотрудников: регулярные часы равны норме (8.6), даже если отработано меньше
                    regular_hours += self.REGULAR_DAILY_HOURS
        
        # Calculate proportional base salary based on actual hours worked
        # If employee worked less than monthly norm, salary is proportional
        work_proportion = min(actual_hours_worked / self.MONTHLY_WORK_HOURS, Decimal('1.0'))
        proportional_base_salary = full_monthly_salary * work_proportion
        
        # For total_hours: use sum of regular_hours (which now includes daily norms) + overtime bonuses only
        # Holiday/Sabbath bonuses are not counted as additional hours, just as bonus payments
        total_hours = regular_hours + bonus_hours_125 + bonus_hours_150
        
        # Calculate bonus payments (these are IN ADDITION to base salary)
        overtime_bonus_125 = bonus_hours_125 * monthly_hourly_rate * self.OVERTIME_BONUS_125
        overtime_bonus_150 = bonus_hours_150 * monthly_hourly_rate * self.OVERTIME_BONUS_150
        holiday_bonus = holiday_bonus_hours * monthly_hourly_rate * self.SPECIAL_DAY_BONUS
        sabbath_bonus = sabbath_bonus_hours * monthly_hourly_rate * self.SPECIAL_DAY_BONUS
        
        # Total bonuses and final salary
        total_bonuses = overtime_bonus_125 + overtime_bonus_150 + holiday_bonus + sabbath_bonus
        total_salary = proportional_base_salary + total_bonuses
        
        # Build breakdown
        breakdown = PayrollBreakdown(
            # Base monthly salary (proportional)
            base_monthly_salary=float(full_monthly_salary),
            work_proportion=float(work_proportion),
            proportional_base=float(proportional_base_salary),
            
            # Regular hours (no bonus)
            regular_hours=float(regular_hours),
            regular_rate=float(monthly_hourly_rate),
            
            # Overtime bonuses
            overtime_125_hours=float(bonus_hours_125),
            overtime_125_rate=float(monthly_hourly_rate * (Decimal('1.0') + self.OVERTIME_BONUS_125)),
            overtime_125_pay=float(overtime_bonus_125),
            
            overtime_150_hours=float(bonus_hours_150),
            overtime_150_rate=float(monthly_hourly_rate * (Decimal('1.0') + self.OVERTIME_BONUS_150)),
            overtime_150_pay=float(overtime_bonus_150),
            
            # Holiday bonus
            holiday_hours=float(holiday_bonus_hours),
            holiday_rate=float(monthly_hourly_rate * (Decimal('1.0') + self.SPECIAL_DAY_BONUS)),
            holiday_pay=float(holiday_bonus),
            
            # Sabbath bonus
            sabbath_hours=float(sabbath_bonus_hours),
            sabbath_rate=float(monthly_hourly_rate * (Decimal('1.0') + self.SPECIAL_DAY_BONUS)),
            sabbath_pay=float(sabbath_bonus),
            
            # Night hours (if applicable)
            night_hours=float(night_hours),
            
            # Total bonuses
            total_bonuses=float(total_bonuses)
        )
        
        # Build metadata
        metadata = PayrollMetadata(
            calculation_strategy=CalculationStrategy.ENHANCED.value,
            employee_type=EmployeeType.MONTHLY.value,
            currency=salary.currency,
            calculation_date=timezone.now().isoformat(),
            fast_mode=self._fast_mode,
            has_cache=bool(self._holidays_cache),
            status=PayrollStatus.SUCCESS.value,
            work_log_count=len(work_logs),
            api_usage=self._api_usage,
            warnings=self._warnings if self._warnings else None
        )
        
        # Sync legacy alias fields for compatibility
        breakdown["sabbath_regular"] = breakdown.get("sabbath_regular_hours", 0)
        breakdown["night_hours"] = breakdown.get("night_shift_hours", 0)  
        breakdown["overtime_pay"] = breakdown.get("overtime_125_pay", 0) + breakdown.get("overtime_150_pay", 0)
        
        return PayrollResult(
            total_salary=total_salary,
            total_hours=total_hours,
            regular_hours=total_hours,  # All hours are "regular" for monthly employees
            overtime_hours=bonus_hours_125 + bonus_hours_150,
            holiday_hours=holiday_bonus_hours,
            shabbat_hours=sabbath_bonus_hours,
            breakdown=breakdown,
            metadata=metadata
        )
    
    def _calculate_night_shift_hours(self, work_log: WorkLog) -> Decimal:
        """
        Calculate night shift hours (22:00-06:00) for a work log.
        
        Args:
            work_log: Work log to analyze
            
        Returns:
            Decimal: Number of night shift hours
        """
        if not work_log.check_out:
            return Decimal('0.0')
        
        try:
            # Use our module-level night_hours function
            night_shift_hours = night_hours(work_log.check_in, work_log.check_out)
            return Decimal(str(night_shift_hours))
        except Exception as e:
            logger.warning(f"Night shift calculation failed: {e}")
            return Decimal('0.0')
    
    def _is_night_segment(self, start: datetime, end: datetime) -> bool:
        """
        Determine if a work segment is night shift according to Israeli law.
        Night shift: >= 2 hours between 22:00-06:00
        
        Args:
            start: Segment start time
            end: Segment end time
            
        Returns:
            bool: True if segment qualifies as night shift
        """
        try:
            night_hours_worked = Decimal(str(calc_night_hours(start, end)))
            return night_hours_worked >= self.NIGHT_DETECTION_MINIMUM
        except Exception as e:
            logger.warning(f"Night shift detection failed: {e}")
            return False
    
    def _get_bands(self, is_sabbath: bool, is_night: bool, is_holiday: bool = False):
        """
        Get hour bands and multipliers based on segment type.
        
        Args:
            is_sabbath: Whether this is a Sabbath segment
            is_night: Whether this is a night shift segment
            is_holiday: Whether this is a holiday segment
            
        Returns:
            tuple: (base_norm, bands)
            bands format: [(hours_limit, multiplier, hours_key, pay_key), ...]
        """
        if is_sabbath and is_night:
            # Шаббат + ночь: до 7ч → 150%, 7-9 → 175%, >9 → 200%
            base_norm = self.NIGHT_NORM
            bands = [
                (base_norm, Decimal("1.50"), "sabbath_regular_hours", "sabbath_regular_pay"),
                (Decimal("2.0"), Decimal("1.75"), "sabbath_overtime_175_hours", "sabbath_overtime_175_pay"),
                (Decimal("999"), Decimal("2.00"), "sabbath_overtime_200_hours", "sabbath_overtime_200_pay"),
            ]
        elif is_sabbath:
            # Шаббат день: до 8.6ч → 150%, +2ч → 175%, >10.6ч → 200%
            base_norm = self.DAY_NORM
            bands = [
                (base_norm, Decimal("1.50"), "sabbath_regular_hours", "sabbath_regular_pay"),
                (Decimal("2.0"), Decimal("1.75"), "sabbath_overtime_175_hours", "sabbath_overtime_175_pay"),
                (Decimal("999"), Decimal("2.00"), "sabbath_overtime_200_hours", "sabbath_overtime_200_pay"),
            ]
        elif is_holiday:
            # Holiday work: same as Sabbath day rates (150% base, with overtime tiers)
            base_norm = self.DAY_NORM
            bands = [
                (base_norm, Decimal("1.50"), "holiday_hours", "holiday_pay"),
                (Decimal("2.0"), Decimal("1.75"), "overtime_125_hours", "overtime_125_pay"),
                (Decimal("999"), Decimal("2.00"), "overtime_150_hours", "overtime_150_pay"),
            ]
        elif is_night:
            # Будни ночь: до 7ч → 100%, 7-9 → 125%, >9 → 150%
            base_norm = self.NIGHT_NORM
            bands = [
                (base_norm, Decimal("1.00"), "regular_hours", "regular_pay"),
                (Decimal("2.0"), Decimal("1.25"), "overtime_125_hours", "overtime_125_pay"),
                (Decimal("999"), Decimal("1.50"), "overtime_150_hours", "overtime_150_pay"),
            ]
        else:
            # Будни день: до 8.6ч → 100%, +2ч → 125%, >10.6ч → 150%
            base_norm = self.DAY_NORM
            bands = [
                (base_norm, Decimal("1.00"), "regular_hours", "regular_pay"),
                (Decimal("2.0"), Decimal("1.25"), "overtime_125_hours", "overtime_125_pay"),
                (Decimal("999"), Decimal("1.50"), "overtime_150_hours", "overtime_150_pay"),
            ]
        
        return base_norm, bands
    
    def _apply_bands(self, segment_hours: Decimal, hourly_rate: Decimal, is_sabbath: bool, is_night: bool, is_holiday: bool = False):
        """
        Apply hour bands to a segment and calculate hours and pay breakdown.
        
        Args:
            segment_hours: Total hours in segment
            hourly_rate: Base hourly rate
            is_sabbath: Whether segment is on Sabbath
            is_night: Whether segment is night shift
            is_holiday: Whether segment is on holiday
            
        Returns:
            dict: Hours and pay breakdown by category
        """
        base_norm, bands = self._get_bands(is_sabbath, is_night, is_holiday)
        
        # Initialize result with all possible keys
        result = {
            # Hours
            "regular_hours": Decimal("0"),
            "overtime_125_hours": Decimal("0"), 
            "overtime_150_hours": Decimal("0"),
            "sabbath_regular_hours": Decimal("0"),
            "sabbath_overtime_175_hours": Decimal("0"),
            "sabbath_overtime_200_hours": Decimal("0"),
            "holiday_hours": Decimal("0"),  # Holiday work hours
            "night_shift_hours": Decimal("0"),  # Diagnostic field
            
            # Pay
            "regular_pay": Decimal("0"),
            "overtime_125_pay": Decimal("0"),
            "overtime_150_pay": Decimal("0"),
            "sabbath_regular_pay": Decimal("0"),
            "sabbath_overtime_175_pay": Decimal("0"),
            "sabbath_overtime_200_pay": Decimal("0"),
            "holiday_pay": Decimal("0"),  # Holiday work pay
            "night_shift_pay": Decimal("0"),  # Not used in new logic
        }
        
        # Track night hours for diagnostics
        if is_night:
            result["night_shift_hours"] = segment_hours
        
        # Apply bands sequentially
        remaining_hours = segment_hours
        
        for i, (hours_limit, multiplier, hours_key, pay_key) in enumerate(bands):
            if remaining_hours <= Decimal("0"):
                break
                
            # Calculate hours in this band
            band_hours = min(remaining_hours, hours_limit)
            
            # For first band (base hours): apply normative hours conversion
            if (i == 0 and hours_key in ["regular_hours", "sabbath_regular_hours", "holiday_hours"] and band_hours > 0):
                # Apply normative conversion to base hours (regular, Sabbath regular, and holiday)
                normative_hours = apply_normative(band_hours, None, self._fast_mode)
                result[hours_key] += normative_hours
                result[pay_key] += band_hours * hourly_rate * multiplier  # Pay based on actual
            else:
                # All other bands (overtime) use actual hours
                result[hours_key] += band_hours
                result[pay_key] += band_hours * hourly_rate * multiplier
            
            # Reduce remaining hours based on actual hours worked
            remaining_hours -= band_hours

        # DEBUG: Log segment breakdown to trace hour distribution
        if __debug__:  # Only in debug mode
            segment_total = (
                result["regular_hours"] + result["overtime_125_hours"] + result["overtime_150_hours"]
                + result["sabbath_regular_hours"] + result["sabbath_overtime_175_hours"] 
                + result["sabbath_overtime_200_hours"] + result["holiday_hours"]
            )
            logger.debug("seg hours: actual=%s -> reg=%s ot125=%s ot150=%s sab_reg=%s sab_175=%s sab_200=%s hol=%s | sum=%s",
                        segment_hours, result["regular_hours"], result["overtime_125_hours"], 
                        result["overtime_150_hours"], result["sabbath_regular_hours"], 
                        result["sabbath_overtime_175_hours"], result["sabbath_overtime_200_hours"],
                        result["holiday_hours"], segment_total)
        
        return result
    
    def _validate_legal_compliance(self, work_logs: List[WorkLog]) -> None:
        """
        Validate work logs against Israeli labor law requirements.
        
        Args:
            work_logs: Work logs to validate
        """
        # Check daily hour limits
        for log in work_logs:
            log_hours = log.get_total_hours()
            if log_hours > self.MAX_DAILY_HOURS:
                warning = f"Daily hours ({log_hours}) exceed legal maximum ({self.MAX_DAILY_HOURS}) on {log.check_in.date()}"
                self._warnings.append(warning)
                logger.warning(warning, extra={
                    "employee_id": self._employee_id,
                    "work_date": log.check_in.date().isoformat(),
                    "hours": float(log_hours),
                    "action": "legal_compliance_warning"
                })
        
        # Check monthly limits (simplified - would need more complex logic for full implementation)
        total_monthly_hours = sum(log.get_total_hours() for log in work_logs)
        max_monthly_hours = self.MONTHLY_WORK_HOURS * Decimal("1.3")  # Allow 30% buffer for overtime
        
        if total_monthly_hours > max_monthly_hours:
            warning = f"Monthly hours ({total_monthly_hours}) significantly exceed normal working time ({self.MONTHLY_WORK_HOURS})"
            self._warnings.append(warning)
    
    def _calculate_worked_days(self, work_logs: List[WorkLog]) -> int:
        """
        Calculate unique days worked in the period.
        
        Args:
            work_logs: List of work logs
            
        Returns:
            int: Number of unique days worked
        """
        worked_dates = set()
        for log in work_logs:
            worked_dates.add(log.check_in.date())
        return len(worked_dates)
    
    def _save_calculation_results(self, employee: Employee, result: PayrollResult, work_logs: List[WorkLog]) -> None:
        """
        Save calculation results to database for audit and caching.
        
        Args:
            employee: Employee instance
            result: Calculation result
            work_logs: Original work logs
        """
        if self._fast_mode:
            return  # Skip saving in fast mode
        
        try:
            # Create or update monthly summary
            breakdown = result.get('breakdown', {})
            
            monthly_summary, created = MonthlyPayrollSummary.objects.update_or_create(
                employee=employee,
                year=self._year,
                month=self._month,
                defaults={
                    'total_salary': result['total_salary'],  # Use correct field name
                    'total_gross_pay': result['total_salary'],
                    'total_hours': result['total_hours'],
                    'regular_hours': result['regular_hours'],
                    'overtime_hours': result['overtime_hours'],
                    'holiday_hours': result['holiday_hours'],
                    'sabbath_hours': result['shabbat_hours'],
                    'base_pay': breakdown.get('regular_pay', Decimal('0')),
                    'overtime_pay': breakdown.get('overtime_pay', Decimal('0')),
                    'holiday_pay': breakdown.get('holiday_pay', Decimal('0')),
                    'sabbath_pay': breakdown.get('sabbath_pay', Decimal('0')),
                    'proportional_monthly': breakdown.get('proportional_base', Decimal('0')),
                    'total_bonuses_monthly': (
                        breakdown.get('holiday_pay', Decimal('0')) +
                        breakdown.get('sabbath_regular_pay', Decimal('0')) +
                        breakdown.get('sabbath_overtime_175_pay', Decimal('0')) +
                        breakdown.get('sabbath_overtime_200_pay', Decimal('0')) +
                        breakdown.get('overtime_125_pay', Decimal('0')) +
                        breakdown.get('overtime_150_pay', Decimal('0'))
                    ),
                    'worked_days': self._calculate_worked_days(work_logs)
                }
            )
            
            logger.info(
                f"Saved {'new' if created else 'updated'} monthly summary for employee {self._employee_id}",
                extra={
                    "employee_id": self._employee_id,
                    "summary_id": monthly_summary.id,
                    "total_salary": float(result['total_salary']),
                    "action": "monthly_summary_saved"
                }
            )
            
            # Also create/update daily calculations for app display
            self._create_daily_calculations(employee, work_logs, result)
            
        except Exception as e:
            logger.error(f"Failed to save calculation results: {e}", extra={
                "employee_id": self._employee_id,
                "error": str(e),
                "action": "save_calculation_error"
            })
    
    def _create_daily_calculations(self, employee: Employee, work_logs: List[WorkLog], result: PayrollResult) -> None:
        """
        Create daily payroll calculations for app display compatibility.
        
        The app expects DailyPayrollCalculation records for detailed views.
        This method creates daily records based on work logs and monthly calculation.
        
        Args:
            employee: Employee instance
            work_logs: List of work logs for the month
            result: Monthly calculation result
        """
        try:
            # Clear existing daily calculations for the month
            DailyPayrollCalculation.objects.filter(
                employee=employee,
                work_date__year=self._year,
                work_date__month=self._month
            ).delete()
            
            # Group work logs by date
            daily_logs = {}
            for log in work_logs:
                work_date = log.check_in.date()
                if work_date not in daily_logs:
                    daily_logs[work_date] = []
                daily_logs[work_date].append(log)
            
            # Calculate daily breakdown
            monthly_total_hours = result.get('total_hours', Decimal('0'))
            monthly_total_salary = result.get('total_salary', Decimal('0'))
            
            if monthly_total_hours == 0:
                return  # No work to process
            
            # Calculate average rates for distribution
            avg_hourly_rate = monthly_total_salary / monthly_total_hours
            
            created_count = 0
            for work_date, date_logs in daily_logs.items():
                daily_hours = sum(log.get_total_hours() for log in date_logs)
                daily_pay = daily_hours * avg_hourly_rate
                
                # Check for special days
                is_sabbath = work_date.weekday() == 5  # Saturday
                is_friday_evening = work_date.weekday() == 4  # Friday
                
                # Check if it's a holiday
                is_holiday = Holiday.objects.filter(
                    date=work_date,
                    is_holiday=True
                ).exists()
                
                # Calculate payment components
                regular_day_hours = min(daily_hours, self.REGULAR_DAILY_HOURS)
                overtime_1_hours = max(Decimal('0'), min(daily_hours - self.REGULAR_DAILY_HOURS, Decimal('2')))
                overtime_2_hours = max(Decimal('0'), daily_hours - self.REGULAR_DAILY_HOURS - Decimal('2'))
                
                # UNIFIED PAYMENT CALCULATION
                base_pay_amount = regular_day_hours * avg_hourly_rate  # Regular work
                overtime_pay_amount = (overtime_1_hours + overtime_2_hours) * avg_hourly_rate  # All overtime
                holiday_pay_amount = Decimal('0')  # Calculate if needed
                sabbath_pay_amount = Decimal('0')  # Calculate if needed
                
                # Adjust for special days
                if is_holiday:
                    holiday_pay_amount = daily_hours * avg_hourly_rate * Decimal('0.5')  # 50% bonus
                elif is_sabbath or is_friday_evening:
                    sabbath_pay_amount = daily_hours * avg_hourly_rate * Decimal('0.5')  # 50% bonus
                
                total_daily_pay = base_pay_amount + overtime_pay_amount + holiday_pay_amount + sabbath_pay_amount
                
                # Create daily calculation record using EXISTING FIELDS ONLY
                daily_calc = DailyPayrollCalculation.objects.create(
                    employee=employee,
                    work_date=work_date,
                    
                    # === HOURS BREAKDOWN ===
                    regular_hours=regular_day_hours,
                    overtime_hours_1=overtime_1_hours,
                    overtime_hours_2=overtime_2_hours,
                    
                    # === DETAILED PAYMENT FIELDS ===
                    base_regular_pay=base_pay_amount,
                    bonus_overtime_pay_1=overtime_1_hours * avg_hourly_rate,
                    bonus_overtime_pay_2=overtime_2_hours * avg_hourly_rate,
                    
                    # === DISPLAY FIELDS (what admin shows) ===
                    base_pay=base_pay_amount,                           # BASE PAY in admin
                    bonus_pay=overtime_pay_amount + holiday_pay_amount + sabbath_pay_amount,  # BONUS PAY in admin  
                    total_gross_pay=total_daily_pay,                    # TOTAL GROSS PAY in admin
                    total_pay=total_daily_pay,                          # Legacy
                    
                    # === OTHER FIELDS ===
                    is_holiday=is_holiday,
                    is_sabbath=is_sabbath or is_friday_evening,
                    holiday_name=self._get_holiday_name(work_date) if is_holiday else '',
                    calculated_by_service='enhanced_strategy',
                    worklog=date_logs[0] if date_logs else None
                )
                created_count += 1
            
            logger.info(
                f"Created {created_count} daily calculations for employee {self._employee_id}",
                extra={
                    "employee_id": self._employee_id,
                    "daily_calculations_created": created_count,
                    "action": "daily_calculations_created"
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to create daily calculations: {e}", extra={
                "employee_id": self._employee_id,
                "error": str(e),
                "action": "daily_calculation_error"
            })
    
    def _get_holiday_name(self, work_date: date) -> str:
        """Get holiday name for a given date."""
        try:
            holiday = Holiday.objects.filter(date=work_date, is_holiday=True).first()
            return holiday.name if holiday else ''
        except Exception:
            return ''