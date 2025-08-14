from django.core.management.base import BaseCommand
from django.db import transaction

from payroll.models import DailyPayrollCalculation
from worktime.models import WorkLog


class Command(BaseCommand):
    help = (
        "Clean up orphaned payroll calculations (calculations without active WorkLogs)"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        self.stdout.write("🧹 Orphaned Payroll Cleanup")
        self.stdout.write("=" * 40)

        # Get all payroll calculations
        all_calcs = DailyPayrollCalculation.objects.all()
        orphaned_calcs = []

        self.stdout.write(f"📊 Scanning {all_calcs.count()} payroll calculations...")

        for calc in all_calcs:
            is_orphaned = False

            if calc.worklog:
                # Shift-based calculation: check if the specific WorkLog still exists and is active
                if calc.worklog.is_deleted:
                    is_orphaned = True
            else:
                # Legacy daily calculation: check if there are any active WorkLogs for this employee/date
                active_worklogs = WorkLog.objects.filter(
                    employee=calc.employee,
                    check_in__date=calc.work_date,
                    is_deleted=False,
                ).exists()
                if not active_worklogs:
                    is_orphaned = True

            if is_orphaned:
                orphaned_calcs.append(
                    {
                        "employee": calc.employee.get_full_name(),
                        "employee_id": calc.employee.id,
                        "date": calc.work_date,
                        "amount": calc.total_gross_pay,
                        "hours": calc.total_hours,
                        "calc": calc,
                    }
                )

        if not orphaned_calcs:
            self.stdout.write(
                self.style.SUCCESS(
                    "✅ No orphaned calculations found - system is clean!"
                )
            )
            return

        self.stdout.write(
            f"❌ Found {len(orphaned_calcs)} orphaned payroll calculations:"
        )

        # Group by employee for better display
        by_employee = {}
        for orphan in orphaned_calcs:
            emp_name = orphan["employee"]
            if emp_name not in by_employee:
                by_employee[emp_name] = []
            by_employee[emp_name].append(orphan)

        total_amount = 0
        for emp_name, calcs in by_employee.items():
            emp_total = sum(float(calc["amount"]) for calc in calcs)
            total_amount += emp_total
            self.stdout.write(
                f"  📝 {emp_name}: {len(calcs)} calculations (₪{emp_total:.2f})"
            )

            if dry_run:
                for calc in calcs[:3]:  # Show first 3 as example
                    self.stdout.write(
                        f"    - {calc['date']}: ₪{calc['amount']} ({calc['hours']}h)"
                    )
                if len(calcs) > 3:
                    self.stdout.write(f"    ... and {len(calcs) - 3} more")

        self.stdout.write(
            f"💰 Total amount in orphaned calculations: ₪{total_amount:.2f}"
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN: Would delete {len(orphaned_calcs)} orphaned calculations"
                )
            )
        else:
            # Confirm cleanup
            self.stdout.write(
                "\n🚨 This will permanently delete the above calculations."
            )

            with transaction.atomic():
                deleted_count = 0
                for orphan in orphaned_calcs:
                    orphan["calc"].delete()
                    deleted_count += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"✅ Deleted {deleted_count} orphaned calculations (₪{total_amount:.2f})"
                    )
                )

            self.stdout.write("✅ Cleanup completed successfully!")
