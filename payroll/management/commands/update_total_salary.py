"""
Alias for update_total_gross_pay command with updated field names.
This command updates total_salary field instead of the deprecated total_gross_pay.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand

from payroll.models import DailyPayrollCalculation


class Command(BaseCommand):
    help = "Update total_salary for existing daily payroll calculations"

    def add_arguments(self, parser):
        parser.add_argument(
            "--month", type=str, help="Month in YYYY-MM format or number (1-12)"
        )
        parser.add_argument("--year", type=int, help="Year, e.g. 2025")

    def handle(self, *args, **options):
        self.stdout.write("Updating total_salary for existing daily calculations...")

        # Parse month parameter (can be YYYY-MM format or just month number)
        year = options.get("year")
        month_param = options.get("month")

        filters = {}

        if month_param:
            if "-" in str(month_param):
                # YYYY-MM format
                year_str, month_str = str(month_param).split("-")
                filters["work_date__year"] = int(year_str)
                filters["work_date__month"] = int(month_str)
            else:
                # Month number
                filters["work_date__month"] = int(month_param)
                if year:
                    filters["work_date__year"] = year
        elif year:
            filters["work_date__year"] = year

        # Find records where total_salary needs updating
        calculations = DailyPayrollCalculation.objects.filter(**filters)

        if not calculations.exists():
            self.stdout.write("No payroll calculations found to update.")
            return

        updated_count = 0

        for calc in calculations:
            # Calculate total_salary as safe aggregation of all payment components
            components = [
                "base_regular_pay",
                "bonus_overtime_pay_1",
                "bonus_overtime_pay_2",
                "bonus_sabbath_overtime_pay_1",
                "bonus_sabbath_overtime_pay_2",
                "bonus_sabbath_pay",
                "bonus_holiday_pay",
                "bonus_night_pay_1",
                "bonus_night_pay_2",
                "base_pay",
            ]
            new_total = sum(
                (getattr(calc, f, None) or Decimal("0")) for f in components
            )

            if calc.total_salary != new_total:
                calc.total_salary = new_total
                calc.save(update_fields=["total_salary", "updated_at"])
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully updated {updated_count} payroll calculations"
            )
        )
