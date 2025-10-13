#!/usr/bin/env python
"""
Load testing script for bulk payroll calculations.

This script tests the bulk payroll service under various load conditions
to verify it can handle realistic production scenarios.

Usage:
    # Test with default settings
    python scripts/testing/load_test_bulk_payroll.py

    # Test with specific parameters
    python scripts/testing/load_test_bulk_payroll.py --employees 200 --iterations 5

    # Test parallel vs sequential
    python scripts/testing/load_test_bulk_payroll.py --compare-modes

    # Stress test
    python scripts/testing/load_test_bulk_payroll.py --stress-test
"""

import argparse
import json
import os
import sys
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytz

import django

# Setup Django environment
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myhours.settings")
os.environ["SKIP_NOTIFICATIONS"] = "1"  # Disable push notifications during load testing
django.setup()

from django.contrib.auth.models import User
from django.db import transaction

from payroll.models import Salary
from payroll.services.bulk.bulk_service import BulkEnhancedPayrollService
from payroll.services.enums import CalculationStrategy
from users.models import Employee
from worktime.models import WorkLog


class LoadTester:
    """Load testing utility for bulk payroll service."""

    def __init__(self, verbose=True):
        self.verbose = verbose
        self.results = []

    def log(self, message):
        """Print message if verbose."""
        if self.verbose:
            print(message)

    def create_test_data(self, employee_count: int) -> list:
        """
        Create test employees with work logs.

        Args:
            employee_count: Number of employees to create

        Returns:
            List of employee IDs
        """
        self.log(f"\n{'='*60}")
        self.log(f"Creating {employee_count} test employees...")
        self.log(f"{'='*60}")

        employees = []
        tz = pytz.timezone("Asia/Jerusalem")

        with transaction.atomic():
            for i in range(employee_count):
                # Create user
                username = f"loadtest_{int(time.time())}_{i}"
                user = User.objects.create_user(
                    username=username,
                    email=f"{username}@example.com",
                    password="testpass123",
                )

                # Create employee
                employee = Employee.objects.create(
                    user=user,
                    first_name=f"Load{i}",
                    last_name="Test",
                    email=f"load{i}@test.com",
                    employment_type="full_time" if i % 2 == 0 else "part_time",
                    is_active=True,
                )

                # Create salary
                if i % 3 == 0:
                    Salary.objects.create(
                        employee=employee,
                        calculation_type="hourly",
                        hourly_rate=Decimal("50.00"),
                        is_active=True,
                    )
                else:
                    Salary.objects.create(
                        employee=employee,
                        calculation_type="monthly",
                        base_salary=Decimal("10000.00"),
                        is_active=True,
                    )

                # Create work logs (10 days of work)
                for day in range(1, 11):
                    WorkLog.objects.create(
                        employee=employee,
                        check_in=datetime(2025, 10, day, 9, 0, 0, tzinfo=tz),
                        check_out=datetime(
                            2025, 10, day, 17 + (i % 3), 0, 0, tzinfo=tz
                        ),
                    )

                employees.append(employee.id)

                if (i + 1) % 10 == 0:
                    self.log(f"  Created {i + 1}/{employee_count} employees...")

        self.log(f"✓ Created {len(employees)} employees with work logs\n")
        return employees

    def cleanup_test_data(self, employee_ids: list):
        """Clean up test data."""
        self.log("\nCleaning up test data...")

        with transaction.atomic():
            employees = Employee.objects.filter(id__in=employee_ids)
            user_ids = list(employees.values_list("user_id", flat=True))

            # Delete employees (cascades to salaries and work logs)
            employees.delete()

            # Delete users
            User.objects.filter(id__in=user_ids).delete()

        self.log(f"✓ Cleaned up {len(employee_ids)} test employees\n")

    def run_load_test(
        self,
        employee_ids: list,
        year: int,
        month: int,
        use_cache: bool = True,
        use_parallel: bool = False,  # False for safety in scripts
        iterations: int = 1,
        clear_cache_before: bool = True,
    ) -> dict:
        """
        Run load test with specified parameters.

        Args:
            employee_ids: List of employee IDs
            year: Year for calculation
            month: Month for calculation
            use_cache: Enable caching
            use_parallel: Enable parallel processing
            iterations: Number of iterations to run
            clear_cache_before: Clear cache before test (default: True)

        Returns:
            Dictionary with test results
        """
        self.log(f"\n{'='*60}")
        self.log(f"LOAD TEST")
        self.log(f"{'='*60}")
        self.log(f"Employees:     {len(employee_ids)}")
        self.log(f"Period:        {year}-{month:02d}")
        self.log(f"Cache:         {'Enabled' if use_cache else 'Disabled'}")
        self.log(f"Parallel:      {'Enabled' if use_parallel else 'Disabled'}")
        self.log(f"Iterations:    {iterations}")
        self.log(f"{'='*60}\n")

        service = BulkEnhancedPayrollService(
            use_cache=use_cache, use_parallel=use_parallel, show_progress=True
        )

        # Clear cache before test (if requested)
        if use_cache and clear_cache_before:
            service.invalidate_cache(employee_ids, year, month)

        iteration_results = []

        for i in range(iterations):
            self.log(f"\n--- Iteration {i + 1}/{iterations} ---")

            start_time = time.time()

            result = service.calculate_bulk(
                employee_ids=employee_ids, year=year, month=month, save_to_db=False
            )

            duration = time.time() - start_time

            iteration_result = {
                "iteration": i + 1,
                "total_count": result.total_count,
                "successful_count": result.successful_count,
                "failed_count": result.failed_count,
                "cached_count": result.cached_count,
                "calculated_count": result.calculated_count,
                "duration_seconds": duration,
                "throughput": len(employee_ids) / duration if duration > 0 else 0,
                "cache_hit_rate": result.cache_hit_rate,
                "db_queries": result.db_queries_count,
            }

            iteration_results.append(iteration_result)

            self.log(f"Duration:     {duration:.2f}s")
            self.log(
                f"Throughput:   {iteration_result['throughput']:.1f} employees/sec"
            )
            self.log(f"Success rate: {result.successful_count}/{result.total_count}")
            self.log(
                f"Cache hits:   {result.cached_count}/{result.total_count} ({result.cache_hit_rate:.1f}%)"
            )

        # Calculate aggregate statistics
        avg_duration = (
            sum(r["duration_seconds"] for r in iteration_results) / iterations
        )
        avg_throughput = sum(r["throughput"] for r in iteration_results) / iterations
        min_duration = min(r["duration_seconds"] for r in iteration_results)
        max_duration = max(r["duration_seconds"] for r in iteration_results)

        summary = {
            "test_config": {
                "employee_count": len(employee_ids),
                "year": year,
                "month": month,
                "use_cache": use_cache,
                "use_parallel": use_parallel,
                "iterations": iterations,
            },
            "results": {
                "avg_duration_seconds": avg_duration,
                "min_duration_seconds": min_duration,
                "max_duration_seconds": max_duration,
                "avg_throughput": avg_throughput,
                "total_successful": sum(
                    r["successful_count"] for r in iteration_results
                ),
                "total_failed": sum(r["failed_count"] for r in iteration_results),
            },
            "iterations": iteration_results,
        }

        self.log(f"\n{'='*60}")
        self.log("SUMMARY")
        self.log(f"{'='*60}")
        self.log(f"Average duration:  {avg_duration:.2f}s")
        self.log(f"Min duration:      {min_duration:.2f}s")
        self.log(f"Max duration:      {max_duration:.2f}s")
        self.log(f"Average throughput: {avg_throughput:.1f} employees/sec")
        self.log(f"{'='*60}\n")

        return summary

    def compare_modes(self, employee_ids: list, year: int, month: int):
        """
        Compare different processing modes.

        Tests:
        1. Sequential without cache
        2. Sequential with cache (cold)
        3. Sequential with cache (warm)
        """
        self.log(f"\n{'='*70}")
        self.log("COMPARISON TEST: Different Processing Modes")
        self.log(f"{'='*70}\n")

        results = {}

        # Test 1: Sequential without cache
        self.log("Test 1: Sequential without cache")
        results["sequential_no_cache"] = self.run_load_test(
            employee_ids, year, month, use_cache=False, use_parallel=False, iterations=1
        )

        # Test 2: Sequential with cache (cold)
        self.log("\nTest 2: Sequential with cache (cold)")
        results["sequential_cold_cache"] = self.run_load_test(
            employee_ids, year, month, use_cache=True, use_parallel=False, iterations=1
        )

        # Test 3: Sequential with cache (warm)
        self.log("\nTest 3: Sequential with cache (warm)")
        results["sequential_warm_cache"] = self.run_load_test(
            employee_ids,
            year,
            month,
            use_cache=True,
            use_parallel=False,
            iterations=1,
            clear_cache_before=False,  # Don't clear cache - use warm cache!
        )

        # Print comparison
        self.log(f"\n{'='*70}")
        self.log("COMPARISON RESULTS")
        self.log(f"{'='*70}")

        for mode_name, result in results.items():
            duration = result["results"]["avg_duration_seconds"]
            throughput = result["results"]["avg_throughput"]
            self.log(f"{mode_name:30s}: {duration:6.2f}s  ({throughput:6.1f} emp/sec)")

        self.log(f"{'='*70}\n")

        return results

    def stress_test(self, max_employees: int = 500, step: int = 50):
        """
        Stress test with increasing employee counts.

        Args:
            max_employees: Maximum number of employees to test
            step: Increment step
        """
        self.log(f"\n{'='*70}")
        self.log(f"STRESS TEST: Scaling from {step} to {max_employees} employees")
        self.log(f"{'='*70}\n")

        results = []

        for employee_count in range(step, max_employees + 1, step):
            self.log(f"\n{'='*70}")
            self.log(f"Testing with {employee_count} employees")
            self.log(f"{'='*70}")

            # Create test data
            employee_ids = self.create_test_data(employee_count)

            try:
                # Run test
                result = self.run_load_test(
                    employee_ids,
                    year=2025,
                    month=10,
                    use_cache=False,
                    use_parallel=False,
                    iterations=1,
                )

                results.append(
                    {
                        "employee_count": employee_count,
                        "duration": result["results"]["avg_duration_seconds"],
                        "throughput": result["results"]["avg_throughput"],
                    }
                )

            finally:
                # Cleanup
                self.cleanup_test_data(employee_ids)

        # Print stress test summary
        self.log(f"\n{'='*70}")
        self.log("STRESS TEST SUMMARY")
        self.log(f"{'='*70}")
        self.log(
            f"{'Employees':>12} | {'Duration (s)':>12} | {'Throughput (emp/s)':>20}"
        )
        self.log(f"{'-'*70}")

        for result in results:
            self.log(
                f"{result['employee_count']:12d} | "
                f"{result['duration']:12.2f} | "
                f"{result['throughput']:20.1f}"
            )

        self.log(f"{'='*70}\n")

        return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Load testing for bulk payroll calculations"
    )
    parser.add_argument(
        "--employees",
        type=int,
        default=50,
        help="Number of employees to test (default: 50)",
    )
    parser.add_argument(
        "--iterations", type=int, default=3, help="Number of iterations (default: 3)"
    )
    parser.add_argument(
        "--year", type=int, default=2025, help="Year for calculation (default: 2025)"
    )
    parser.add_argument(
        "--month", type=int, default=10, help="Month for calculation (default: 10)"
    )
    parser.add_argument(
        "--compare-modes",
        action="store_true",
        help="Compare different processing modes",
    )
    parser.add_argument(
        "--stress-test",
        action="store_true",
        help="Run stress test with increasing employee counts",
    )
    parser.add_argument(
        "--max-employees",
        type=int,
        default=200,
        help="Maximum employees for stress test (default: 200)",
    )
    parser.add_argument(
        "--output", type=str, help="Output file for results (JSON format)"
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress detailed output")

    args = parser.parse_args()

    tester = LoadTester(verbose=not args.quiet)

    try:
        if args.stress_test:
            # Run stress test
            results = tester.stress_test(max_employees=args.max_employees, step=50)

        elif args.compare_modes:
            # Create test data once
            employee_ids = tester.create_test_data(args.employees)

            try:
                results = tester.compare_modes(employee_ids, args.year, args.month)
            finally:
                tester.cleanup_test_data(employee_ids)

        else:
            # Standard load test
            employee_ids = tester.create_test_data(args.employees)

            try:
                results = tester.run_load_test(
                    employee_ids,
                    args.year,
                    args.month,
                    use_cache=True,
                    use_parallel=False,  # Keep False for script safety
                    iterations=args.iterations,
                )
            finally:
                tester.cleanup_test_data(employee_ids)

        # Save results if output file specified
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w") as f:
                json.dump(results, f, indent=2, default=str)

            print(f"\n✓ Results saved to: {output_path}")

        print("\n✓ Load testing completed successfully!")

    except KeyboardInterrupt:
        print("\n\n⚠ Load testing interrupted by user")
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ Load testing failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
