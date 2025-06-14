"""
Payroll calculation services following Israeli labor law

This module provides comprehensive payroll calculation services that comply with
Israeli labor laws, including proper handling of overtime, holiday work, Sabbath work,
and compensatory days.

Key Features:
- Israeli labor law compliance for overtime calculations
- Proper Sabbath detection (Friday evening to Saturday evening)
- Holiday work compensation with 150% pay rates
- Automatic compensatory day creation for holiday/Sabbath work
- Minimum wage enforcement
- Detailed calculation breakdowns and auditing

Israeli Labor Law Requirements Implemented:
- Maximum 12 hours per day, 45 hours per week regular time
- Maximum 16 hours overtime per week
- Overtime rates: 125% for first 2 hours, 150% for additional hours
- Holiday/Sabbath work: 150% rate + compensatory day
- Minimum wage enforcement (₪5,300/month as of 2025)
"""

from django.utils import timezone
from datetime import datetime, date, timedelta
from decimal import Decimal
import logging
import calendar

from worktime.models import WorkLog
from payroll.models import Salary, CompensatoryDay
from integrations.models import Holiday
from integrations.services.sunrise_sunset_service import SunriseSunsetService

logger = logging.getLogger(__name__)

class PayrollCalculationService:
    """
    Service for calculating payroll according to Israeli labor laws
    """
    
    # Israeli labor law constants
    MAX_DAILY_HOURS = Decimal('12')
    MAX_WEEKLY_REGULAR_HOURS = Decimal('45')
    MAX_WEEKLY_OVERTIME_HOURS = Decimal('16')
    MINIMUM_WAGE_ILS = Decimal('5300')  # Israeli minimum wage as of 2025
    
    # Pay rate multipliers
    OVERTIME_RATE_1 = Decimal('1.25')  # First 2 overtime hours
    OVERTIME_RATE_2 = Decimal('1.50')  # Additional overtime hours
    HOLIDAY_RATE = Decimal('1.50')     # Holiday work rate
    SABBATH_RATE = Decimal('1.50')     # Sabbath work rate
    
    def __init__(self, employee, year, month):
        """
        Initialize payroll calculation for specific employee and period
        
        Args:
            employee (Employee): Employee object
            year (int): Year for calculation
            month (int): Month for calculation
        """
        self.employee = employee
        self.year = year
        self.month = month
        self.salary = employee.salary_info
        self.calculation_errors = []
        self.warnings = []
        
    def is_sabbath_work(self, work_datetime):
        """
        Determine if work occurred during Sabbath according to Israeli law
        
        Sabbath is from Friday evening (18 minutes before sunset) to Saturday evening
        (42 minutes after sunset). For practical purposes, we consider work on Friday
        evening and Saturday as Sabbath work.
        
        Args:
            work_datetime (datetime): Work start time
            
        Returns:
            tuple: (is_sabbath, sabbath_type, precise_timing)
        """
        work_date = work_datetime.date()
        work_time = work_datetime.time()
        
        # Check if there's a Sabbath holiday record
        sabbath_holiday = Holiday.objects.filter(
            date=work_date,
            is_shabbat=True
        ).first()
        
        if sabbath_holiday:
            return True, 'registered_sabbath', sabbath_holiday
        
        # Check for Friday evening or Saturday work
        if work_date.weekday() == 4:  # Friday
            # Consider work after 18:00 on Friday as Sabbath work
            if work_time.hour >= 18:
                return True, 'friday_evening', None
        elif work_date.weekday() == 5:  # Saturday
            # All Saturday work is considered Sabbath work
            return True, 'saturday', None
            
        return False, None, None
    
    def is_holiday_work(self, work_date):
        """
        Check if work occurred on an Israeli holiday
        
        Args:
            work_date (date): Work date
            
        Returns:
            Holiday object or None
        """
        return Holiday.objects.filter(
            date=work_date,
            is_holiday=True,
            is_shabbat=False  # Exclude Sabbath holidays (handled separately)
        ).first()
    
    def create_compensatory_day(self, work_date, reason, work_hours=None):
        """
        Create compensatory day for holiday or Sabbath work
        
        Args:
            work_date (date): Date work occurred
            reason (str): 'holiday' or 'shabbat'
            work_hours (Decimal, optional): Hours worked
            
        Returns:
            tuple: (created, compensatory_day)
        """
        try:
            # Check if compensatory day already exists
            existing = CompensatoryDay.objects.filter(
                employee=self.employee,
                date_earned=work_date,
                reason=reason
            ).first()
            
            if existing:
                logger.debug(f"Compensatory day already exists for {self.employee.get_full_name()} "
                           f"on {work_date} (reason: {reason})")
                return False, existing
            
            # Create new compensatory day
            comp_day = CompensatoryDay.objects.create(
                employee=self.employee,
                date_earned=work_date,
                reason=reason
            )
            
            logger.info(f"Created compensatory day for {self.employee.get_full_name()} "
                       f"on {work_date} (reason: {reason})"
                       + (f" - {work_hours}h worked" if work_hours else ""))
            
            return True, comp_day
            
        except Exception as e:
            error_msg = f"Error creating compensatory day for {self.employee.get_full_name()}: {e}"
            self.calculation_errors.append(error_msg)
            logger.error(error_msg)
            return False, None
    
    def calculate_overtime_pay(self, hours_worked, base_rate, is_special_day=False):
        """
        Calculate overtime pay according to Israeli labor law
        
        Args:
            hours_worked (Decimal): Total hours worked in the day
            base_rate (Decimal): Base hourly rate
            is_special_day (bool): True if holiday/Sabbath (different rates apply)
            
        Returns:
            dict: Breakdown of regular and overtime pay
        """
        result = {
            'regular_hours': Decimal('0'),
            'regular_pay': Decimal('0'),
            'overtime_hours_1': Decimal('0'),  # First 2 overtime hours
            'overtime_pay_1': Decimal('0'),
            'overtime_hours_2': Decimal('0'),  # Additional overtime hours
            'overtime_pay_2': Decimal('0'),
            'total_pay': Decimal('0'),
            'rate_used': base_rate
        }
        
        if hours_worked <= 0:
            return result
        
        # Check for excessive daily hours
        if hours_worked > self.MAX_DAILY_HOURS:
            warning = f"Employee {self.employee.get_full_name()} exceeded maximum daily hours: {hours_worked}h > {self.MAX_DAILY_HOURS}h"
            self.warnings.append(warning)
            logger.warning(warning)
        
        # Regular hours (up to 8 hours)
        regular_hours = min(hours_worked, Decimal('8'))
        result['regular_hours'] = regular_hours
        result['regular_pay'] = regular_hours * base_rate
        
        # Overtime hours
        if hours_worked > 8:
            overtime_total = hours_worked - Decimal('8')
            
            # First 2 overtime hours at 125% (or 175% on special days)
            overtime_rate_1 = base_rate * (Decimal('1.75') if is_special_day else self.OVERTIME_RATE_1)
            overtime_hours_1 = min(overtime_total, Decimal('2'))
            result['overtime_hours_1'] = overtime_hours_1
            result['overtime_pay_1'] = overtime_hours_1 * overtime_rate_1
            
            # Additional overtime hours at 150% (or 200% on special days)
            if overtime_total > 2:
                overtime_rate_2 = base_rate * (Decimal('2.0') if is_special_day else self.OVERTIME_RATE_2)
                overtime_hours_2 = overtime_total - Decimal('2')
                result['overtime_hours_2'] = overtime_hours_2
                result['overtime_pay_2'] = overtime_hours_2 * overtime_rate_2
        
        result['total_pay'] = result['regular_pay'] + result['overtime_pay_1'] + result['overtime_pay_2']
        return result
    
    def calculate_daily_pay(self, work_log):
        """
        Calculate pay for a single work day, including special day handling
        
        Args:
            work_log (WorkLog): Work log entry
            
        Returns:
            dict: Detailed pay calculation for the day
        """
        work_date = work_log.check_in.date()
        hours_worked = work_log.get_total_hours()
        base_rate = self.salary.hourly_rate
        
        result = {
            'date': work_date,
            'hours_worked': hours_worked,
            'is_holiday': False,
            'is_sabbath': False,
            'holiday_name': None,
            'compensatory_day_created': False,
            'regular_pay': Decimal('0'),
            'overtime_pay': Decimal('0'),
            'special_day_bonus': Decimal('0'),
            'total_pay': Decimal('0'),
            'breakdown': {}
        }
        
        # Check for holiday work
        holiday = self.is_holiday_work(work_date)
        if holiday:
            result['is_holiday'] = True
            result['holiday_name'] = holiday.name
            
            # Create compensatory day
            created, _ = self.create_compensatory_day(work_date, 'holiday', hours_worked)
            result['compensatory_day_created'] = created
            
            # Calculate pay at holiday rates
            holiday_rate = base_rate * self.HOLIDAY_RATE
            pay_breakdown = self.calculate_overtime_pay(hours_worked, holiday_rate, is_special_day=True)
            result['breakdown'] = pay_breakdown
            result['total_pay'] = pay_breakdown['total_pay']
            
            return result
        
        # Check for Sabbath work
        is_sabbath, sabbath_type, sabbath_info = self.is_sabbath_work(work_log.check_in)
        if is_sabbath:
            result['is_sabbath'] = True
            result['sabbath_type'] = sabbath_type
            
            # Create compensatory day
            created, _ = self.create_compensatory_day(work_date, 'shabbat', hours_worked)
            result['compensatory_day_created'] = created
            
            # Calculate pay at Sabbath rates
            sabbath_rate = base_rate * self.SABBATH_RATE
            pay_breakdown = self.calculate_overtime_pay(hours_worked, sabbath_rate, is_special_day=True)
            result['breakdown'] = pay_breakdown
            result['total_pay'] = pay_breakdown['total_pay']
            
            return result
        
        # Regular workday calculation
        pay_breakdown = self.calculate_overtime_pay(hours_worked, base_rate, is_special_day=False)
        result['breakdown'] = pay_breakdown
        result['total_pay'] = pay_breakdown['total_pay']
        
        return result
    
    def validate_weekly_limits(self, work_logs):
        """
        Validate weekly hour limits according to Israeli labor law
        
        Args:
            work_logs (QuerySet): Work logs for the month
            
        Returns:
            list: List of violations found
        """
        violations = []
        
        # Group work logs by week
        weeks = {}
        for log in work_logs:
            # Get Monday of the week (start of work week)
            monday = log.check_in.date() - timedelta(days=log.check_in.weekday())
            if monday not in weeks:
                weeks[monday] = []
            weeks[monday].append(log)
        
        # Check each week
        for week_start, week_logs in weeks.items():
            week_end = week_start + timedelta(days=6)
            total_hours = sum(log.get_total_hours() for log in week_logs)
            
            regular_hours = min(total_hours, self.MAX_WEEKLY_REGULAR_HOURS)
            overtime_hours = max(Decimal('0'), total_hours - self.MAX_WEEKLY_REGULAR_HOURS)
            
            # Check maximum weekly hours (45 regular + 16 overtime = 61 total)
            max_total = self.MAX_WEEKLY_REGULAR_HOURS + self.MAX_WEEKLY_OVERTIME_HOURS
            if total_hours > max_total:
                violation = {
                    'type': 'weekly_hours_exceeded',
                    'week_start': week_start,
                    'week_end': week_end,
                    'total_hours': total_hours,
                    'max_allowed': max_total,
                    'excess_hours': total_hours - max_total
                }
                violations.append(violation)
                
            # Check maximum overtime hours
            elif overtime_hours > self.MAX_WEEKLY_OVERTIME_HOURS:
                violation = {
                    'type': 'overtime_exceeded',
                    'week_start': week_start,
                    'week_end': week_end,
                    'overtime_hours': overtime_hours,
                    'max_overtime': self.MAX_WEEKLY_OVERTIME_HOURS,
                    'excess_overtime': overtime_hours - self.MAX_WEEKLY_OVERTIME_HOURS
                }
                violations.append(violation)
        
        return violations
    
    def calculate_monthly_salary(self):
        """
        Calculate complete monthly salary with all components
        
        Returns:
            dict: Comprehensive salary calculation
        """
        # Get work logs for the month
        work_logs = WorkLog.objects.filter(
            employee=self.employee,
            check_in__year=self.year,
            check_in__month=self.month
        ).order_by('check_in')
        
        result = {
            'employee': self.employee.get_full_name(),
            'period': f"{self.year}-{self.month:02d}",
            'calculation_type': self.salary.calculation_type,
            'currency': self.salary.currency,
            'base_hourly_rate': self.salary.hourly_rate,
            'daily_calculations': [],
            'total_hours': Decimal('0'),
            'regular_hours': Decimal('0'),
            'overtime_hours': Decimal('0'),
            'holiday_hours': Decimal('0'),
            'sabbath_hours': Decimal('0'),
            'total_gross_pay': Decimal('0'),
            'compensatory_days_earned': 0,
            'legal_violations': [],
            'warnings': [],
            'errors': self.calculation_errors,
            'minimum_wage_applied': False
        }
        
        if not work_logs.exists():
            result['note'] = 'No work logs found for this period'
            return result
        
        # Calculate pay for each work day
        for log in work_logs:
            daily_calc = self.calculate_daily_pay(log)
            result['daily_calculations'].append(daily_calc)
            
            # Accumulate totals
            result['total_hours'] += daily_calc['hours_worked']
            result['total_gross_pay'] += daily_calc['total_pay']
            
            if daily_calc['breakdown']:
                result['regular_hours'] += daily_calc['breakdown'].get('regular_hours', Decimal('0'))
                result['overtime_hours'] += (
                    daily_calc['breakdown'].get('overtime_hours_1', Decimal('0')) +
                    daily_calc['breakdown'].get('overtime_hours_2', Decimal('0'))
                )
            
            if daily_calc['is_holiday']:
                result['holiday_hours'] += daily_calc['hours_worked']
            elif daily_calc['is_sabbath']:
                result['sabbath_hours'] += daily_calc['hours_worked']
                
            if daily_calc['compensatory_day_created']:
                result['compensatory_days_earned'] += 1
        
        # Validate legal compliance
        violations = self.validate_weekly_limits(work_logs)
        result['legal_violations'] = violations
        result['warnings'] = self.warnings
        
        # Apply minimum wage if necessary
        if (self.salary.currency == 'ILS' and 
            result['total_gross_pay'] < self.MINIMUM_WAGE_ILS and
            result['total_hours'] >= 186):  # Approximately full-time month
            
            result['original_gross_pay'] = result['total_gross_pay']
            result['total_gross_pay'] = self.MINIMUM_WAGE_ILS
            result['minimum_wage_applied'] = True
            result['minimum_wage_supplement'] = self.MINIMUM_WAGE_ILS - result['original_gross_pay']
        
        # Round final amounts
        result['total_gross_pay'] = round(result['total_gross_pay'], 2)
        result['total_hours'] = round(result['total_hours'], 2)
        result['regular_hours'] = round(result['regular_hours'], 2)
        result['overtime_hours'] = round(result['overtime_hours'], 2)
        result['holiday_hours'] = round(result['holiday_hours'], 2)
        result['sabbath_hours'] = round(result['sabbath_hours'], 2)
        
        return result

class CompensatoryDayService:
    """
    Service for managing compensatory days
    """
    
    @staticmethod
    def get_employee_compensatory_days(employee, year=None, month=None):
        """
        Get compensatory days for an employee
        
        Args:
            employee (Employee): Employee object
            year (int, optional): Year filter
            month (int, optional): Month filter
            
        Returns:
            QuerySet: CompensatoryDay objects
        """
        qs = CompensatoryDay.objects.filter(employee=employee)
        
        if year:
            qs = qs.filter(date_earned__year=year)
        if month:
            qs = qs.filter(date_earned__month=month)
            
        return qs.order_by('-date_earned')
    
    @staticmethod
    def use_compensatory_day(compensatory_day, date_used):
        """
        Mark a compensatory day as used
        
        Args:
            compensatory_day (CompensatoryDay): Compensatory day object
            date_used (date): Date the compensatory day was used
            
        Returns:
            bool: Success status
        """
        try:
            if compensatory_day.date_used:
                logger.warning(f"Compensatory day already used on {compensatory_day.date_used}")
                return False
                
            compensatory_day.date_used = date_used
            compensatory_day.save()
            
            logger.info(f"Marked compensatory day as used: {compensatory_day.employee.get_full_name()} "
                       f"earned on {compensatory_day.date_earned}, used on {date_used}")
            return True
            
        except Exception as e:
            logger.error(f"Error marking compensatory day as used: {e}")
            return False
    
    @staticmethod
    def get_compensatory_day_balance(employee):
        """
        Get the balance of unused compensatory days for an employee
        
        Args:
            employee (Employee): Employee object
            
        Returns:
            dict: Balance breakdown
        """
        all_comp_days = CompensatoryDay.objects.filter(employee=employee)
        
        total = all_comp_days.count()
        used = all_comp_days.filter(date_used__isnull=False).count()
        unused = total - used
        
        holiday_total = all_comp_days.filter(reason='holiday').count()
        holiday_used = all_comp_days.filter(reason='holiday', date_used__isnull=False).count()
        holiday_unused = holiday_total - holiday_used
        
        sabbath_total = all_comp_days.filter(reason='shabbat').count()
        sabbath_used = all_comp_days.filter(reason='shabbat', date_used__isnull=False).count()
        sabbath_unused = sabbath_total - sabbath_used
        
        return {
            'total': total,
            'used': used,
            'unused': unused,
            'holiday': {
                'total': holiday_total,
                'used': holiday_used,
                'unused': holiday_unused
            },
            'sabbath': {
                'total': sabbath_total,
                'used': sabbath_used,
                'unused': sabbath_unused
            }
        }