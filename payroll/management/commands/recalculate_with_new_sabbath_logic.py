from datetime import date, datetime
from decimal import Decimal

from django.core.management.base import BaseCommand

from payroll.models import DailyPayrollCalculation
from payroll.services import EnhancedPayrollCalculationService
from users.models import Employee
from worktime.models import WorkLog


class Command(BaseCommand):
    help = "Recalculate payroll with updated Sabbath detection logic for shifts spanning into Sabbath"

    def add_arguments(self, parser):
        parser.add_argument(
            "--employee-id", type=int, help="Recalculate only for specific employee ID"
        )
        parser.add_argument(
            "--date", type=str, help="Recalculate only for specific date (YYYY-MM-DD)"
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without saving",
        )

    def handle(self, *args, **options):
        self.stdout.write("Recalculating payroll with new Sabbath detection logic...")

        # Build query filter
        query_filter = {}
        if options["employee_id"]:
            query_filter["employee_id"] = options["employee_id"]

        if options["date"]:
            try:
                work_date = datetime.strptime(options["date"], "%Y-%m-%d").date()
                query_filter["work_date"] = work_date
            except ValueError:
                self.stdout.write(
                    self.style.ERROR("Invalid date format. Use YYYY-MM-DD")
                )
                return

        # Find all daily calculations
        calculations = (
            DailyPayrollCalculation.objects.filter(**query_filter)
            .select_related("employee", "employee__salary_info")
            .order_by("employee", "work_date")
        )

        self.stdout.write(f"Found {calculations.count()} daily calculations to check")

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
                old_is_sabbath = calc.is_sabbath
                old_base_pay = calc.base_pay
                old_bonus_pay = calc.bonus_pay
                old_total_gross = calc.total_gross_pay

                # Calculate with new Sabbath logic
                calculation_type = calc.employee.salary_info.calculation_type

                if calculation_type == "monthly":
                    service = EnhancedPayrollCalculationService(
                        calc.employee,
                        calc.work_date.year,
                        calc.work_date.month,
                        fast_mode=True,
                    )
                    result = service.calculate_daily_bonuses_monthly(
                        worklog, save_to_db=False
                    )

                elif calculation_type == "hourly":
                    service = EnhancedPayrollCalculationService(
                        calc.employee,
                        calc.work_date.year,
                        calc.work_date.month,
                        fast_mode=True,
                    )
                    result = service.calculate_daily_pay_hourly(
                        worklog, save_to_db=False
                    )

                    # Convert hourly result to unified structure
                    if "breakdown" in result:
                        breakdown = result["breakdown"]
                        # Calculate base_pay and bonus_pay from breakdown
                        hours_worked = worklog.get_total_hours()
                        hourly_rate = calc.employee.salary_info.hourly_rate or Decimal(
                            "0"
                        )

                        # NEW UNIFIED LOGIC:
                        # base_pay = hours × hourly_rate
                        # bonus_pay = total_pay - base_pay
                        new_base_pay = hours_worked * hourly_rate
                        new_total_pay = result.get("total_pay", Decimal("0"))
                        new_bonus_pay = max(Decimal("0"), new_total_pay - new_base_pay)

                        # Update result for unified structure
                        result["base_pay"] = new_base_pay
                        result["bonus_pay"] = new_bonus_pay
                        result["total_gross_pay"] = new_total_pay
                else:
                    self.stdout.write(
                        f"⚠️  Unsupported calculation type '{calculation_type}' for {calc.employee.get_full_name()}"
                    )
                    continue

                # Extract new values
                new_is_sabbath = result.get("is_sabbath", False)
                new_base_pay = result.get("base_pay", Decimal("0"))
                new_bonus_pay = result.get("bonus_pay", Decimal("0"))
                new_total_gross = result.get("total_gross_pay", Decimal("0"))

                # Check if there's a change
                sabbath_change = new_is_sabbath != old_is_sabbath
                pay_change = abs(new_base_pay - old_base_pay) > Decimal("0.01") or abs(
                    new_bonus_pay - old_bonus_pay
                ) > Decimal("0.01")

                if sabbath_change or pay_change:
                    if not options["dry_run"]:
                        # Update the record
                        calc.is_sabbath = new_is_sabbath
                        calc.base_pay = new_base_pay
                        calc.bonus_pay = new_bonus_pay
                        calc.total_gross_pay = new_total_gross

                        # Update other fields from result
                        if "sabbath_type" in result:
                            calc.calculation_details = calc.calculation_details or {}
                            calc.calculation_details["sabbath_type"] = result[
                                "sabbath_type"
                            ]

                        calc.save()

                    change_desc = []
                    if sabbath_change:
                        change_desc.append(
                            f"Sabbath: {old_is_sabbath} → {new_is_sabbath}"
                        )
                    if pay_change:
                        change_desc.append(
                            f"base ₪{old_base_pay:.2f} → ₪{new_base_pay:.2f}"
                        )
                        change_desc.append(
                            f"bonus ₪{old_bonus_pay:.2f} → ₪{new_bonus_pay:.2f}"
                        )

                    self.stdout.write(
                        f"{'[DRY RUN] ' if options['dry_run'] else ''}Updated {calc.employee.get_full_name()} - {calc.work_date}: {', '.join(change_desc)}"
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
                    f"Successfully updated {updated_count} records with new Sabbath logic, {errors} errors"
                )
            )
