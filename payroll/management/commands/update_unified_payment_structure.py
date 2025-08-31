from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand

from payroll.models import DailyPayrollCalculation
from payroll.services import EnhancedPayrollCalculationService
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
                calculation_type = calc.employee.salary_info.calculation_type

                if calculation_type == "monthly":
                    # Use monthly employee logic
                    service = EnhancedPayrollCalculationService(
                        calc.employee,
                        calc.work_date.year,
                        calc.work_date.month,
                        fast_mode=True,  # Skip API calls for speed
                    )
                    result = service.calculate_daily_bonuses_monthly(
                        worklog, save_to_db=False
                    )

                elif calculation_type == "hourly":
                    # For hourly employees: implement similar unified logic
                    # For now, calculate manually
                    hours_worked = worklog.get_total_hours()
                    hourly_rate = calc.employee.salary_info.hourly_rate or Decimal("0")

                    # NEW UNIFIED LOGIC for hourly employees:
                    # base_pay = hours × hourly_rate
                    # bonus_pay = overtime premiums + special day bonuses
                    # total_pay = base_pay + bonus_pay

                    new_base_pay = hours_worked * hourly_rate

                    # For now, use existing total_pay as total and calculate bonus_pay
                    new_total_pay = calc.total_pay if calc.total_pay else new_base_pay
                    new_bonus_pay = max(Decimal("0"), new_total_pay - new_base_pay)

                    result = {
                        "base_pay": new_base_pay,
                        "bonus_pay": new_bonus_pay,
                        "total_pay": new_total_pay,
                        "total_gross_pay": new_total_pay,
                    }
                else:
                    self.stdout.write(
                        f"⚠️  Unsupported calculation type '{calculation_type}' for {calc.employee.get_full_name()}"
                    )
                    continue

                # Extract new values
                new_base_pay = result.get("base_pay", Decimal("0"))
                new_bonus_pay = result.get("bonus_pay", Decimal("0"))
                new_total_gross = result.get(
                    "total_gross_pay", result.get("total_pay", Decimal("0"))
                )

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
