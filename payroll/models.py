import calendar
import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from integrations.models import Holiday
# Removed import to avoid circular dependency - will import lazily when needed
from users.models import Employee
from worktime.models import WorkLog


class Salary(models.Model):
    CURRENCY_CHOICES = [
        ("ILS", "Israeli Shekel"),
        ("USD", "US Dollar"),
        ("EUR", "Euro"),
    ]

    CALCULATION_TYPES = [
        ("hourly", "hourly"),
        ("monthly", "monthly"),
        ("project", "project"),
    ]

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="salaries"
    )

    # Basic salary information
    base_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        null=True,
        blank=True,
        help_text="Monthly salary or total project cost (required for monthly/project types)",
    )

    hourly_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        null=True,
        blank=True,
        help_text="Hourly rate (required for hourly type)",
    )

    calculation_type = models.CharField(
        max_length=10, choices=CALCULATION_TYPES, default="hourly"
    )

    # For project-based payment
    project_start_date = models.DateField(null=True, blank=True)
    project_end_date = models.DateField(null=True, blank=True)
    project_completed = models.BooleanField(default=False)

    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="ILS")

    # Active status - only one active salary per employee allowed
    is_active = models.BooleanField(
        default=True, help_text="Whether this salary configuration is currently active"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- Backward-compat: tests/старый код обращаются к monthly_hourly ---
    @property
    def monthly_hourly(self):
        # alias на фактическое поле с почасовой ставкой
        return getattr(self, "hourly_rate", None)

    @monthly_hourly.setter
    def monthly_hourly(self, value):
        setattr(self, "hourly_rate", value)

    def calculate_salary(self):
        """
        Backward compatibility method for tests.
        """
        from django.utils import timezone

        now = timezone.now()
        result = self.calculate_monthly_salary(now.month, now.year)
        # For compatibility with old tests, return only total_salary
        if isinstance(result, dict) and "total_salary" in result:
            return result["total_salary"]
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
                        date=current_date, is_holiday=True
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
            from core.logging_utils import err_tag

            logger.error(
                "Error calculating working days",
                extra={"err": err_tag(e), "year": year, "month": month},
            )
            # Fallback: approximate working days for 5-day week
            _, num_days = calendar.monthrange(year, month)
            return max(1, int(num_days * 5 / 7))  # Approximate 5-day work week

    def get_worked_days_in_month(self, year, month):
        """
        Gets the actual worked days in a given month
        """
        try:
            # Get work logs that overlap with the month
            import calendar
            from datetime import date, timedelta

            # Calculate exact month boundaries
            start_date = date(year, month, 1)
            _, last_day = calendar.monthrange(year, month)
            end_date = date(year, month, last_day)

            work_logs = WorkLog.objects.filter(
                employee=self.employee,
                check_in__date__lte=end_date,
                check_out__date__gte=start_date,
                check_out__isnull=False,
            )

            logger = logging.getLogger(__name__)
            logger.info(
                f"Found {work_logs.count()} work logs for {self.employee.get_full_name()} in {year}-{month:02d}"
            )

            if not work_logs.exists():
                logger.info(
                    f"No work logs found for {self.employee.get_full_name()} in {year}-{month:02d}"
                )
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
            logger.info(
                f"Worked days for {self.employee.get_full_name()} in {year}-{month:02d}: {worked_days_count}"
            )
            return worked_days_count

        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(
                f"Error calculating worked days for {self.employee.get_full_name()} in {year}-{month:02d}: {e}"
            )
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
                    check_out__isnull=False,
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
        DEPRECATED: Use PayrollService with CalculationStrategy.ENHANCED instead.

        This method implements the Fat Model anti-pattern and should not be used.

        Legacy method for calculating monthly salary considering the payment type and Israeli labor laws.
        Will be removed in future version.

        Args:
            month: Month number (1-12)
            year: Year (YYYY)

        Returns:
            Calculation result

        Raises:
            DeprecationWarning: This method is deprecated
        """
        import warnings
        from payroll.services.payroll_service import get_payroll_service
        from payroll.services.contracts import CalculationContext

        warnings.warn(
            "Salary.calculate_monthly_salary() is deprecated. Use PayrollService directly.",
            DeprecationWarning,
            stacklevel=2
        )

        service = get_payroll_service()
        context = CalculationContext(
            employee_id=self.employee.id,
            year=year,
            month=month,
            user_id=0  # user_id=0 for system call
        )

        # The result from the service is already a dictionary in the correct format
        return service.calculate(context)


    def clean(self):
        """Validate Salary model fields based on calculation_type"""
        from django.core.exceptions import ValidationError
        errors = {}

        # Monthly calculation requires base_salary
        if self.calculation_type == "monthly":
            if not self.base_salary or self.base_salary <= 0:
                errors['base_salary'] = "Monthly calculation type requires a positive base salary."
            if self.hourly_rate and self.hourly_rate > 0:
                errors['hourly_rate'] = "Monthly calculation type should not have hourly rate."

        # Hourly calculation requires hourly_rate
        elif self.calculation_type == "hourly":
            if not self.hourly_rate or self.hourly_rate <= 0:
                errors['hourly_rate'] = "Hourly calculation type requires a positive hourly rate."
            if self.base_salary and self.base_salary > 0:
                errors['base_salary'] = "Hourly calculation type should not have base salary."

        # Project calculation requires dates and either base_salary or hourly_rate
        elif self.calculation_type == "project":
            if not self.project_start_date:
                errors['project_start_date'] = "Project calculation type requires start date."
            if not self.project_end_date:
                errors['project_end_date'] = "Project calculation type requires end date."
            if self.project_start_date and self.project_end_date and self.project_start_date > self.project_end_date:
                errors['project_end_date'] = "Project end date must be after start date."
            if not ((self.base_salary and self.base_salary > 0) or (self.hourly_rate and self.hourly_rate > 0)):
                errors['base_salary'] = "Project calculation type requires either base salary or hourly rate."

        # Check for conflicting fields (both base_salary and hourly_rate positive)
        if (self.base_salary and self.base_salary > 0) and (self.hourly_rate and self.hourly_rate > 0):
            errors['__all__'] = "Cannot have both base salary and hourly rate positive."

        # Check for zero values on active salaries (context-specific)
        if self.is_active:
            # For monthly salaries, base_salary must be positive
            if self.calculation_type == "monthly" and self.base_salary is not None and self.base_salary == 0:
                errors['base_salary'] = "Active monthly salary cannot have zero base salary."
            # For hourly salaries, hourly_rate must be positive
            if self.calculation_type == "hourly" and self.hourly_rate is not None and self.hourly_rate == 0:
                errors['hourly_rate'] = "Active hourly salary cannot have zero hourly rate."
            # For project salaries, either base_salary or hourly_rate must be positive
            if self.calculation_type == "project":
                if (self.base_salary is None or self.base_salary == 0) and (self.hourly_rate is None or self.hourly_rate == 0):
                    errors['base_salary'] = "Active project salary must have either positive base salary or hourly rate."

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Salary {self.employee.get_full_name()} ({self.get_calculation_type_display()})"

    def save(self, *args, **kwargs):
        """
        В тестах есть вызовы save(validate=False) — при этом тип расчёта
        (например, 'project') не должен переписываться и валидация не запускается.
        """
        from django.conf import settings

        validate = kwargs.pop("validate", True)
        skip_validation = kwargs.pop("skip_validation", False)
        
        # Track if this is a brand new record
        is_new_record = not self.pk

        # Handle active salary constraint: only one active salary per employee
        if self.is_active:
            # Deactivate all other active salaries for this employee
            Salary.objects.filter(employee=self.employee, is_active=True).exclude(
                pk=self.pk
            ).update(is_active=False)

        # Only auto-set calculation type for brand new records and when validating
        if validate and not skip_validation and is_new_record:
            employment_type_mapping = {
                "hourly": "hourly",
                "full_time": "monthly",
                "part_time": "monthly",
                "contract": "monthly",
            }

            # Only auto-convert in specific scenarios
            expected_calc_type = employment_type_mapping.get(
                self.employee.employment_type, "hourly"
            )

            should_convert = False
            new_calculation_type = None

            # Scenario 1: Project payroll disabled and calculation_type is 'project' -> convert to expected type
            if self.calculation_type == "project" and not settings.FEATURE_FLAGS.get(
                "ENABLE_PROJECT_PAYROLL", False
            ):
                should_convert = True
                new_calculation_type = expected_calc_type

            # Scenario 2: Using model default calculation_type ('hourly') but have fields for a different type
            # This handles cases where objects are created with base_salary but no explicit calculation_type
            elif (
                self.calculation_type == "hourly"  # Using default
                and self.base_salary
                and not self.hourly_rate  # Have monthly-style fields
                and expected_calc_type == "monthly"
            ):  # Employee should be monthly
                should_convert = True
                new_calculation_type = "monthly"

            if should_convert:
                old_calculation_type = self.calculation_type
                self.calculation_type = new_calculation_type

                # Adjust fields to match the new calculation type
                if (
                    new_calculation_type == "hourly"
                    and self.base_salary
                    and not self.hourly_rate
                ):
                    # Convert base_salary to hourly_rate (rough estimate: base_salary / 180 hours per month)
                    self.hourly_rate = self.base_salary / Decimal("180")
                    self.base_salary = None
                elif (
                    new_calculation_type == "monthly"
                    and self.hourly_rate
                    and not self.base_salary
                ):
                    # Convert hourly_rate to base_salary (rough estimate: hourly_rate * 180 hours per month)
                    self.base_salary = self.hourly_rate * Decimal("180")
                    self.hourly_rate = None

            elif self.calculation_type not in ["hourly", "monthly", "project"]:
                # Set calculation type based on employee's employment type only if invalid
                self.calculation_type = employment_type_mapping.get(
                    self.employee.employment_type, "hourly"
                )

        # Sync related fields for test compatibility - только при валидации
        if validate and not skip_validation:
            if self.calculation_type == "hourly" and self.monthly_hourly and not self.hourly_rate:
                self.hourly_rate = self.monthly_hourly
            elif self.calculation_type == "hourly" and self.hourly_rate and not self.monthly_hourly:
                self.monthly_hourly = self.hourly_rate

        # Validate salary fields based on calculation_type
        # Skip validation if explicitly requested (for test compatibility)
        if validate and not skip_validation:
            # For existing project types when feature is disabled, skip validation to allow updates
            if (
                not is_new_record
                and self.calculation_type == "project"
                and not settings.FEATURE_FLAGS.get("ENABLE_PROJECT_PAYROLL", False)
            ):
                pass  # Skip validation for existing project salaries
            else:
                self.clean()
                self.validate_constraints()
        return super().save(*args, **kwargs)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["employee"],
                condition=models.Q(is_active=True),
                name="unique_active_salary_per_employee",
            )
        ]


class CompensatoryDay(models.Model):
    """Compensatory days for working on Shabbat or holidays"""

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="compensatory_days"
    )
    date_earned = models.DateField()
    reason = models.CharField(
        max_length=50,
        choices=[("shabbat", "Work on Shabbat"), ("holiday", "Work on Holiday")],
    )
    date_used = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        status = "Used" if self.date_used else "Not used"
        return f"{self.employee} - {self.get_reason_display()} ({status})"

    class Meta:
        verbose_name = "Compensatory Day"
        verbose_name_plural = "Compensatory Days"
        ordering = ["-date_earned"]


class DailyPayrollCalculation(models.Model):
    """Store payroll calculations for individual shifts or daily summaries"""

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="daily_payroll_calculations"
    )
    work_date = models.DateField(db_index=True)

    # Link to specific WorkLog for shift-based calculations
    worklog = models.ForeignKey(
        "worktime.WorkLog",
        on_delete=models.CASCADE,
        related_name="payroll_calculations",
        null=True,
        blank=True,
        help_text="Link to specific shift (WorkLog). Null for daily summary records.",
    )

    # Hours worked
    regular_hours = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0")
    )
    overtime_hours_1 = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        help_text="First 2 overtime hours at 125%",
    )
    overtime_hours_2 = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Additional overtime hours at 150%",
    )
    # Sabbath-specific hours
    sabbath_regular_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Regular hours worked during Sabbath at 150%",
    )
    # Sabbath-specific overtime hours (higher rates: 175% and 200%)
    sabbath_overtime_hours_1 = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        help_text="First 2 sabbath overtime hours at 175%",
    )
    sabbath_overtime_hours_2 = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Additional sabbath overtime hours at 200%",
    )
    night_hours = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0")
    )

    # Payment amounts - renamed to clarify relationship to base_pay and bonus_pay
    base_regular_pay = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"),
        help_text="Regular pay component of base_pay"
    )
    bonus_overtime_pay_1 = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"),
        help_text="First 2 overtime hours at 125% - component of bonus_pay"
    )
    bonus_overtime_pay_2 = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"),
        help_text="Additional overtime hours at 150% - component of bonus_pay"
    )
    # Sabbath-specific overtime payments
    bonus_sabbath_overtime_pay_1 = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Payment for first 2 sabbath overtime hours at 175% - component of bonus_pay",
    )
    bonus_sabbath_overtime_pay_2 = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Payment for additional sabbath overtime hours at 200% - component of bonus_pay",
    )
    # New unified payment structure
    base_pay = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Base payment: hours × hourly_rate for all employee types",
    )
    bonus_pay = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text="All bonus payments: overtime, sabbath, holiday premiums",
    )

    # Legacy fields - keep for backward compatibility
    total_pay = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"),
        help_text="DEPRECATED - use total_gross_pay instead"
    )
    total_gross_pay = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Full gross payment including base salary for monthly employees",
    )
    total_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Total salary amount for this calculation period",
    )

    # Special circumstances
    is_holiday = models.BooleanField(default=False)
    is_sabbath = models.BooleanField(default=False)
    is_night_shift = models.BooleanField(default=False)
    holiday_name = models.CharField(max_length=100, blank=True, null=True)

    # Calculation details
    calculation_details = models.JSONField(
        default=dict, blank=True, help_text="Detailed breakdown of calculation"
    )

    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    calculated_by_service = models.CharField(
        max_length=50, default="PayrollService"
    )
    proportional_monthly = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        help_text="Proportional monthly salary portion for this calculation"
    )

    class Meta:
        verbose_name = "Daily Payroll Calculation"
        verbose_name_plural = "Daily Payroll Calculations"
        # Removed unique_together to allow multiple shifts per day
        ordering = ["-work_date", "worklog_id"]
        indexes = [
            models.Index(fields=["employee", "work_date"]),
            models.Index(fields=["work_date"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["worklog"]),  # Index for shift-based lookups
        ]

    def __str__(self):
        return f"{self.employee.get_full_name()} - {self.work_date} - ₪{self.total_gross_pay}"

    @property
    def total_hours(self):
        """Calculate total hours worked"""
        return (
            self.regular_hours
            + self.overtime_hours_1
            + self.overtime_hours_2
            + self.sabbath_regular_hours
            + self.sabbath_overtime_hours_1
            + self.sabbath_overtime_hours_2
        )


class MonthlyPayrollSummary(models.Model):
    """Store monthly payroll summaries for quick access"""

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="monthly_payroll_summaries"
    )
    year = models.IntegerField()
    month = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)]
    )

    # Summary data
    total_hours = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0")
    )
    regular_hours = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0")
    )
    overtime_hours = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0")
    )
    holiday_hours = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0")
    )
    sabbath_hours = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0")
    )

    # Payment totals
    base_pay = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    overtime_pay = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    holiday_pay = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    sabbath_pay = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    total_gross_pay = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    total_salary = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        help_text="Total salary amount for the month"
    )
    proportional_monthly = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        help_text="Proportional monthly salary based on hours worked"
    )
    total_bonuses_monthly = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0"),
        help_text="Total bonus payments for monthly employees (overtime, sabbath, etc.)"
    )

    # Additional info
    worked_days = models.IntegerField(default=0)
    compensatory_days_earned = models.IntegerField(default=0)

    # Calculation metadata
    calculation_date = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)
    calculation_details = models.JSONField(
        default=dict, blank=True, help_text="Additional calculation metadata"
    )

    class Meta:
        verbose_name = "Monthly Payroll Summary"
        verbose_name_plural = "Monthly Payroll Summaries"
        unique_together = ["employee", "year", "month"]
        ordering = ["-year", "-month"]
        indexes = [
            models.Index(fields=["employee", "year", "month"]),
            models.Index(fields=["year", "month"]),
            models.Index(fields=["calculation_date"]),
        ]

    def __str__(self):
        return f"{self.employee.get_full_name()} - {self.year}/{self.month:02d} - ₪{self.total_gross_pay}"

    @property
    def period_display(self):
        """Return formatted period display"""
        return f"{calendar.month_name[self.month]} {self.year}"
