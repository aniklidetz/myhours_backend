from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand

from payroll.models import DailyPayrollCalculation
from payroll.services.payroll_service import PayrollService
from payroll.services.contracts import CalculationContext
from payroll.services.enums import CalculationStrategy, EmployeeType
from users.models import Employee
from worktime.models import WorkLog


class Command(BaseCommand):
    help = "Recalculate all daily payroll calculations for monthly employees"

    def add_arguments(self, parser):
        parser.add_argument("--month", type=int, help="Month number (1-12)")
        parser.add_argument("--year", type=int, help="Year, e.g. 2025")
        parser.add_argument(
            "--employee-id", type=int, help="Recalculate only for specific employee ID"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without saving",
        )

    def handle(self, *args, **options):
        self.stdout.write("Recalculating daily payroll for monthly employees...")

        # Find all daily calculations for monthly employees
        query = (
            DailyPayrollCalculation.objects.filter(
                employee__salaries__is_active=True,
                employee__salaries__calculation_type="monthly",
            )
            .select_related("employee")
            .prefetch_related("employee__salaries")
        )

        # Filter by month and year if provided
        if options.get("month") and options.get("year"):
            query = query.filter(
                work_date__month=options["month"], work_date__year=options["year"]
            )
        elif options.get("month") or options.get("year"):
            self.stdout.write(
                self.style.WARNING("Both --month and --year must be provided together")
            )

        if options.get("employee_id"):
            query = query.filter(employee_id=options["employee_id"])

        calculations = query.order_by("employee", "work_date")

        self.stdout.write(
            f"Found {calculations.count()} daily calculations for monthly employees"
        )

        updated_count = 0
        errors = 0

        for calc in calculations:
            try:
                # Find the corresponding worklog
                worklog = WorkLog.objects.filter(
                    employee=calc.employee, check_in__date=calc.work_date
                ).first()

                if not worklog:
                    self.stdout.write(
                        f"⚠️  No worklog found for {calc.employee.get_full_name()} on {calc.work_date}"
                    )
                    continue

                # Store old values for comparison
                old_total_pay = calc.total_pay
                old_total_gross = calc.total_gross_pay
                old_bonus_ot1_pay = getattr(calc, 'bonus_overtime_pay_1', Decimal('0'))
                old_bonus_ot2_pay = getattr(calc, 'bonus_overtime_pay_2', Decimal('0'))

                # Determine employee type
                employee_type = EmployeeType.HOURLY if calc.employee.salaries.filter(
                    is_active=True, calculation_type='hourly'
                ).exists() else EmployeeType.MONTHLY

                # Recalculate using new PayrollService
                service = PayrollService()
                context = CalculationContext(
                    employee_id=calc.employee.id,
                    year=calc.work_date.year,
                    month=calc.work_date.month,
                    user_id=1,  # System user for management commands
                    employee_type=employee_type,
                    force_recalculate=True,
                    fast_mode=True  # Skip external API calls for speed
                )

                # Calculate new values
                result = service.calculate(context, CalculationStrategy.ENHANCED)

                # Check if there's a significant change
                # Note: New PayrollService returns total_salary instead of total_pay
                new_total_salary = Decimal(str(result.get("total_salary", 0)))
                new_total_gross = new_total_salary  # For consistency with old structure

                if abs(new_total_salary - old_total_gross) > Decimal("0.01"):
                    if not options["dry_run"]:
                        # Update the record with new unified structure
                        calc.total_pay = new_total_salary  # Legacy field
                        calc.total_gross_pay = new_total_salary  # Main field
                        
                        # Update base_pay and bonus_pay from calculation result
                        # Note: New service calculates these automatically
                        # We approximate breakdown for compatibility
                        regular_hours = Decimal(str(result.get("regular_hours", 0)))
                        overtime_hours = Decimal(str(result.get("overtime_hours", 0)))
                        
                        if calc.employee.salaries.filter(is_active=True).first():
                            salary = calc.employee.salaries.filter(is_active=True).first()
                            if salary.calculation_type == 'hourly' and salary.hourly_rate:
                                hourly_rate = salary.hourly_rate
                                calc.base_pay = regular_hours * hourly_rate
                                calc.bonus_pay = new_total_salary - calc.base_pay
                            else:
                                # For monthly employees, split based on hours proportion
                                total_hours = regular_hours + overtime_hours
                                if total_hours > 0:
                                    calc.base_pay = new_total_salary * (regular_hours / total_hours)
                                    calc.bonus_pay = new_total_salary * (overtime_hours / total_hours)
                                else:
                                    calc.base_pay = new_total_salary
                                    calc.bonus_pay = Decimal('0')

                        # Ensure updated_at is updated
                        import time

                        from django.utils import timezone

                        time.sleep(0.001)  # Small delay to ensure timestamp difference
                        calc.updated_at = timezone.now()
                        calc.save()

                    self.stdout.write(
                        f"{'[DRY RUN] ' if options['dry_run'] else ''}Updated {calc.employee.get_full_name()} - {calc.work_date}: "
                        f"₪{old_total_pay:.2f} → ₪{new_total_pay:.2f} "
                        f"(gross: ₪{old_total_gross:.2f} → ₪{new_total_gross:.2f})"
                    )
                    updated_count += 1
                else:
                    self.stdout.write(
                        f"✓ No change needed for {calc.employee.get_full_name()} - {calc.work_date}"
                    )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"Error recalculating {calc.employee.get_full_name()} - {calc.work_date}: {e}"
                    )
                )
                errors += 1
                continue

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN: Would update {updated_count} records, {errors} errors"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully recalculated {updated_count} daily calculations, {errors} errors"
                )
            )
