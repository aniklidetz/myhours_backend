from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand

from payroll.models import DailyPayrollCalculation
from payroll.services import EnhancedPayrollCalculationService
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
                old_ot1_pay = calc.overtime_pay_1
                old_ot2_pay = calc.overtime_pay_2

                # Recalculate using the service
                service = EnhancedPayrollCalculationService(
                    calc.employee,
                    calc.work_date.year,
                    calc.work_date.month,
                    fast_mode=True,  # Skip API calls for speed
                )

                # Calculate new values
                result = service.calculate_daily_bonuses_monthly(
                    worklog, save_to_db=False
                )

                # Check if there's a significant change
                new_total_pay = result["total_pay"]
                new_total_gross = result["total_gross_pay"]

                if abs(new_total_pay - old_total_pay) > Decimal("0.01"):
                    if not options["dry_run"]:
                        # Update the record
                        calc.total_pay = new_total_pay
                        calc.total_gross_pay = new_total_gross

                        # Update overtime pay breakdown if available
                        if "breakdown" in result:
                            breakdown = result["breakdown"]
                            calc.overtime_pay_1 = breakdown.get(
                                "overtime_pay_1", Decimal("0")
                            )
                            calc.overtime_pay_2 = breakdown.get(
                                "overtime_pay_2", Decimal("0")
                            )

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
