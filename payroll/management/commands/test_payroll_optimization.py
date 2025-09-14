"""
LEGACY - Django management command for testing the removed OptimizedPayrollService.

WARNING: This targets OptimizedPayrollService which has been REMOVED from the system.
    This command exists only for historical testing and will be deleted during legacy cleanup.

    SCHEDULED FOR REMOVAL: 2025-10-15

    PROBLEM: OptimizedPayrollService used incorrect calculation formula (hours × rate × 1.3).
    SOLUTION: Use PayrollService with CalculationStrategy.ENHANCED for all new implementations.

    DO NOT USE THIS COMMAND FOR NEW TESTING - it tests deprecated/incorrect logic.

Usage:
    python manage.py test_payroll_optimization
    python manage.py test_payroll_optimization --year 2025 --month 7
    python manage.py test_payroll_optimization --benchmark
"""

import logging
import time
import warnings

from django.core.management.base import BaseCommand
from django.utils import timezone

from payroll.optimized_service import optimized_payroll_service
from payroll.redis_cache_service import payroll_cache
from payroll.warnings import LegacyWarning
from users.models import Employee

logger = logging.getLogger(__name__)

# Ensure LegacyWarning is always visible
warnings.simplefilter("always", LegacyWarning)


class Command(BaseCommand):
    help = "LEGACY - targets OptimizedPayrollService with incorrect calculation formula (removed from system)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=timezone.now().year,
            help="Year for payroll calculation (default: current year)",
        )
        parser.add_argument(
            "--month",
            type=int,
            default=timezone.now().month,
            help="Month for payroll calculation (default: current month)",
        )
        parser.add_argument(
            "--benchmark",
            action="store_true",
            help="Run performance benchmark comparison",
        )
        parser.add_argument(
            "--employees",
            type=int,
            default=None,
            help="Limit to specific number of employees for testing",
        )

    def handle(self, *args, **options):
        # Issue programmatic warning that's always visible
        warnings.warn(
            "LEGACY: This command targets OptimizedPayrollService; use PayrollService with CalculationStrategy.ENHANCED.",
            LegacyWarning,
            stacklevel=2
        )

        self.stdout.write(
            self.style.ERROR("LEGACY WARNING: This command targets OptimizedPayrollService")
        )
        self.stdout.write(
            self.style.WARNING("   Problem: Uses incorrect calculation formula (hours × rate × 1.3)")
        )
        self.stdout.write(
            self.style.WARNING("   Solution: Use PayrollService with CalculationStrategy.ENHANCED instead")
        )
        self.stdout.write("")

        year = options["year"]
        month = options["month"]
        benchmark = options["benchmark"]
        employee_limit = options["employees"]

        self.stdout.write(
            self.style.SUCCESS(
                f" Testing Payroll Optimization for {year}-{month:02d}"
            )
        )

        # Get employees with salary info (active salary)
        employees = (
            Employee.objects.filter(salaries__is_active=True)
            .distinct()
            .prefetch_related("salaries")
        )

        if employee_limit:
            employees = employees[:employee_limit]

        employee_count = employees.count()

        if employee_count == 0:
            self.stdout.write(
                self.style.WARNING("WARNING: No employees with salary configuration found")
            )
            return

        self.stdout.write(f"Found {employee_count} employees to process")

        # Test Redis cache status
        self._test_redis_cache()

        if benchmark:
            self._run_benchmark(employees, year, month)
        else:
            self._run_optimized_test(employees, year, month)

    def _test_redis_cache(self):
        """Test Redis cache connectivity and performance"""
        self.stdout.write(self.style.HTTP_INFO("📋 Testing Redis Cache..."))

        try:
            cache_stats = payroll_cache.get_cache_stats()

            if cache_stats["status"] == "available":
                self.stdout.write(self.style.SUCCESS(f"Redis cache is available"))
                self.stdout.write(
                    f"   Connected clients: {cache_stats.get('connected_clients', 'unknown')}"
                )
                self.stdout.write(
                    f"   Used memory: {cache_stats.get('used_memory_human', 'unknown')}"
                )
                self.stdout.write(
                    f"   Cache hits: {cache_stats.get('keyspace_hits', 0)}"
                )
                self.stdout.write(
                    f"   Cache misses: {cache_stats.get('keyspace_misses', 0)}"
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'WARNING: Redis cache not available: {cache_stats.get("error", "unknown")}'
                    )
                )
                self.stdout.write("   Will use database fallback")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Redis cache test failed: {e}"))

    def _run_optimized_test(self, employees, year, month):
        """Run optimized payroll calculation test"""
        self.stdout.write(
            self.style.HTTP_INFO(" Running Optimized Payroll Calculation...")
        )

        start_time = time.time()

        try:
            results = optimized_self.payroll_service.calculate_bulk_payroll(
                employees, year, month
            )

            end_time = time.time()
            execution_time = end_time - start_time

            # Display results
            self.stdout.write(
                self.style.SUCCESS(
                    f"Calculation completed in {execution_time:.2f} seconds"
                )
            )

            self.stdout.write(f" Results Summary:")
            self.stdout.write(f"   Total employees processed: {len(results)}")

            # Count by status
            status_counts = {}
            total_salary = 0
            total_hours = 0

            for result in results:
                status = result.get("status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1
                total_salary += result.get("total_salary", 0)
                total_hours += result.get("total_hours", 0)

            for status, count in status_counts.items():
                self.stdout.write(f"   {status.title()}: {count} employees")

            self.stdout.write(f"   Total salary: ₪{total_salary:,.2f}")
            self.stdout.write(f"   Total hours: {total_hours:,.1f}")

            # Optimization stats
            optimization_stats = optimized_self.payroll_service.get_optimization_stats()
            api_usage = optimization_stats["api_usage"]

            self.stdout.write(f"📈 Performance Stats:")
            self.stdout.write(f'   DB queries: {api_usage["db_queries"]}')
            self.stdout.write(f'   Cache hits: {api_usage["cache_hits"]}')
            self.stdout.write(f'   Cache misses: {api_usage["cache_misses"]}')
            self.stdout.write(
                f'   Calculations performed: {api_usage["calculations_performed"]}'
            )

            # Performance metrics
            avg_time_per_employee = (
                execution_time / len(results) if len(results) > 0 else 0
            )
            self.stdout.write(f"⚡ Performance:")
            self.stdout.write(
                f"   Average time per employee: {avg_time_per_employee:.3f} seconds"
            )
            self.stdout.write(
                f"   Employees per second: {len(results) / execution_time:.1f}"
            )

            # Show sample results
            if results:
                self.stdout.write(f"📋 Sample Results:")
                for i, result in enumerate(results[:3]):  # Show first 3
                    employee = result["employee"]
                    self.stdout.write(
                        f'   {i+1}. {employee["name"]}: ₪{result["total_salary"]:.2f} '
                        f'({result["total_hours"]:.1f}h, {result["worked_days"]} days)'
                    )

                if len(results) > 3:
                    self.stdout.write(f"   ... and {len(results) - 3} more employees")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Optimized calculation failed: {e}"))
            logger.exception("Optimized payroll calculation failed")

    def _run_benchmark(self, employees, year, month):
        """Run benchmark comparison between optimized and legacy approaches"""
        self.stdout.write(self.style.HTTP_INFO("🏁 Running Performance Benchmark..."))

        # Test optimized approach
        self.stdout.write(" Testing optimized approach...")
        start_time = time.time()

        try:
            optimized_results = optimized_self.payroll_service.calculate_bulk_payroll(
                employees, year, month
            )
            optimized_time = time.time() - start_time
            optimized_success = True

        except Exception as e:
            optimized_time = time.time() - start_time
            optimized_success = False
            self.stdout.write(self.style.ERROR(f"❌ Optimized approach failed: {e}"))

        # Display benchmark results
        self.stdout.write(f"📈 Benchmark Results:")
        self.stdout.write(f"   Employees processed: {employees.count()}")

        if optimized_success:
            self.stdout.write(
                self.style.SUCCESS(
                    f"   Optimized: {optimized_time:.2f}s ({len(optimized_results)} results)"
                )
            )

            # Performance metrics
            avg_time = (
                optimized_time / len(optimized_results)
                if len(optimized_results) > 0
                else 0
            )
            throughput = (
                len(optimized_results) / optimized_time if optimized_time > 0 else 0
            )

            self.stdout.write(f"⚡ Performance Metrics:")
            self.stdout.write(f"   Time per employee: {avg_time:.3f}s")
            self.stdout.write(f"   Throughput: {throughput:.1f} employees/second")

            # Memory and efficiency stats
            optimization_stats = optimized_self.payroll_service.get_optimization_stats()
            api_usage = optimization_stats["api_usage"]

            self.stdout.write(f"Optimization Features:")
            for feature in optimization_stats["optimization_features"]:
                self.stdout.write(f"   ✓ {feature}")

        else:
            self.stdout.write(
                self.style.ERROR(f"   ❌ Optimized: FAILED after {optimized_time:.2f}s")
            )

        # Performance recommendation
        if optimized_success and optimized_time < 2.0:  # Less than 2 seconds
            self.stdout.write(
                self.style.SUCCESS("🎉 EXCELLENT: API response time under 2 seconds!")
            )
        elif optimized_success and optimized_time < 5.0:  # Less than 5 seconds
            self.stdout.write(
                self.style.SUCCESS("GOOD: API response time under 5 seconds")
            )
        elif optimized_success:
            self.stdout.write(
                self.style.WARNING(
                    f"WARNING: SLOW: API response time {optimized_time:.1f}s - consider further optimization"
                )
            )

