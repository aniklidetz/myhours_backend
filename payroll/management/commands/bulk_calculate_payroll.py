"""
Django management command for bulk payroll calculation.

Usage:
    # Calculate for all active employees in October 2025
    python manage.py bulk_calculate_payroll --year 2025 --month 10

    # Calculate for specific employees
    python manage.py bulk_calculate_payroll --year 2025 --month 10 --employees 1,2,3

    # Calculate without saving to database (dry run)
    python manage.py bulk_calculate_payroll --year 2025 --month 10 --dry-run

    # Calculate without cache
    python manage.py bulk_calculate_payroll --year 2025 --month 10 --no-cache

    # Calculate without parallel processing
    python manage.py bulk_calculate_payroll --year 2025 --month 10 --no-parallel

    # Export statistics
    python manage.py bulk_calculate_payroll --year 2025 --month 10 --export-stats /tmp/stats.json
"""

import logging
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from payroll.services.bulk import BulkEnhancedPayrollService
from payroll.services.enums import CalculationStrategy
from users.models import Employee

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Calculate payroll for multiple employees using bulk operations"

    def add_arguments(self, parser):
        # Required arguments
        parser.add_argument(
            "--year",
            type=int,
            required=True,
            help="Year for payroll calculation (e.g., 2025)",
        )

        parser.add_argument(
            "--month",
            type=int,
            required=True,
            help="Month for payroll calculation (1-12)",
        )

        # Optional arguments
        parser.add_argument(
            "--employees",
            type=str,
            help='Comma-separated list of employee IDs (e.g., "1,2,3"). If not provided, all active employees will be processed.',
        )

        parser.add_argument(
            "--strategy",
            type=str,
            default="enhanced",
            choices=["enhanced", "critical_points"],
            help="Calculation strategy to use (default: enhanced)",
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run calculations without saving to database",
        )

        parser.add_argument(
            "--no-cache", action="store_true", help="Disable Redis cache"
        )

        parser.add_argument(
            "--no-parallel", action="store_true", help="Disable parallel processing"
        )

        parser.add_argument(
            "--max-workers",
            type=int,
            help="Maximum number of parallel workers (default: auto-detect)",
        )

        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Batch size for database operations (default: 1000)",
        )

        parser.add_argument(
            "--no-progress", action="store_true", help="Disable progress bar"
        )

        parser.add_argument(
            "--export-stats", type=str, help="Path to export statistics JSON file"
        )

        parser.add_argument(
            "--invalidate-cache",
            action="store_true",
            help="Invalidate cache before calculation",
        )

    def handle(self, *args, **options):
        year = options["year"]
        month = options["month"]

        # Validate month
        if not 1 <= month <= 12:
            raise CommandError("Month must be between 1 and 12")

        # Get employee IDs
        if options["employees"]:
            # Parse comma-separated IDs
            try:
                employee_ids = [
                    int(emp_id.strip()) for emp_id in options["employees"].split(",")
                ]
            except ValueError:
                raise CommandError(
                    'Invalid employee IDs format. Use comma-separated integers (e.g., "1,2,3")'
                )

            # Validate employees exist
            existing_ids = set(
                Employee.objects.filter(id__in=employee_ids).values_list(
                    "id", flat=True
                )
            )
            invalid_ids = set(employee_ids) - existing_ids

            if invalid_ids:
                raise CommandError(f"Invalid employee IDs: {invalid_ids}")

        else:
            # Get all active employees
            employee_ids = list(
                Employee.objects.filter(is_active=True).values_list("id", flat=True)
            )

            if not employee_ids:
                self.stdout.write(self.style.WARNING("No active employees found"))
                return

        # Parse strategy
        strategy_map = {
            "enhanced": CalculationStrategy.ENHANCED,
            "critical_points": CalculationStrategy.CRITICAL_POINTS,
        }
        strategy = strategy_map[options["strategy"]]

        # Parse export path
        export_stats_path = None
        if options["export_stats"]:
            export_stats_path = Path(options["export_stats"])

        # Display configuration
        self.stdout.write(self.style.SUCCESS("Bulk Payroll Calculation"))
        self.stdout.write(f"Period: {year}-{month:02d}")
        self.stdout.write(f"Employees: {len(employee_ids)}")
        self.stdout.write(f'Strategy: {options["strategy"]}')
        self.stdout.write(f'Dry run: {options["dry_run"]}')
        self.stdout.write(f'Cache: {"disabled" if options["no_cache"] else "enabled"}')
        self.stdout.write(
            f'Parallel: {"disabled" if options["no_parallel"] else "enabled"}'
        )

        if options["max_workers"]:
            self.stdout.write(f'Max workers: {options["max_workers"]}')

        self.stdout.write("")

        # Create service
        service = BulkEnhancedPayrollService(
            use_cache=not options["no_cache"],
            use_parallel=not options["no_parallel"],
            max_workers=options["max_workers"],
            batch_size=options["batch_size"],
            show_progress=not options["no_progress"],
        )

        # Invalidate cache if requested
        if options["invalidate_cache"] and not options["no_cache"]:
            self.stdout.write("Invalidating cache...")
            deleted_count = service.invalidate_cache(employee_ids, year, month)
            self.stdout.write(f"Invalidated {deleted_count} cache keys")
            self.stdout.write("")

        # Run calculation
        try:
            result = service.calculate_bulk(
                employee_ids=employee_ids,
                year=year,
                month=month,
                strategy=strategy,
                save_to_db=not options["dry_run"],
                export_stats_path=export_stats_path,
            )

            # Display results
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("=" * 60))
            self.stdout.write(self.style.SUCCESS("Calculation Complete"))
            self.stdout.write(self.style.SUCCESS("=" * 60))

            # Get detailed summary
            summary = result.get_detailed_report()

            self.stdout.write(f"Total employees: {summary.total_employees}")
            self.stdout.write(self.style.SUCCESS(f"Successful: {summary.successful}"))

            if summary.failed > 0:
                self.stdout.write(self.style.ERROR(f"Failed: {summary.failed}"))

            # Calculate performance metrics
            calculations_per_second = (
                result.total_count / result.duration_seconds
                if result.duration_seconds > 0
                else 0
            )

            self.stdout.write("")
            self.stdout.write("Performance:")
            self.stdout.write(f"  Duration: {summary.duration_seconds:.2f}s")
            self.stdout.write(f"  Calculations/sec: {calculations_per_second:.2f}")
            self.stdout.write(
                f"  Avg time/employee: {summary.avg_time_per_employee:.3f}s"
            )

            self.stdout.write("")
            self.stdout.write("Database:")
            self.stdout.write(f"  Total queries: {summary.db_queries}")

            if not options["no_cache"]:
                self.stdout.write("")
                self.stdout.write("Cache:")
                self.stdout.write(f"  Hit rate: {summary.cache_hit_rate:.1f}%")
                self.stdout.write(
                    f"  Cached results: {result.cached_count}/{result.total_count}"
                )

            # Display errors if any
            if result.errors:
                self.stdout.write("")
                self.stdout.write(self.style.ERROR(f"Errors ({len(result.errors)}):"))

                error_list = list(result.errors.values())[:10]  # Show first 10 errors
                for error in error_list:
                    self.stdout.write(
                        f"  Employee {error.employee_id}: {error.error_type} - {error.error_message}"
                    )

                if len(result.errors) > 10:
                    self.stdout.write(
                        f"  ... and {len(result.errors) - 10} more errors"
                    )

            # Display export info
            if export_stats_path:
                self.stdout.write("")
                self.stdout.write(f"Statistics exported to: {export_stats_path}")

            self.stdout.write(self.style.SUCCESS("=" * 60))

        except Exception as e:
            raise CommandError(f"Bulk calculation failed: {e}")
