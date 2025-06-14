from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
import calendar
from users.models import Employee
from integrations.models import Holiday
from worktime.models import WorkLog
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
        help_text='Monthly rate or total project cost'
    )
    
    hourly_rate = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        validators=[MinValueValidator(0)],
        help_text='Hourly rate'
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
        """
        _, num_days = calendar.monthrange(year, month)
        working_days = 0
        
        for day in range(1, num_days + 1):
            current_date = timezone.datetime(year, month, day).date()
            
            # Check if it's Shabbat (Saturday - 5 in Python)
            if current_date.weekday() == 5:
                continue
                
            # Check if it's a holiday
            holiday = Holiday.objects.filter(
                date=current_date, 
                is_holiday=True
            ).exists()
            
            if not holiday:
                working_days += 1
                
        return working_days
    
    def get_worked_days_in_month(self, year, month):
        """
        Gets the actual worked days in a given month
        """
        work_logs = WorkLog.objects.filter(
            employee=self.employee,
            check_in__year=year,
            check_in__month=month
        )
        
        # Get unique dates the employee worked
        worked_days = set()
        for log in work_logs:
            worked_days.add(log.check_in.date())
            
        return len(worked_days)

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
        Calculates the fixed monthly salary considering worked days.
        """
        total_working_days = self.get_working_days_in_month(year, month)
        worked_days = self.get_worked_days_in_month(year, month)
        
        # Calculate the proportion of salary based on worked days
        if total_working_days > 0:
            proportion = worked_days / total_working_days
        else:
            proportion = Decimal('0')
            
        base_pay = self.base_salary * Decimal(str(proportion))
        
        # Check overtime, holiday, and Shabbat work
        extra_pay = self._calculate_extras(month, year)
        
        total_salary = base_pay + extra_pay['total_extra']
        
        # Ensure minimum wage (for a full month)
        minimum_wage = Decimal('5300')  # in NIS
        if self.currency == 'ILS' and proportion == 1 and total_salary < minimum_wage:
            total_salary = minimum_wage
        
        return {
            'total_salary': round(total_salary, 2),
            'base_salary': round(base_pay, 2),
            'total_working_days': total_working_days,
            'worked_days': worked_days,
            'work_proportion': round(Decimal(str(proportion * 100)), 2),
            **extra_pay
        }
        
    def _calculate_hourly_salary(self, month, year):
        """
        Calculates hourly salary using the improved PayrollCalculationService.
        This method maintains backward compatibility while using the new service.
        """
        try:
            from payroll.services import PayrollCalculationService
            
            # Use the new service for calculation
            service = PayrollCalculationService(self.employee, year, month)
            result = service.calculate_monthly_salary()
            
            # Convert to the expected format for backward compatibility
            return {
                'total_salary': result['total_gross_pay'],
                'regular_hours': float(result['regular_hours']),
                'overtime_hours': float(result['overtime_hours']),
                'holiday_hours': float(result['holiday_hours']),
                'shabbat_hours': float(result['sabbath_hours']),
                'compensatory_days': result['compensatory_days_earned'],
                'warnings': result.get('warnings', []),
                'legal_violations': result.get('legal_violations', []),
                'minimum_wage_applied': result.get('minimum_wage_applied', False)
            }
            
        except ImportError:
            # Fallback to legacy calculation if service is not available
            return self._calculate_hourly_salary_legacy(month, year)
    
    def _calculate_hourly_salary_legacy(self, month, year):
        """
        Legacy hourly salary calculation method (original implementation)
        """
        # Retrieve all work logs for the month
        work_logs = WorkLog.objects.filter(
            employee=self.employee,
            check_in__year=year,
            check_in__month=month
        ).order_by('check_in')

        total_salary = Decimal('0')
        detailed_breakdown = {
            'regular_hours': 0,
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
                    if hours_worked <= 8:
                        total_salary += hours_worked * (self.hourly_rate * Decimal('1.5'))
                        detailed_breakdown['shabbat_hours'] += float(hours_worked)
                    else:
                        # First 8 hours at 150%
                        total_salary += Decimal('8') * (self.hourly_rate * Decimal('1.5'))
                        detailed_breakdown['shabbat_hours'] += 8
                        
                        # Remaining hours at higher rates
                        overtime_hours = hours_worked - 8
                        total_salary += overtime_hours * (self.hourly_rate * Decimal('1.75'))
                        detailed_breakdown['overtime_hours'] += float(overtime_hours)

                elif holiday.is_holiday:
                    # Holiday - 150% for the first 8 hours
                    if hours_worked <= 8:
                        total_salary += hours_worked * (self.hourly_rate * Decimal('1.5'))
                        detailed_breakdown['holiday_hours'] += float(hours_worked)
                    else:
                        # 150% for the first 8 hours
                        total_salary += Decimal('8') * (self.hourly_rate * Decimal('1.5'))
                        detailed_breakdown['holiday_hours'] += 8
                        
                        # Next 2 hours at 175%
                        overtime_hours_1 = min(hours_worked - 8, 2)
                        total_salary += overtime_hours_1 * (self.hourly_rate * Decimal('1.75'))
                        detailed_breakdown['overtime_hours'] += float(overtime_hours_1)
                        
                        # Remaining hours at 200%
                        if hours_worked > 10:
                            overtime_hours_2 = hours_worked - 10
                            total_salary += overtime_hours_2 * (self.hourly_rate * Decimal('2.0'))
                            detailed_breakdown['overtime_hours'] += float(overtime_hours_2)
            else:
                # Check for Sabbath work (Friday evening/Saturday) even if not marked as holiday
                work_date = log.check_in.date()
                work_time = log.check_in.time()
                
                is_sabbath_work = False
                if work_date.weekday() == 4 and work_time.hour >= 18:  # Friday evening
                    is_sabbath_work = True
                elif work_date.weekday() == 5:  # Saturday
                    is_sabbath_work = True
                
                if is_sabbath_work:
                    # Add compensatory day for Sabbath work
                    self._add_compensatory_day(work_date, True)
                    detailed_breakdown['compensatory_days'] += 1
                    
                    # Sabbath - 150% for the first 8 hours
                    if hours_worked <= 8:
                        total_salary += hours_worked * (self.hourly_rate * Decimal('1.5'))
                        detailed_breakdown['shabbat_hours'] += float(hours_worked)
                    else:
                        # First 8 hours at 150%
                        total_salary += Decimal('8') * (self.hourly_rate * Decimal('1.5'))
                        detailed_breakdown['shabbat_hours'] += 8
                        
                        # Remaining hours at higher rates
                        overtime_hours = hours_worked - 8
                        total_salary += overtime_hours * (self.hourly_rate * Decimal('1.75'))
                        detailed_breakdown['overtime_hours'] += float(overtime_hours)
                else:
                    # Work on a regular weekday
                    regular_hours = min(hours_worked, 8)
                    total_salary += regular_hours * self.hourly_rate
                    detailed_breakdown['regular_hours'] += float(regular_hours)

                    # Overtime hours
                    if hours_worked > 8:
                        overtime_hours = hours_worked - 8
                        
                        # First 2 overtime hours
                        if overtime_hours <= 2:
                            total_salary += overtime_hours * (self.hourly_rate * Decimal('1.25'))
                            detailed_breakdown['overtime_hours'] += float(overtime_hours)
                        else:
                            # First 2 hours at 125%
                            total_salary += Decimal('2') * (self.hourly_rate * Decimal('1.25'))
                            detailed_breakdown['overtime_hours'] += 2
                            
                            # Remaining overtime at 150%
                            remaining_overtime = overtime_hours - 2
                            total_salary += remaining_overtime * (self.hourly_rate * Decimal('1.5'))
                            detailed_breakdown['overtime_hours'] += float(remaining_overtime)

        # Minimum wage check
        minimum_wage = Decimal('5300')  # Minimum wage in Israel (NIS)
        if self.currency == 'ILS' and total_salary < minimum_wage and detailed_breakdown['regular_hours'] >= 186:  # ~186 working hours per month
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

            if holiday:
                # Add compensatory day
                self._add_compensatory_day(log.check_in.date(), holiday.is_shabbat)
                detailed['compensatory_days'] += 1

                # Bonuses for working on Shabbat/holiday
                if holiday.is_shabbat:
                    # Shabbat bonus - 50% extra
                    extra_pay += hours_worked * (self.hourly_rate * Decimal('0.5'))  # bonus only
                    detailed['shabbat_hours'] += float(hours_worked)
                elif holiday.is_holiday:
                    # Holiday bonus - 50% extra
                    extra_pay += hours_worked * (self.hourly_rate * Decimal('0.5'))  # bonus only
                    detailed['holiday_hours'] += float(hours_worked)

            # Overtime bonuses
            if hours_worked > 8:
                overtime_hours = hours_worked - 8

                # First 2 hours - 25% extra
                overtime_1 = min(overtime_hours, 2)
                extra_pay += overtime_1 * (self.hourly_rate * Decimal('0.25'))  # bonus only

                # Remaining hours - 50% extra
                overtime_2 = max(0, overtime_hours - 2)
                extra_pay += overtime_2 * (self.hourly_rate * Decimal('0.5'))  # bonus only

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

    def validate_constraints(self):
        """
        Validates constraints on overtime and maximum daily working hours
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

        # Check for weekly overtime limit
        weekly_overtime = 0
        for log in weekly_work_logs:
            hours = log.get_total_hours()
            if hours > 8:
                weekly_overtime += hours - 8

        if weekly_overtime > 16:
            raise ValidationError("Exceeded maximum weekly overtime hours (16 hours)")

        # Check for maximum daily work hours
        for log in weekly_work_logs:
            if log.get_total_hours() > 12:
                raise ValidationError(f"Exceeded maximum daily work hours (12 hours) for date {log.check_in.date()}")

        # Additional checks for project-based payment
        if self.calculation_type == 'project':
            if not self.project_start_date or not self.project_end_date:
                raise ValidationError("Project start and end dates must be specified for project-based payment")

            if self.project_start_date > self.project_end_date:
                raise ValidationError("Project start date cannot be later than end date")

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