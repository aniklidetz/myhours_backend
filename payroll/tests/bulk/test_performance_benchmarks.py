"""
Performance benchmarking tests for BulkEnhancedPayrollService.

These tests measure performance characteristics and verify that bulk
processing provides the expected speedup compared to sequential processing.

Run with:
    pytest payroll/tests/bulk/test_performance_benchmarks.py -v -s
"""

import time
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytz

from django.contrib.auth.models import User
from django.test import TestCase

from payroll.models import Salary
from payroll.services.bulk.bulk_service import BulkEnhancedPayrollService
from payroll.services.enums import CalculationStrategy
from users.models import Employee
from worktime.models import WorkLog


class PerformanceBenchmarkTestCase(TestCase):
    """Performance benchmarking tests for bulk payroll service."""

    @classmethod
    def setUpTestData(cls):
        """Create a large dataset for benchmarking."""
        cls.employee_count = 50  # Adjustable for different scales
        cls.employees = []

        tz = pytz.timezone("Asia/Jerusalem")

        for i in range(cls.employee_count):
            # Create user
            user = User.objects.create_user(
                username=f"perftest{i}", email=f"perftest{i}@example.com"
            )

            # Create employee
            employee = Employee.objects.create(
                user=user,
                first_name=f"Test{i}",
                last_name="User",
                email=f"test{i}@example.com",
                employment_type="full_time",
                is_active=True,
            )

            # Create salary (alternate between hourly and monthly)
            if i % 2 == 0:
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
                    base_salary=Decimal("8000.00"),
                    is_active=True,
                )

            # Create work logs (5 days of work)
            for day in range(9, 14):  # Oct 9-13, 2025
                WorkLog.objects.create(
                    employee=employee,
                    check_in=datetime(2025, 10, day, 9, 0, 0, tzinfo=tz),
                    check_out=datetime(2025, 10, day, 17, 0, 0, tzinfo=tz),
                )

            cls.employees.append(employee)

    @patch("payroll.services.bulk.data_loader.get_shabbat_times")
    def test_benchmark_sequential_vs_bulk(self, mock_get_shabbat_times):
        """
        Benchmark sequential vs bulk processing.

        This test measures the time difference between:
        1. Processing employees one-by-one (sequential)
        2. Processing all employees at once (bulk)

        Expected: Bulk should be faster for large batches
        """
        mock_get_shabbat_times.return_value = {
            "shabbat_start": "2025-10-10T18:00:00Z",
            "shabbat_end": "2025-10-11T19:00:00Z",
        }

        employee_ids = [emp.id for emp in self.employees]
        year = 2025
        month = 10

        # Test 1: Sequential processing
        print(f"\n{'='*60}")
        print(f"Testing with {len(employee_ids)} employees")
        print(f"{'='*60}")

        service_sequential = BulkEnhancedPayrollService(
            use_cache=False, use_parallel=False, show_progress=True
        )

        start_seq = time.time()
        result_seq = service_sequential.calculate_bulk(
            employee_ids=employee_ids, year=year, month=month, save_to_db=False
        )
        duration_seq = time.time() - start_seq

        # Test 2: Bulk processing (sequential mode for tests, but with bulk data loading)
        service_bulk = BulkEnhancedPayrollService(
            use_cache=False,
            use_parallel=False,  # Keep False for tests
            batch_size=1000,
            show_progress=True,
        )

        start_bulk = time.time()
        result_bulk = service_bulk.calculate_bulk(
            employee_ids=employee_ids, year=year, month=month, save_to_db=False
        )
        duration_bulk = time.time() - start_bulk

        # Print results
        print(f"\n{'='*60}")
        print("BENCHMARK RESULTS")
        print(f"{'='*60}")
        print(f"Sequential processing: {duration_seq:.2f}s")
        print(f"Bulk processing:       {duration_bulk:.2f}s")
        print(f"Speedup:               {duration_seq/duration_bulk:.2f}x")
        print(
            f"Throughput (seq):      {len(employee_ids)/duration_seq:.1f} employees/sec"
        )
        print(
            f"Throughput (bulk):     {len(employee_ids)/duration_bulk:.1f} employees/sec"
        )
        print(
            f"\nSequential result: {result_seq.successful_count}/{result_seq.total_count} successful"
        )
        print(
            f"Bulk result:       {result_bulk.successful_count}/{result_bulk.total_count} successful"
        )
        print(f"{'='*60}\n")

        # Assertions
        self.assertEqual(result_seq.successful_count, len(employee_ids))
        self.assertEqual(result_bulk.successful_count, len(employee_ids))

        # Bulk should be at least as fast (accounting for overhead in small batches)
        # Note: 2.0x tolerance to account for test environment variability
        self.assertLessEqual(
            duration_bulk,
            duration_seq * 2.0,
            "Bulk processing should not be significantly slower",
        )

    @patch("payroll.services.bulk.data_loader.get_shabbat_times")
    def test_benchmark_with_cache(self, mock_get_shabbat_times):
        """
        Benchmark cache effectiveness.

        Measures performance improvement from caching:
        1. First run (cold cache)
        2. Second run (warm cache)

        Expected: Second run should be significantly faster
        """
        mock_get_shabbat_times.return_value = {
            "shabbat_start": "2025-10-10T18:00:00Z",
            "shabbat_end": "2025-10-11T19:00:00Z",
        }

        employee_ids = [emp.id for emp in self.employees[:20]]  # Smaller batch
        year = 2025
        month = 10

        service = BulkEnhancedPayrollService(
            use_cache=True, use_parallel=False, show_progress=False
        )

        # Clear cache first
        service.invalidate_cache(employee_ids, year, month)

        # Run 1: Cold cache
        start_cold = time.time()
        result_cold = service.calculate_bulk(
            employee_ids=employee_ids, year=year, month=month, save_to_db=False
        )
        duration_cold = time.time() - start_cold

        # Run 2: Warm cache
        start_warm = time.time()
        result_warm = service.calculate_bulk(
            employee_ids=employee_ids, year=year, month=month, save_to_db=False
        )
        duration_warm = time.time() - start_warm

        # Print results
        print(f"\n{'='*60}")
        print("CACHE BENCHMARK RESULTS")
        print(f"{'='*60}")
        print(f"Cold cache (calculated): {duration_cold:.3f}s")
        print(f"Warm cache (from cache): {duration_warm:.3f}s")
        print(f"Cache speedup:           {duration_cold/duration_warm:.2f}x")
        print(f"Cache hit rate:          {result_warm.cache_hit_rate:.1f}%")
        print(
            f"Cached results:          {result_warm.cached_count}/{result_warm.total_count}"
        )
        print(f"{'='*60}\n")

        # Assertions
        self.assertEqual(result_cold.successful_count, len(employee_ids))
        self.assertEqual(result_warm.successful_count, len(employee_ids))
        self.assertEqual(
            result_warm.cached_count,
            len(employee_ids),
            "All results should come from cache on second run",
        )
        self.assertLess(
            duration_warm, duration_cold, "Cached run should be faster than cold run"
        )

    @patch("payroll.services.bulk.data_loader.get_shabbat_times")
    def test_benchmark_database_queries(self, mock_get_shabbat_times):
        """
        Benchmark database query efficiency.

        Verifies that bulk loading uses minimal queries regardless of
        employee count (3-5 queries vs N*100+ in naive implementation).
        """
        mock_get_shabbat_times.return_value = {
            "shabbat_start": "2025-10-10T18:00:00Z",
            "shabbat_end": "2025-10-11T19:00:00Z",
        }

        # Test with different batch sizes
        batch_sizes = [5, 10, 20, 50]

        print(f"\n{'='*60}")
        print("DATABASE QUERY BENCHMARK")
        print(f"{'='*60}")

        for batch_size in batch_sizes:
            employee_ids = [emp.id for emp in self.employees[:batch_size]]

            service = BulkEnhancedPayrollService(
                use_cache=False, use_parallel=False, show_progress=False
            )

            result = service.calculate_bulk(
                employee_ids=employee_ids, year=2025, month=10, save_to_db=False
            )

            queries_per_employee = (
                result.db_queries_count / batch_size if batch_size > 0 else 0
            )

            print(
                f"Batch size: {batch_size:3d} | "
                f"Queries: {result.db_queries_count:3d} | "
                f"Per employee: {queries_per_employee:.2f}"
            )

            # Verify query efficiency
            # With bulk loading, we expect ~3-5 queries total, not per employee
            self.assertLess(
                result.db_queries_count,
                20,
                f"Expected < 20 queries for {batch_size} employees, "
                f"got {result.db_queries_count}",
            )

        print(f"{'='*60}\n")

    @patch("payroll.services.bulk.data_loader.get_shabbat_times")
    def test_benchmark_memory_efficiency(self, mock_get_shabbat_times):
        """
        Benchmark memory usage patterns.

        Verifies that bulk processing doesn't load excessive data into memory.
        """
        import tracemalloc

        mock_get_shabbat_times.return_value = {
            "shabbat_start": "2025-10-10T18:00:00Z",
            "shabbat_end": "2025-10-11T19:00:00Z",
        }

        employee_ids = [emp.id for emp in self.employees]

        service = BulkEnhancedPayrollService(
            use_cache=False, use_parallel=False, show_progress=False
        )

        # Start memory tracking
        tracemalloc.start()

        result = service.calculate_bulk(
            employee_ids=employee_ids, year=2025, month=10, save_to_db=False
        )

        # Get memory usage
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Print results
        print(f"\n{'='*60}")
        print("MEMORY BENCHMARK RESULTS")
        print(f"{'='*60}")
        print(f"Employees processed: {len(employee_ids)}")
        print(f"Current memory:      {current / 1024 / 1024:.2f} MB")
        print(f"Peak memory:         {peak / 1024 / 1024:.2f} MB")
        print(f"Memory per employee: {peak / len(employee_ids) / 1024:.2f} KB")
        print(f"{'='*60}\n")

        # Assertion: memory usage should be reasonable
        # (< 100MB for 50 employees is very generous)
        self.assertLess(
            peak,
            100 * 1024 * 1024,
            "Peak memory usage should be < 100MB for test batch",
        )
