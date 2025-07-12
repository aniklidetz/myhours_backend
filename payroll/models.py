from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
import calendar
import logging
from users.models import Employee
from integrations.models import Holiday
from worktime.models import WorkLog
from integrations.services.sunrise_sunset_service import SunriseSunsetService
from decimal import Decimal

class Salary(models.Model):
    CURRENCY_CHOICES = [
        ('ILS', 'Israeli Shekel'),
        ('USD', 'US Dollar'),
        ('EUR', 'Euro')
    ]

    CALCULATION_TYPES = [
        ('hourly', 'hourly'),
        ('monthly', 'monthly'),
        ('project', 'project')
    ]

    employee = models.OneToOneField(
        Employee, 
        on_delete=models.CASCADE, 
        related_name='salary_info'
    )
    
    # Basic salary information
    base_salary = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(0)],
        null=True,
        blank=True,
        help_text='Monthly salary or total project cost (required for monthly/project types)'
    )
    
    hourly_rate = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        validators=[MinValueValidator(0)],
        null=True,
        blank=True,
        help_text='Hourly rate (required for hourly type)'
    )
    
    calculation_type = models.CharField(
        max_length=10, 
        choices=CALCULATION_TYPES, 
        default='hourly'
    )
    
    # For project-based payment
    project_start_date = models.DateField(null=True, blank=True)
    project_end_date = models.DateField(null=True, blank=True)
    project_completed = models.BooleanField(default=False)
    
    currency = models.CharField(
        max_length=3, 
        choices=CURRENCY_CHOICES, 
        default='ILS'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def calculate_salary(self):
        """
        Backward compatibility method for tests.
        """
        from django.utils import timezone
        now = timezone.now()
        result = self.calculate_monthly_salary(now.month, now.year)
        # For compatibility with old tests, return only total_salary
        if isinstance(result, dict) and 'total_salary' in result:
            return result['total_salary']
        return result

    def get_working_days_in_month(self, year, month):
        """
        Gets the number of working days in a month (excluding Shabbat and holidays)
        Updated for 5-day work week
        """
        try:
            _, num_days = calendar.monthrange(year, month)
            working_days = 0
            
            for day in range(1, num_days + 1):
                current_date = timezone.datetime(year, month, day).date()
                
                # Check if it's Shabbat (Saturday - 5 in Python) or Sunday (6)
                if current_date.weekday() in [5, 6]:  # Saturday or Sunday
                    continue
                    
                # Check if it's a holiday
                try:
                    holiday = Holiday.objects.filter(
                        date=current_date, 
                        is_holiday=True
                    ).exists()
                    
                    if not holiday:
                        working_days += 1
                except Exception as e:
                    # If holiday check fails, assume it's a working day
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Holiday check failed for {current_date}: {e}")
                    working_days += 1
                    
            logger = logging.getLogger(__name__)
            logger.info(f"Working days in {year}-{month:02d}: {working_days}")
            return working_days
            
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error calculating working days for {year}-{month:02d}: {e}")
            # Fallback: approximate working days for 5-day week
            _, num_days = calendar.monthrange(year, month)
            return max(1, int(num_days * 5 / 7))  # Approximate 5-day work week
    
    def get_worked_days_in_month(self, year, month):
        """
        Gets the actual worked days in a given month
        """
        try:
            # Get work logs that overlap with the month
            from datetime import date, timedelta
            import calendar
            
            # Calculate exact month boundaries
            start_date = date(year, month, 1)
            _, last_day = calendar.monthrange(year, month)
            end_date = date(year, month, last_day)
            
            work_logs = WorkLog.objects.filter(
                employee=self.employee,
                check_in__date__lte=end_date,
                check_out__date__gte=start_date,
                check_out__isnull=False
            )
            
            logger = logging.getLogger(__name__)
            logger.info(f"Found {work_logs.count()} work logs for {self.employee.get_full_name()} in {year}-{month:02d}")
            
            if not work_logs.exists():
                logger.info(f"No work logs found for {self.employee.get_full_name()} in {year}-{month:02d}")
                return 0
            
            # Get unique dates the employee worked (within the month)
            worked_days = set()
            for log in work_logs:
                # Count days where work was performed within the month
                work_start = max(log.check_in.date(), start_date)
                work_end = min(log.check_out.date(), end_date)
                
                current_date = work_start
                while current_date <= work_end:
                    worked_days.add(current_date)
                    current_date += timedelta(days=1)
            
            worked_days_count = len(worked_days)
            logger.info(f"Worked days for {self.employee.get_full_name()} in {year}-{month:02d}: {worked_days_count}")
            return worked_days_count
            
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error calculating worked days for {self.employee.get_full_name()} in {year}-{month:02d}: {e}")
            # Fallback: count unique work session dates
            try:
                from datetime import date
                start_date = date(year, month, 1)
                _, last_day = calendar.monthrange(year, month)
                end_date = date(year, month, last_day)
                
                work_logs = WorkLog.objects.filter(
                    employee=self.employee,
                    check_in__year=year,
                    check_in__month=month,
                    check_out__isnull=False
                )
                
                unique_dates = set()
                for log in work_logs:
                    if start_date <= log.check_in.date() <= end_date:
                        unique_dates.add(log.check_in.date())
                
                return len(unique_dates)
            except Exception as fallback_error:
                logger.error(f"Fallback calculation also failed: {fallback_error}")
                return 0

    def calculate_monthly_salary(self, month, year):
        """
        Calculates the monthly salary considering the payment type and Israeli labor laws.
        """
        if self.calculation_type == 'monthly':
            return self._calculate_monthly_fixed_salary(month, year)
        elif self.calculation_type == 'hourly':
            return self._calculate_hourly_salary(month, year)
        elif self.calculation_type == 'project':
            return self._calculate_project_salary(month, year)
        else:
            raise ValueError(f"Unsupported calculation type: {self.calculation_type}")

    def _calculate_monthly_fixed_salary(self, month, year):
        """
        Calculates the fixed monthly salary for salaried employees.
        Monthly employees receive proportional salary based on worked days vs expected working days,
        with additional pay for overtime/holiday/Sabbath work on top.
        """
        # Validate inputs
        if not self.base_salary or self.base_salary <= 0:
            raise ValueError("Base salary must be set and greater than 0 for monthly calculation")
        
        try:
            # Get worked hours for overtime calculations
            from payroll.services import PayrollCalculationService
            
            # Use the service to get accurate hour calculations
            service = PayrollCalculationService(self.employee, year, month, fast_mode=True)
            service_result = service.calculate_monthly_salary()
            
            # Extract total hours worked for reporting purposes
            total_hours_worked = service_result.get('total_hours', Decimal('0'))
            
            # Get worked days and working days for proportional calculation
            worked_days = self.get_worked_days_in_month(year, month)
            working_days_in_month = self.get_working_days_in_month(year, month)
            
            # Calculate proportional base salary
            if working_days_in_month > 0:
                days_proportion = Decimal(str(worked_days)) / Decimal(str(working_days_in_month))
                base_pay = self.base_salary * days_proportion
            else:
                base_pay = Decimal('0')
            
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error calculating monthly fixed salary for employee {self.employee.id}: {e}")
            # Fallback: use full base salary
            base_pay = self.base_salary
            total_hours_worked = Decimal('0')
            worked_days = 0
            working_days_in_month = 22  # fallback
        
        # For monthly employees, we still add overtime pay on top of base salary
        extra_pay = self._calculate_extras(month, year)
        
        total_salary = base_pay + extra_pay['total_extra']
        
        # Calculate work proportion for reporting
        standard_monthly_hours = Decimal('182')
        proportion = total_hours_worked / standard_monthly_hours if standard_monthly_hours > 0 else Decimal('0')
        proportion = min(proportion, Decimal('1.0'))
        
        # Ensure minimum wage (for a full month only)
        minimum_wage = Decimal('5300')  # in NIS
        if self.currency == 'ILS' and proportion >= Decimal('0.9') and total_salary < minimum_wage:
            total_salary = minimum_wage
        
        return {
            'total_salary': round(total_salary, 2),
            'base_salary': round(base_pay, 2),
            'total_hours_worked': float(total_hours_worked),
            'standard_monthly_hours': 182,
            'work_proportion': round(Decimal(str(proportion * 100)), 2),
            'worked_days': worked_days,
            'working_days_in_month': working_days_in_month,
            **extra_pay
        }
        
    def _calculate_hourly_salary(self, month, year):
        """
        Calculates hourly salary using the improved PayrollCalculationService.
        This method maintains backward compatibility while using the new service.
        """
        # Validate inputs first
        if not self.hourly_rate or self.hourly_rate <= 0:
            raise ValueError("Hourly rate must be set and greater than 0 for hourly calculation")
        
        try:
            from payroll.services import PayrollCalculationService
            
            # Use the new service for calculation
            service = PayrollCalculationService(self.employee, year, month, fast_mode=True)
            result = service.calculate_monthly_salary()
            
            # Validate service result
            if not result or 'total_gross_pay' not in result:
                logger = logging.getLogger(__name__)
                logger.error(f"PayrollCalculationService returned invalid result for employee {self.employee.id}")
                raise ValueError("PayrollCalculationService returned invalid result")
            
            # Convert to the expected format for backward compatibility
            return {
                'total_salary': result['total_gross_pay'],
                'regular_hours': float(result.get('regular_hours', 0)),
                'overtime_hours': float(result.get('overtime_hours', 0)),
                'holiday_hours': float(result.get('holiday_hours', 0)),
                'shabbat_hours': float(result.get('sabbath_hours', 0)),
                'compensatory_days': result.get('compensatory_days_earned', 0),
                'warnings': result.get('warnings', []),
                'legal_violations': result.get('legal_violations', []),
                'minimum_wage_applied': result.get('minimum_wage_applied', False),
                'work_sessions_count': result.get('work_sessions_count', 0),
                'worked_days': result.get('worked_days', 0),
                'total_hours': float(result.get('total_hours', 0))
            }
            
        except ImportError as ie:
            logger = logging.getLogger(__name__)
            logger.warning(f"PayrollCalculationService not available for employee {self.employee.id}: {ie}")
            # Fallback to legacy calculation if service is not available
            return self._calculate_hourly_salary_legacy(month, year)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error in PayrollCalculationService for employee {self.employee.id}: {e}")
            # Fallback to legacy calculation if service fails
            return self._calculate_hourly_salary_legacy(month, year)
    
    def _calculate_hourly_salary_legacy(self, month, year):
        """
        Legacy hourly salary calculation method (original implementation)
        """
        # Validate inputs
        if not self.hourly_rate or self.hourly_rate <= 0:
            raise ValueError("Hourly rate must be set and greater than 0 for hourly calculation")
        
        try:
            # Retrieve all work logs for the month - include sessions that overlap
            from datetime import date
            import calendar
            
            # Calculate exact month boundaries
            start_date = date(year, month, 1)
            _, last_day = calendar.monthrange(year, month)
            end_date = date(year, month, last_day)
            
            # Include work logs that have any overlap with the target month
            work_logs = WorkLog.objects.filter(
                employee=self.employee,
                check_in__date__lte=end_date,
                check_out__date__gte=start_date,
                check_out__isnull=False  # Only completed sessions
            ).order_by('check_in')
            
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error retrieving work logs for employee {self.employee.id}: {e}")
            # Return empty result if we can't get work logs
            return {
                'total_salary': Decimal('0.00'),
                'regular_hours': 0,
                'shabbat_hours': 0,
                'holiday_hours': 0,
                'overtime_hours': 0,
                'compensatory_days': 0,
                'error': f'Failed to retrieve work logs: {str(e)}'
            }

        total_salary = Decimal('0')
        detailed_breakdown = {
            'regular_hours': 0,
            'shabbat_hours': 0,
            'holiday_hours': 0,
            'overtime_hours': 0,
            'compensatory_days': 0
        }

        try:
            for log in work_logs:
                try:
                    holiday = Holiday.objects.filter(
                        date=log.check_in.date()
                    ).first()

                    hours_worked = log.get_total_hours()
                    
                    # Validate hours_worked - skip if None or invalid
                    if hours_worked is None:
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Skipping work log {log.id} for employee {self.employee.id}: hours_worked is None")
                        continue
                    
                    # Validate hourly_rate - should not be None for hourly calculations
                    if self.hourly_rate is None:
                        logger = logging.getLogger(__name__)
                        logger.error(f"Hourly rate is None for employee {self.employee.id} (salary {self.id})")
                        continue
                    
                    # Convert to Decimal for precise calculations
                    hours_worked = Decimal(str(hours_worked))
                    
                    # Check for maximum workday duration
                    if hours_worked > 12:
                        # warnings
                        detailed_breakdown['warnings'] = detailed_breakdown.get('warnings', [])
                        detailed_breakdown['warnings'].append(f"Exceeded maximum workday duration ({log.check_in.date()}): {hours_worked} hours")

                    if holiday:
                        # Work on a holiday or Shabbat - add a compensatory day
                        self._add_compensatory_day(log.check_in.date(), holiday.is_shabbat)
                        detailed_breakdown['compensatory_days'] += 1

                        # Work on a holiday
                        if holiday.is_shabbat:
                            # Shabbat - 150% for the first 8 hours
                            if hours_worked <= Decimal('8'):
                                total_salary += hours_worked * (self.hourly_rate * Decimal('1.5'))
                                detailed_breakdown['shabbat_hours'] += float(hours_worked)
                            else:
                                # First 8 hours at 150%
                                total_salary += Decimal('8') * (self.hourly_rate * Decimal('1.5'))
                                detailed_breakdown['shabbat_hours'] += 8
                                
                                # Remaining hours at higher rates
                                overtime_hours = hours_worked - Decimal('8')
                                total_salary += overtime_hours * (self.hourly_rate * Decimal('1.75'))
                                detailed_breakdown['overtime_hours'] += float(overtime_hours)

                        elif holiday.is_holiday:
                            # Holiday - 150% for the first 8 hours
                            if hours_worked <= Decimal('8'):
                                total_salary += hours_worked * (self.hourly_rate * Decimal('1.5'))
                                detailed_breakdown['holiday_hours'] += float(hours_worked)
                            else:
                                # 150% for the first 8 hours
                                total_salary += Decimal('8') * (self.hourly_rate * Decimal('1.5'))
                                detailed_breakdown['holiday_hours'] += 8
                                
                                # Next 2 hours at 175%
                                overtime_hours_1 = min(hours_worked - Decimal('8'), Decimal('2'))
                                total_salary += overtime_hours_1 * (self.hourly_rate * Decimal('1.75'))
                                detailed_breakdown['overtime_hours'] += float(overtime_hours_1)
                                
                                # Remaining hours at 200%
                                if hours_worked > Decimal('10'):
                                    overtime_hours_2 = hours_worked - Decimal('10')
                                    total_salary += overtime_hours_2 * (self.hourly_rate * Decimal('2.0'))
                                    detailed_breakdown['overtime_hours'] += float(overtime_hours_2)
                    else:
                        # Check for Sabbath work using precise sunset times
                        work_date = log.check_in.date()
                        work_datetime = log.check_in
                        
                        is_sabbath_work = self._is_sabbath_work_precise(work_datetime)
                        
                        if is_sabbath_work:
                            # Add compensatory day for Sabbath work
                            self._add_compensatory_day(work_date, True)
                            detailed_breakdown['compensatory_days'] += 1
                    
                            # Sabbath - 150% for the first 8 hours
                            if hours_worked <= Decimal('8'):
                                total_salary += hours_worked * (self.hourly_rate * Decimal('1.5'))
                                detailed_breakdown['shabbat_hours'] += float(hours_worked)
                            else:
                                # First 8 hours at 150%
                                total_salary += Decimal('8') * (self.hourly_rate * Decimal('1.5'))
                                detailed_breakdown['shabbat_hours'] += 8
                                
                                # Remaining hours at higher rates
                                overtime_hours = hours_worked - Decimal('8')
                                total_salary += overtime_hours * (self.hourly_rate * Decimal('1.75'))
                                detailed_breakdown['overtime_hours'] += float(overtime_hours)
                        else:
                            # Work on a regular weekday
                            regular_hours = min(hours_worked, Decimal('8'))
                            total_salary += regular_hours * self.hourly_rate
                            detailed_breakdown['regular_hours'] += float(regular_hours)

                            # Overtime hours
                            if hours_worked > Decimal('8'):
                                overtime_hours = hours_worked - Decimal('8')
                                
                                # First 2 overtime hours
                                if overtime_hours <= Decimal('2'):
                                    total_salary += overtime_hours * (self.hourly_rate * Decimal('1.25'))
                                    detailed_breakdown['overtime_hours'] += float(overtime_hours)
                                else:
                                    # First 2 hours at 125%
                                    total_salary += Decimal('2') * (self.hourly_rate * Decimal('1.25'))
                                    detailed_breakdown['overtime_hours'] += 2
                                    
                                    # Remaining overtime at 150%
                                    remaining_overtime = overtime_hours - Decimal('2')
                                    total_salary += remaining_overtime * (self.hourly_rate * Decimal('1.5'))
                                    detailed_breakdown['overtime_hours'] += float(remaining_overtime)
                
                except Exception as log_error:
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error processing work log {log.id} for employee {self.employee.id}: {log_error}")
                    # Continue with next log instead of failing entire calculation
                    continue
        
        except Exception as calc_error:
            logger = logging.getLogger(__name__)
            logger.error(f"Error in hourly salary calculation for employee {self.employee.id}: {calc_error}")
            # Return fallback result
            return {
                'total_salary': Decimal('0.00'),
                'regular_hours': 0,
                'shabbat_hours': 0,
                'holiday_hours': 0,
                'overtime_hours': 0,
                'compensatory_days': 0,
                'error': str(calc_error)
            }

        # Minimum wage check - updated for 5-day work week
        minimum_wage = Decimal('5300')  # Minimum wage in Israel (NIS)
        if self.currency == 'ILS' and total_salary < minimum_wage and detailed_breakdown['regular_hours'] >= 182:  # Standard monthly hours for 5-day week
            total_salary = minimum_wage
            detailed_breakdown['minimum_wage_applied'] = True

        return {
            'total_salary': round(total_salary, 2),
            **detailed_breakdown
        }

    def _calculate_project_salary(self, month, year):
        """
        Calculates project-based salary
        """
        # If the project is completed, pay the full amount
        if self.project_completed:
            return {
                'total_salary': self.base_salary,
                'project_status': 'Completed',
                'payment_type': 'Full payment'
            }

        # Otherwise, calculate by phases or progress
        # You can add logic here to calculate partial payment based on progress
        # For example, by completion percentage or reaching specific milestones

        # Example: linear calculation from project start to end
        if not self.project_start_date or not self.project_end_date:
            return {
                'total_salary': Decimal('0'),
                'project_status': 'Not configured',
                'error': 'Project start and end dates are not set'
            }

        # Calculate project progress
        start_date = self.project_start_date
        end_date = self.project_end_date
        current_date = timezone.datetime(year, month, 1).date()

        # If the current date is before project start
        if current_date < start_date:
            return {
                'total_salary': Decimal('0'),
                'project_status': 'Not started',
                'start_date': start_date,
                'end_date': end_date
            }

        # If the current date is after project end
        if current_date > end_date:
            if not self.project_completed:
                return {
                    'total_salary': Decimal('0'),
                    'project_status': 'Overdue',
                    'start_date': start_date,
                    'end_date': end_date,
                    'message': 'Project is overdue but not marked as completed'
                }
            else:
                return {
                    'total_salary': self.base_salary,
                    'project_status': 'Completed',
                    'payment_type': 'Full payment'
                }
                
        # Calculate the portion of the project completed in the current month
        total_days = (end_date - start_date).days

        # Define start and end of the current month
        _, last_day = calendar.monthrange(year, month)
        month_start = max(start_date, timezone.datetime(year, month, 1).date())
        month_end = min(end_date, timezone.datetime(year, month, last_day).date())

        # Days in the current month
        days_in_month = (month_end - month_start).days + 1

        # Portion of the overall project completed this month
        proportion = Decimal(str(days_in_month / total_days)) if total_days > 0 else Decimal('0')

        # Monthly salary
        monthly_salary = self.base_salary * proportion

        return {
            'total_salary': round(monthly_salary, 2),
            'project_status': 'In progress',
            'start_date': start_date,
            'end_date': end_date,
            'progress_percent': round(Decimal(str((days_in_month / total_days) * 100)), 2) if total_days > 0 else Decimal('0')
        }

    def _calculate_extras(self, month, year):
        """
        Calculates additional payments for overtime, holidays, and Shabbat
        """
        # For monthly employees, derive hourly rate from base salary
        effective_hourly_rate = self.hourly_rate
        
        if self.calculation_type == 'monthly' and self.base_salary:
            # Calculate hourly rate from monthly salary (185 hours per month standard)
            standard_monthly_hours = Decimal('185')
            effective_hourly_rate = self.base_salary / standard_monthly_hours
        elif not self.hourly_rate or self.hourly_rate <= 0:
            logger = logging.getLogger(__name__)
            logger.warning(f"Employee {self.employee.id} has no valid hourly_rate - skipping extras calculation")
            return {
                'total_extra': Decimal('0.00'),
                'shabbat_hours': 0,
                'holiday_hours': 0,
                'overtime_hours': 0,
                'compensatory_days': 0
            }
        
        work_logs = WorkLog.objects.filter(
            employee=self.employee,
            check_in__year=year,
            check_in__month=month
        )

        extra_pay = Decimal('0')
        detailed = {
            'shabbat_hours': 0,
            'holiday_hours': 0,
            'overtime_hours': 0,
            'compensatory_days': 0
        }

        for log in work_logs:
            holiday = Holiday.objects.filter(
                date=log.check_in.date()
            ).first()

            hours_worked = log.get_total_hours()
            
            # Skip if hours_worked is None or invalid
            if hours_worked is None or hours_worked <= 0:
                logger = logging.getLogger(__name__)
                logger.warning(f"Invalid hours_worked for log {log.id}: {hours_worked}")
                continue

            if holiday:
                # Add compensatory day
                self._add_compensatory_day(log.check_in.date(), holiday.is_shabbat)
                detailed['compensatory_days'] += 1

                # Bonuses for working on Shabbat/holiday
                if holiday.is_shabbat:
                    # Shabbat premium - 50% bonus only (since base salary already paid)
                    extra_pay += hours_worked * (effective_hourly_rate * Decimal('0.5'))
                    detailed['shabbat_hours'] += float(hours_worked)
                elif holiday.is_holiday:
                    # Holiday premium - 50% bonus only (since base salary already paid)
                    extra_pay += hours_worked * (effective_hourly_rate * Decimal('0.5'))
                    detailed['holiday_hours'] += float(hours_worked)

            # Overtime bonuses
            if hours_worked > 8:
                overtime_hours = hours_worked - 8

                # First 2 hours - 25% extra
                overtime_1 = min(overtime_hours, 2)
                extra_pay += overtime_1 * (effective_hourly_rate * Decimal('0.25'))  # bonus only

                # Remaining hours - 50% extra
                overtime_2 = max(0, overtime_hours - 2)
                extra_pay += overtime_2 * (effective_hourly_rate * Decimal('0.5'))  # bonus only

                detailed['overtime_hours'] += float(overtime_hours)

        return {
            'total_extra': round(extra_pay, 2),
            **detailed
        }
    
    def _add_compensatory_day(self, work_date, is_shabbat):
        """
        Adds a compensatory day for working on a holiday or Shabbat
        """
        reason = 'shabbat' if is_shabbat else 'holiday'

        # Check if a compensatory day has already been added for this specific reason
        exists = CompensatoryDay.objects.filter(
            employee=self.employee,
            date_earned=work_date,
            reason=reason
        ).exists()

        if not exists:
            CompensatoryDay.objects.create(
                employee=self.employee,
                date_earned=work_date,
                reason=reason
            )
            
            # Log the creation for audit purposes
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Created compensatory day for {self.employee.get_full_name()} "
                       f"on {work_date} (reason: {reason})")

    def clean(self):
        """
        Validates salary fields based on calculation_type
        """
        super().clean()
        
        if self.calculation_type == 'hourly':
            # For hourly type: hourly_rate required, base_salary should be null/0
            if not self.hourly_rate or self.hourly_rate <= 0:
                raise ValidationError({
                    'hourly_rate': 'Hourly rate is required and must be greater than 0 for hourly calculation type.'
                })
            if self.base_salary and self.base_salary > 0:
                raise ValidationError({
                    'base_salary': 'Base salary should be empty (null/0) for hourly calculation type.'
                })
                
        elif self.calculation_type == 'monthly':
            # For monthly type: base_salary required, hourly_rate should be null/0
            if not self.base_salary or self.base_salary <= 0:
                raise ValidationError({
                    'base_salary': 'Base salary is required and must be greater than 0 for monthly calculation type.'
                })
            if self.hourly_rate and self.hourly_rate > 0:
                raise ValidationError({
                    'hourly_rate': 'Hourly rate should be empty (null/0) for monthly calculation type.'
                })
                
        elif self.calculation_type == 'project':
            # For project type: exactly one field should be filled
            has_base_salary = self.base_salary and self.base_salary > 0
            has_hourly_rate = self.hourly_rate and self.hourly_rate > 0
            
            if not has_base_salary and not has_hourly_rate:
                raise ValidationError(
                    'For project calculation type, either base_salary (for fixed-bid projects) '
                    'or hourly_rate (for hourly projects) must be specified.'
                )
            if has_base_salary and has_hourly_rate:
                raise ValidationError(
                    'For project calculation type, specify either base_salary OR hourly_rate, not both.'
                )
                
            # Project dates validation
            if not self.project_start_date or not self.project_end_date:
                raise ValidationError(
                    'Project start and end dates must be specified for project-based payment.'
                )
            if self.project_start_date > self.project_end_date:
                raise ValidationError(
                    'Project start date cannot be later than end date.'
                )

    def validate_constraints(self):
        """
        Validates constraints on overtime and maximum daily working hours
        Updated for 5-day work week (42 hours regular + 16 hours overtime = 58 hours max)
        """
        # Weekly constraints
        current_date = timezone.now().date()
        start_of_week = current_date - timezone.timedelta(days=current_date.weekday())
        end_of_week = start_of_week + timezone.timedelta(days=6)

        weekly_work_logs = WorkLog.objects.filter(
            employee=self.employee,
            check_in__date__gte=start_of_week,
            check_in__date__lte=end_of_week
        )

        # Check for weekly overtime limit - updated for 5-day work week
        weekly_hours = 0
        for log in weekly_work_logs:
            hours = log.get_total_hours()
            weekly_hours += hours

        # 5-day work week: max 42 regular hours + 16 overtime hours = 58 total
        max_weekly_hours = 58
        if weekly_hours > max_weekly_hours:
            raise ValidationError(f"Exceeded maximum weekly hours ({max_weekly_hours} hours) for 5-day work week")

        # Check for maximum daily work hours
        for log in weekly_work_logs:
            if log.get_total_hours() > 12:
                raise ValidationError(f"Exceeded maximum daily work hours (12 hours) for date {log.check_in.date()}")

    def _is_sabbath_work_precise(self, work_datetime):
        """
        Check if work occurred during Sabbath using precise sunset times
        
        Args:
            work_datetime (datetime): Work start time
            
        Returns:
            bool: True if work occurred during Sabbath
        """
        work_date = work_datetime.date()
        work_time = work_datetime.time()
        
        # Check for registered Sabbath in Holiday model first
        sabbath_holiday = Holiday.objects.filter(
            date=work_date,
            is_shabbat=True
        ).first()
        
        if sabbath_holiday and sabbath_holiday.start_time and sabbath_holiday.end_time:
            # Use precise times from database if available
            import pytz
            
            # Convert database times to Israel timezone
            israel_tz = pytz.timezone('Asia/Jerusalem')
            start_datetime_israel = sabbath_holiday.start_time.astimezone(israel_tz)
            end_datetime_israel = sabbath_holiday.end_time.astimezone(israel_tz)
            
            # Ensure work_datetime is timezone-aware and in Israel timezone
            if work_datetime.tzinfo is None:
                work_datetime = timezone.make_aware(work_datetime)
            work_datetime_israel = work_datetime.astimezone(israel_tz)
            
            # Handle Sabbath spanning midnight (Friday evening to Saturday evening)
            if work_date.weekday() == 4:  # Friday
                return work_datetime_israel >= start_datetime_israel
            elif work_date.weekday() == 5:  # Saturday
                return work_datetime_israel <= end_datetime_israel
        
        # Fallback: use SunriseSunsetService for precise calculation
        try:
            if work_date.weekday() == 4:  # Friday
                shabbat_times = SunriseSunsetService.get_shabbat_times(work_date)
                if not shabbat_times.get('is_estimated', True):
                    from datetime import datetime
                    import pytz
                    
                    # Parse UTC time from API
                    shabbat_start_utc = datetime.fromisoformat(shabbat_times['start'].replace('Z', '+00:00'))
                    
                    # Convert to Israel timezone (UTC+2/UTC+3)
                    israel_tz = pytz.timezone('Asia/Jerusalem')
                    shabbat_start_local = shabbat_start_utc.astimezone(israel_tz)
                    
                    # Ensure work_datetime is timezone-aware
                    if work_datetime.tzinfo is None:
                        work_datetime = timezone.make_aware(work_datetime)
                    work_local = work_datetime.astimezone(israel_tz)
                    
                    return work_local >= shabbat_start_local
                else:
                    # Fallback to 18:00 if API fails
                    return work_time.hour >= 18
            elif work_date.weekday() == 5:  # Saturday
                # All Saturday work is Sabbath work
                return True
                
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning(f"Error checking precise Sabbath times for {work_date}: {e}")
            # Fallback to simple time check
            if work_date.weekday() == 4 and work_time.hour >= 18:
                return True
            elif work_date.weekday() == 5:
                return True
                
        return False

    def __str__(self):
        return f"Salary {self.employee.get_full_name()} ({self.get_calculation_type_display()})"

    def save(self, *args, **kwargs):
        # If the record is new (not yet saved to the database)
        if not self.pk:
            # Set calculation type based on employee's employment type
            employment_type_mapping = {
                'hourly': 'hourly',
                'monthly': 'monthly',
                'contract': 'project'
            }
            self.calculation_type = employment_type_mapping.get(
                self.employee.employment_type, 'hourly')

        # Validate salary fields based on calculation_type
        self.clean()
        self.validate_constraints()
        return super().save(*args, **kwargs)


class CompensatoryDay(models.Model):
    """Compensatory days for working on Shabbat or holidays"""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='compensatory_days')
    date_earned = models.DateField()
    reason = models.CharField(max_length=50, choices=[
        ('shabbat', 'Work on Shabbat'),
        ('holiday', 'Work on Holiday')
    ])
    date_used = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        status = "Used" if self.date_used else "Not used"
        return f"{self.employee} - {self.get_reason_display()} ({status})"

    class Meta:
        verbose_name = "Compensatory Day"
        verbose_name_plural = "Compensatory Days"
        ordering = ['-date_earned']