"""
Management command to generate missing Daily Payroll Calculations and Monthly Payroll Summaries
"""

import logging
from datetime import date, datetime

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from payroll.models import DailyPayrollCalculation, MonthlyPayrollSummary
from payroll.services.payroll_service import PayrollService
from payroll.services.contracts import CalculationContext
from payroll.services.enums import CalculationStrategy, EmployeeType
from users.models import Employee
from worktime.models import WorkLog

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Generate missing Daily Payroll Calculations and Monthly Payroll Summaries"

    def add_arguments(self, parser):
        parser.add_argument(
            "--year", type=int, help="Year to process (e.g., 2025)", default=2025
        )
        parser.add_argument(
            "--month",
            type=int,
            help="Month to process (1-12). If not specified, processes all months with work logs",
        )
        parser.add_argument(
            "--employee-id", type=int, help="Process only specific employee ID"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be generated without actually creating records",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Recalculate even if records already exist",
        )

    def handle(self, *args, **options):
        year = options["year"]
        month = options.get("month")
        employee_id = options.get("employee_id")
        dry_run = options["dry_run"]
        force = options["force"]

        self.stdout.write(f"Generating missing payroll calculations for {year}")
        if month:
            self.stdout.write(f"   Month: {month}")
        if employee_id:
            self.stdout.write(f"   Employee ID: {employee_id}")
        if dry_run:
            self.stdout.write("   DRY RUN MODE - No changes will be saved")

        # Get employees with salary info (active salary)
        employees_query = Employee.objects.filter(salaries__is_active=True).distinct()
        if employee_id:
            employees_query = employees_query.filter(id=employee_id)

        employees = list(employees_query.prefetch_related("salaries"))
        self.stdout.write(f" Found {len(employees)} employees with salary info")

        # Get work dates that need processing
        work_logs_query = WorkLog.objects.filter(
            check_in__date__year=year, check_out__isnull=False
        )

        if month:
            work_logs_query = work_logs_query.filter(check_in__date__month=month)

        if employee_id:
            work_logs_query = work_logs_query.filter(employee_id=employee_id)

        # Get unique work dates
        work_dates = set()
        for log in work_logs_query.values_list("check_in__date", flat=True):
            work_dates.add(log)

        work_dates = sorted(work_dates)
        self.stdout.write(f" Found work logs on {len(work_dates)} unique dates")

        if not work_dates:
            self.stdout.write("ERROR: No work logs found for the specified criteria")
            return

        daily_created = 0
        daily_updated = 0
        monthly_created = 0
        monthly_updated = 0
        errors = 0

        # Process each employee and date combination
        for employee in employees:
            # Get work dates for this specific employee
            employee_work_dates = set()
            employee_logs = WorkLog.objects.filter(
                employee=employee, check_in__date__year=year, check_out__isnull=False
            )

            if month:
                employee_logs = employee_logs.filter(check_in__date__month=month)

            for log in employee_logs.values_list("check_in__date", flat=True):
                employee_work_dates.add(log)

            if not employee_work_dates:
                continue

            self.stdout.write(
                f"\n Processing {employee.get_full_name()} ({len(employee_work_dates)} work dates)"
            )

            # Process daily calculations
            for work_date in sorted(employee_work_dates):
                try:
                    # Check if daily calculation already exists
                    existing_daily = DailyPayrollCalculation.objects.filter(
                        employee=employee, work_date=work_date
                    ).first()

                    if existing_daily and not force:
                        self.stdout.write(f"  ✓ Daily calc exists for {work_date}")
                        continue

                    if not dry_run:
                        # Generate daily calculation using new PayrollService
                        active_salary = employee.salaries.filter(is_active=True).first()
                        if not active_salary:
                            self.stdout.write(f"  ERROR: No active salary for {employee.get_full_name()}")
                            errors += 1
                            continue
                        
                        employee_type = EmployeeType.HOURLY if active_salary.calculation_type == 'hourly' else EmployeeType.MONTHLY
                        
                        service = PayrollService()
                        context = CalculationContext(
                            employee_id=employee.id,
                            year=work_date.year,
                            month=work_date.month,
                            user_id=1,  # System user for commands
                            employee_type=employee_type,
                            force_recalculate=force
                            # Remove fast_mode=True to enable database persistence
                        )

                        work_logs = WorkLog.objects.filter(
                            employee=employee,
                            check_in__date=work_date,
                            check_out__isnull=False,
                        )

                        try:
                            # Calculate using new unified service
                            result = service.calculate(context, CalculationStrategy.ENHANCED)

                            if result and result.get('total_salary', 0) > 0:
                                # Create or update DailyPayrollCalculation record
                                daily_defaults = {
                                    'regular_hours': result.get('regular_hours', 0),
                                    'overtime_hours_1': result.get('overtime_hours', 0),
                                    'overtime_hours_2': result.get('overtime_hours_2', 0),
                                    'night_hours': result.get('night_hours', 0),
                                    'shabbat_hours': result.get('shabbat_hours', 0),
                                    'holiday_hours': result.get('holiday_hours', 0),
                                    # Don't set total_hours - it's a computed property
                                    'total_salary': result.get('total_salary', 0),
                                    'compensatory_days_earned': result.get('compensatory_days_earned', 0),
                                    'daily_calculation_breakdown': result.get('breakdown', {}),
                                    'updated_at': timezone.now(),
                                }

                                daily_calc, created = DailyPayrollCalculation.objects.update_or_create(
                                    employee=employee,
                                    work_date=work_date,
                                    defaults=daily_defaults
                                )

                                if created:
                                    daily_created += 1
                                    self.stdout.write(
                                        f"   Created daily calc for {work_date} - salary: {result['total_salary']}"
                                    )
                                else:
                                    daily_updated += 1
                                    self.stdout.write(
                                        f"   Updated daily calc for {work_date} - salary: {result['total_salary']}"
                                    )
                            else:
                                self.stdout.write(f"  ERROR: No result from calculation for {work_date}")
                                errors += 1
                                
                        except Exception as e:
                            self.stdout.write(
                                f"  ERROR: Error creating daily calc for {work_date}: {e}"
                            )
                            errors += 1
                    else:
                        action = "Update" if existing_daily else "Create"
                        self.stdout.write(f"  [{action}] Daily calc for {work_date}")

                except Exception as e:
                    self.stdout.write(f"  ERROR: Error processing {work_date}: {e}")
                    errors += 1

            # Process monthly summaries
            months_to_process = set()
            for work_date in employee_work_dates:
                months_to_process.add((work_date.year, work_date.month))

            for summary_year, summary_month in sorted(months_to_process):
                try:
                    existing_monthly = MonthlyPayrollSummary.objects.filter(
                        employee=employee, year=summary_year, month=summary_month
                    ).first()

                    if existing_monthly and not force:
                        self.stdout.write(
                            f"  ✓ Monthly summary exists for {summary_year}-{summary_month:02d}"
                        )
                        continue

                    if not dry_run:
                        # Generate monthly summary using new PayrollService
                        active_salary = employee.salaries.filter(is_active=True).first()
                        if not active_salary:
                            self.stdout.write(f"  ERROR: No active salary for {employee.get_full_name()}")
                            errors += 1
                            continue
                        
                        employee_type = EmployeeType.HOURLY if active_salary.calculation_type == 'hourly' else EmployeeType.MONTHLY
                        
                        service = PayrollService()
                        context = CalculationContext(
                            employee_id=employee.id,
                            year=summary_year,
                            month=summary_month,
                            user_id=1,  # System user for commands
                            employee_type=employee_type,
                            force_recalculate=force,
                            fast_mode=False
                        )
                        
                        try:
                            monthly_result = service.calculate(context, CalculationStrategy.ENHANCED)

                            if monthly_result and monthly_result.get('status') == 'success':
                                if existing_monthly:
                                    monthly_updated += 1
                                    self.stdout.write(
                                        f"   Updated monthly summary for {summary_year}-{summary_month:02d}"
                                    )
                                else:
                                    monthly_created += 1
                                    self.stdout.write(
                                        f"   Created monthly summary for {summary_year}-{summary_month:02d}"
                                    )
                            else:
                                self.stdout.write(f"  ERROR: No result from monthly calculation for {summary_year}-{summary_month:02d}")
                                errors += 1

                        except Exception as e:
                            self.stdout.write(
                                f"  ERROR: Error creating monthly summary for {summary_year}-{summary_month:02d}: {e}"
                            )
                            errors += 1
                    else:
                        action = "Update" if existing_monthly else "Create"
                        self.stdout.write(
                            f"  [{action}] Monthly summary for {summary_year}-{summary_month:02d}"
                        )

                except Exception as e:
                    self.stdout.write(
                        f"  ERROR: Error processing monthly summary for {summary_year}-{summary_month:02d}: {e}"
                    )
                    errors += 1

        # Summary
        self.stdout.write(f"\n Summary:")
        if dry_run:
            self.stdout.write("   DRY RUN - No changes were made")
        else:
            self.stdout.write(f"   Daily calculations created: {daily_created}")
            self.stdout.write(f"   Daily calculations updated: {daily_updated}")
            self.stdout.write(f"   Monthly summaries created: {monthly_created}")
            self.stdout.write(f"   Monthly summaries updated: {monthly_updated}")
            self.stdout.write(f"   Errors: {errors}")

        if not dry_run and (daily_created > 0 or monthly_created > 0):
            self.stdout.write("SUCCESS: Payroll generation completed successfully!")
        elif errors > 0:
            self.stdout.write("WARNING:  Completed with errors. Check the logs above.")
