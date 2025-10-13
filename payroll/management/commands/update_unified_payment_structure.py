from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand

from payroll.models import DailyPayrollCalculation
from payroll.services.contracts import CalculationContext
from payroll.services.enums import CalculationStrategy, EmployeeType
from payroll.services.payroll_service import PayrollService
from users.models import Employee
from worktime.models import WorkLog


class Command(BaseCommand):
    help = "Update all daily payroll calculations with new unified payment structure (base_pay + bonus_pay)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--employee-id", type=int, help="Recalculate only for specific employee ID"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without saving",
        )
        parser.add_argument(
            "--calculation-type",
            choices=["monthly", "hourly", "all"],
            default="all",
            help="Recalculate only specific employee types",
        )

    def handle(self, *args, **options):
        self.stdout.write(
            "Updating daily payroll calculations with unified payment structure..."
        )

        # Build query filter
        query_filter = {}
        if options["employee_id"]:
            query_filter["employee_id"] = options["employee_id"]

        if options["calculation_type"] != "all":
            query_filter["employee__salaries__calculation_type"] = options[
                "calculation_type"
            ]
            query_filter["employee__salaries__is_active"] = True

        # Find all daily calculations
        calculations = (
            DailyPayrollCalculation.objects.filter(**query_filter)
            .select_related("employee")
            .prefetch_related("employee__salaries")
            .order_by("employee", "work_date")
        )

        self.stdout.write(f"Found {calculations.count()} daily calculations to update")

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
                old_base_pay = calc.base_pay
                old_bonus_pay = calc.bonus_pay
                old_total_gross = calc.total_gross_pay

                # Calculate new values using unified logic
                # Get active salary to determine employee type
                active_salary = calc.employee.salaries.filter(is_active=True).first()
                if not active_salary:
                    self.stdout.write(
                        self.style.ERROR(
                            f"No active salary found for {calc.employee.get_full_name()}"
                        )
                    )
                    continue

                calculation_type = active_salary.calculation_type
                employee_type = (
                    EmployeeType.HOURLY
                    if calculation_type == "hourly"
                    else EmployeeType.MONTHLY
                )

                # Use new PayrollService
                service = PayrollService()
                context = CalculationContext(
                    employee_id=calc.employee.id,
                    year=calc.work_date.year,
                    month=calc.work_date.month,
                    user_id=1,  # System user for management commands
                    employee_type=employee_type,
                    force_recalculate=True,
                    fast_mode=False,  # Enable database persistence
                )
                result = service.calculate(context, CalculationStrategy.ENHANCED)

                # Extract unified values from result
                total_salary = Decimal(str(result.get("total_salary", 0)))

                # Calculate base_pay and bonus_pay from the result
                regular_hours = Decimal(str(result.get("regular_hours", 0)))
                total_hours = regular_hours + Decimal(
                    str(result.get("overtime_hours", 0))
                )

                if calculation_type == "hourly" and active_salary.hourly_rate:
                    new_base_pay = regular_hours * active_salary.hourly_rate
                    new_bonus_pay = total_salary - new_base_pay
                else:
                    # For monthly employees, use proportional split
                    if total_hours > 0:
                        new_base_pay = total_salary * (regular_hours / total_hours)
                        new_bonus_pay = total_salary - new_base_pay
                    else:
                        new_base_pay = total_salary
                        new_bonus_pay = Decimal("0")

                unified_result = {
                    "base_pay": new_base_pay,
                    "bonus_pay": new_bonus_pay,
                    "total_pay": total_salary,
                    "total_gross_pay": total_salary,
                }

                # Check if values changed significantly
                new_base_pay = unified_result["base_pay"]
                new_bonus_pay = unified_result["bonus_pay"]
                new_total_gross = unified_result["total_gross_pay"]

                # Check if there's a significant change
                base_change = abs(new_base_pay - old_base_pay) > Decimal("0.01")
                bonus_change = abs(new_bonus_pay - old_bonus_pay) > Decimal("0.01")

                if base_change or bonus_change:
                    if not options["dry_run"]:
                        # Update the record with new unified structure
                        calc.base_pay = new_base_pay
                        calc.bonus_pay = new_bonus_pay
                        calc.total_gross_pay = new_total_gross

                        # Keep legacy fields for backward compatibility
                        if "total_pay" in result:
                            calc.total_pay = result["total_pay"]

                        calc.save()

                    self.stdout.write(
                        f"{'[DRY RUN] ' if options['dry_run'] else ''}Updated {calc.employee.get_full_name()} - {calc.work_date} ({calculation_type}): "
                        f"base ₪{old_base_pay:.2f} → ₪{new_base_pay:.2f}, "
                        f"bonus ₪{old_bonus_pay:.2f} → ₪{new_bonus_pay:.2f}, "
                        f"total ₪{old_total_gross:.2f} → ₪{new_total_gross:.2f}"
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
                    f"Successfully updated {updated_count} daily calculations with unified payment structure, {errors} errors"
                )
            )
