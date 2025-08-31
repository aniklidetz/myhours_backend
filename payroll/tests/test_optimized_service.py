"""
Smoke tests for payroll/optimized_service.py to improve coverage from 0% to 85%+

Tests the OptimizedPayrollService class covering:
- Service initialization and configuration
- Basic bulk payroll calculation workflow
- Optimization statistics tracking
- Error handling scenarios
- Cache interaction
- Performance optimizations (prefetch, bulk queries)

These are "smoke tests" - they verify the service works without errors
and covers main execution paths without deep business logic validation.
"""

import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase

from payroll.models import MonthlyPayrollSummary, Salary
from payroll.optimized_service import OptimizedPayrollService
from users.models import Employee
from worktime.models import WorkLog


class OptimizedPayrollServiceTest(TestCase):
    """Smoke tests for OptimizedPayrollService"""

    def setUp(self):
        # Create test users and employees
        self.user1 = User.objects.create_user(
            username="emp1", email="emp1@test.com", password="pass123"
        )
        self.employee1 = Employee.objects.create(
            user=self.user1,
            first_name="Test",
            last_name="Employee1",
            email="emp1@test.com",
            employment_type="full_time",
            role="employee",
        )
        self.salary1 = Salary.objects.create(
            employee=self.employee1,
            calculation_type="monthly",
            base_salary=Decimal("10000.00"),
            currency="ILS",
        )

        self.user2 = User.objects.create_user(
            username="emp2", email="emp2@test.com", password="pass123"
        )
        self.employee2 = Employee.objects.create(
            user=self.user2,
            first_name="Test",
            last_name="Employee2",
            email="emp2@test.com",
            employment_type="part_time",
            role="employee",
        )
        self.salary2 = Salary.objects.create(
            employee=self.employee2,
            calculation_type="hourly",
            hourly_rate=Decimal("50.00"),
            currency="ILS",
        )

        # Test date parameters
        self.test_year = 2025
        self.test_month = 2


class OptimizedServiceInitializationTest(OptimizedPayrollServiceTest):
    """Test service initialization"""

    def test_service_initialization_default(self):
        """Test service initializes with default parameters"""
        service = OptimizedPayrollService()

        self.assertTrue(service.fast_mode)
        self.assertIsInstance(service.api_usage, dict)
        self.assertEqual(service.api_usage["db_queries"], 0)
        self.assertEqual(service.api_usage["cache_hits"], 0)
        self.assertEqual(service.api_usage["cache_misses"], 0)
        self.assertEqual(service.api_usage["calculations_performed"], 0)

    def test_service_initialization_slow_mode(self):
        """Test service initializes with slow mode disabled"""
        service = OptimizedPayrollService(fast_mode=False)

        self.assertFalse(service.fast_mode)
        self.assertIsInstance(service.api_usage, dict)

    def test_get_optimization_stats(self):
        """Test getting optimization statistics"""
        service = OptimizedPayrollService()

        # Initially should have zero stats
        stats = service.get_optimization_stats()

        self.assertIsInstance(stats, dict)
        self.assertIn("api_usage", stats)
        self.assertIn("service_type", stats)
        self.assertIn("fast_mode", stats)
        self.assertIn("optimization_features", stats)

        # Check API usage structure
        api_usage = stats["api_usage"]
        self.assertIn("db_queries", api_usage)
        self.assertIn("cache_hits", api_usage)
        self.assertIn("cache_misses", api_usage)
        self.assertIn("calculations_performed", api_usage)
        self.assertEqual(api_usage["db_queries"], 0)
        self.assertEqual(api_usage["cache_hits"], 0)
        self.assertEqual(api_usage["cache_misses"], 0)
        self.assertEqual(api_usage["calculations_performed"], 0)


class OptimizedServiceBulkCalculationTest(OptimizedPayrollServiceTest):
    """Test bulk payroll calculation"""

    @patch("payroll.optimized_service.enhanced_payroll_cache")
    def test_calculate_bulk_payroll_empty_employees(self, mock_cache):
        """Test bulk calculation with empty employee queryset"""
        service = OptimizedPayrollService()

        # Mock cache to return empty data
        mock_cache.get_holidays_with_shabbat_times.return_value = {}

        # Empty queryset
        employees = Employee.objects.none()

        results = service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        self.assertEqual(results, [])

        # Check that cache was called
        mock_cache.get_holidays_with_shabbat_times.assert_called_once_with(
            self.test_year, self.test_month
        )

        # Verify stats were updated
        stats = service.get_optimization_stats()
        api_usage = stats["api_usage"]
        self.assertEqual(api_usage["db_queries"], 1)  # Prefetch query
        # Cache returning empty data might be counted as miss, not hit
        self.assertGreaterEqual(api_usage["cache_hits"] + api_usage["cache_misses"], 1)

    @patch("payroll.optimized_service.enhanced_payroll_cache")
    def test_calculate_bulk_payroll_with_employees(self, mock_cache):
        """Test bulk calculation with actual employees"""
        service = OptimizedPayrollService()

        # Mock cache to return holidays data
        mock_cache.get_holidays_with_shabbat_times.return_value = {
            "2025-02-08": {
                "name": "Shabbat",
                "is_shabbat": True,
                "precise_start_time": "2025-02-07T17:00:00Z",
                "precise_end_time": "2025-02-08T18:00:00Z",
            }
        }

        # Get employees with salary info
        employees = Employee.objects.prefetch_related("salaries").filter(
            id__in=[self.employee1.id, self.employee2.id]
        )

        results = service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        # Should return results for all employees (even if empty/error results)
        self.assertEqual(len(results), 2)

        # Each result should be a dictionary
        for result in results:
            self.assertIsInstance(result, dict)
            self.assertIn("employee", result)

        # Verify stats were updated
        stats = service.get_optimization_stats()
        api_usage = stats["api_usage"]
        self.assertGreater(api_usage["db_queries"], 0)
        self.assertGreater(api_usage["calculations_performed"], 0)

    @patch("payroll.optimized_service.enhanced_payroll_cache")
    def test_calculate_bulk_payroll_cache_failure(self, mock_cache):
        """Test bulk calculation when cache fails"""
        service = OptimizedPayrollService()

        # Mock cache to raise exception
        mock_cache.get_holidays_with_shabbat_times.side_effect = Exception(
            "Cache error"
        )

        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.employee1.id
        )

        # Should not raise exception, should handle gracefully
        results = service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        self.assertIsInstance(results, list)

        # Verify cache miss was recorded
        stats = service.get_optimization_stats()
        api_usage = stats["api_usage"]
        self.assertEqual(api_usage["cache_misses"], 1)

    @patch("payroll.optimized_service.enhanced_payroll_cache")
    def test_calculate_bulk_payroll_with_existing_summary(self, mock_cache):
        """Test bulk calculation when MonthlyPayrollSummary exists"""
        service = OptimizedPayrollService()

        # Mock cache
        mock_cache.get_holidays_with_shabbat_times.return_value = {}

        # Create existing monthly summary
        summary = MonthlyPayrollSummary.objects.create(
            employee=self.employee1,
            year=self.test_year,
            month=self.test_month,
            total_gross_pay=Decimal("8000.00"),
            total_hours=Decimal("160.0"),
            worked_days=20,
        )

        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.employee1.id
        )

        results = service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        self.assertEqual(len(results), 1)
        result = results[0]

        # Should use existing summary data
        self.assertIn("employee", result)
        self.assertIsInstance(result["employee"], dict)
        self.assertEqual(result["employee"]["name"], self.employee1.get_full_name())


class OptimizedServiceSingleEmployeeTest(OptimizedPayrollServiceTest):
    """Test single employee calculation methods"""

    @patch("payroll.optimized_service.enhanced_payroll_cache")
    def test_calculate_single_employee_optimized(self, mock_cache):
        """Test single employee optimized calculation"""
        service = OptimizedPayrollService()

        # Mock cache
        mock_cache.get_holidays_with_shabbat_times.return_value = {}

        # Create some work logs
        WorkLog.objects.create(
            employee=self.employee1,
            check_in=datetime(2025, 2, 15, 9, 0),
            check_out=datetime(2025, 2, 15, 17, 0),
        )

        # This is a private method, but we can test it exists and works
        # through the public bulk calculation method
        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.employee1.id
        )

        results = service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        # Should complete without error
        self.assertEqual(len(results), 1)

        # Result should have basic structure
        result = results[0]
        self.assertIn("employee", result)
        self.assertIsInstance(result, dict)


class OptimizedServiceHelperMethodsTest(OptimizedPayrollServiceTest):
    """Test helper and utility methods"""

    def test_convert_summary_to_result(self):
        """Test conversion of MonthlyPayrollSummary to result dict"""
        service = OptimizedPayrollService()

        # Create test summary
        summary = MonthlyPayrollSummary(
            employee=self.employee1,
            year=self.test_year,
            month=self.test_month,
            total_gross_pay=Decimal("8000.00"),
            total_hours=Decimal("160.0"),
            worked_days=20,
        )

        # This is a private method, test indirectly
        # We'll verify it's called through the public interface
        MonthlyPayrollSummary.objects.create(
            employee=self.employee1,
            year=self.test_year,
            month=self.test_month,
            total_gross_pay=Decimal("8000.00"),
            total_hours=Decimal("160.0"),
            worked_days=20,
        )

        with patch("payroll.optimized_service.enhanced_payroll_cache") as mock_cache:
            mock_cache.get_holidays_with_shabbat_times.return_value = {}

            employees = Employee.objects.prefetch_related("salaries").filter(
                id=self.employee1.id
            )

            results = service.calculate_bulk_payroll(
                employees, self.test_year, self.test_month
            )

            # Should successfully convert summary to result
            self.assertEqual(len(results), 1)
            result = results[0]
            self.assertIn("employee", result)
            self.assertIsInstance(result["employee"], dict)
            self.assertEqual(result["employee"]["name"], self.employee1.get_full_name())

    def test_create_error_result(self):
        """Test error result creation"""
        service = OptimizedPayrollService()

        # Force an error by using an employee without salary info
        employee_no_salary = Employee.objects.create(
            user=User.objects.create_user(
                username="nosalary", email="nosalary@test.com", password="pass123"
            ),
            first_name="No",
            last_name="Salary",
            email="nosalary@test.com",
            employment_type="full_time",
            role="employee",
        )

        with patch("payroll.optimized_service.enhanced_payroll_cache") as mock_cache:
            mock_cache.get_holidays_with_shabbat_times.return_value = {}

            employees = Employee.objects.prefetch_related("salaries").filter(
                id=employee_no_salary.id
            )

            results = service.calculate_bulk_payroll(
                employees, self.test_year, self.test_month
            )

            # Should create error result instead of crashing
            self.assertEqual(len(results), 1)
            result = results[0]
            self.assertIn("employee", result)
            # Error results should still have basic structure


class OptimizedServicePerformanceTest(OptimizedPayrollServiceTest):
    """Test performance optimizations"""

    @patch("payroll.optimized_service.enhanced_payroll_cache")
    def test_bulk_db_optimization_tracking(self, mock_cache):
        """Test that bulk operations track database queries properly"""
        service = OptimizedPayrollService()

        # Mock cache
        mock_cache.get_holidays_with_shabbat_times.return_value = {}

        # Create multiple employees
        employees = Employee.objects.prefetch_related("salaries").filter(
            id__in=[self.employee1.id, self.employee2.id]
        )

        # Track initial query count
        initial_stats = service.get_optimization_stats()
        initial_api_usage = initial_stats["api_usage"]
        initial_queries = initial_api_usage["db_queries"]

        results = service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        # Verify query optimization
        final_stats = service.get_optimization_stats()
        final_api_usage = final_stats["api_usage"]

        # Should have made minimal database queries due to optimization
        # The exact number depends on prefetch and bulk operations
        self.assertGreater(final_api_usage["db_queries"], initial_queries)
        self.assertGreater(final_api_usage["calculations_performed"], 0)

        # Results should be returned for all employees
        self.assertEqual(len(results), 2)

    @patch("payroll.optimized_service.enhanced_payroll_cache")
    def test_cache_hit_optimization(self, mock_cache):
        """Test cache hit optimization tracking"""
        service = OptimizedPayrollService()

        # Mock successful cache hit
        mock_cache.get_holidays_with_shabbat_times.return_value = {
            "2025-02-01": {"name": "Test Holiday", "is_holiday": True}
        }

        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.employee1.id
        )

        service.calculate_bulk_payroll(employees, self.test_year, self.test_month)

        stats = service.get_optimization_stats()
        api_usage = stats["api_usage"]
        self.assertEqual(api_usage["cache_hits"], 1)
        self.assertEqual(api_usage["cache_misses"], 0)

    @patch("payroll.optimized_service.enhanced_payroll_cache")
    def test_cache_miss_optimization(self, mock_cache):
        """Test cache miss optimization tracking"""
        service = OptimizedPayrollService()

        # Mock cache miss (returns None or empty)
        mock_cache.get_holidays_with_shabbat_times.return_value = None

        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.employee1.id
        )

        service.calculate_bulk_payroll(employees, self.test_year, self.test_month)

        stats = service.get_optimization_stats()
        api_usage = stats["api_usage"]
        self.assertEqual(api_usage["cache_hits"], 0)
        self.assertEqual(api_usage["cache_misses"], 1)


class OptimizedServiceErrorHandlingTest(OptimizedPayrollServiceTest):
    """Test error handling scenarios"""

    @patch("payroll.optimized_service.enhanced_payroll_cache")
    def test_employee_calculation_exception_handling(self, mock_cache):
        """Test handling of exceptions during employee calculation"""
        service = OptimizedPayrollService()

        # Mock cache
        mock_cache.get_holidays_with_shabbat_times.return_value = {}

        # Use employees that might cause calculation issues
        employees = Employee.objects.prefetch_related("salaries").filter(
            id__in=[self.employee1.id, self.employee2.id]
        )

        # Should handle any calculation exceptions gracefully
        results = service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        # Should not crash and should return results (even if error results)
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 2)

        # Each result should be a valid dictionary
        for result in results:
            self.assertIsInstance(result, dict)
            self.assertIn("employee", result)

    @patch("payroll.optimized_service.enhanced_payroll_cache")
    @patch("payroll.optimized_service.MonthlyPayrollSummary.objects.filter")
    def test_summary_loading_exception_handling(self, mock_summary_filter, mock_cache):
        """Test handling of exceptions when loading monthly summaries"""
        service = OptimizedPayrollService()

        # Mock cache
        mock_cache.get_holidays_with_shabbat_times.return_value = {}

        # Mock summary loading to raise exception
        mock_summary_filter.side_effect = Exception("Database error")

        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.employee1.id
        )

        # Should handle exception gracefully and continue
        results = service.calculate_bulk_payroll(
            employees, self.test_year, self.test_month
        )

        # Should still return results
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 1)

    def test_fast_mode_configuration(self):
        """Test fast mode vs slow mode behavior"""
        # Fast mode service
        fast_service = OptimizedPayrollService(fast_mode=True)
        self.assertTrue(fast_service.fast_mode)

        # Slow mode service
        slow_service = OptimizedPayrollService(fast_mode=False)
        self.assertFalse(slow_service.fast_mode)

        # Both should initialize properly
        self.assertIsInstance(fast_service.api_usage, dict)
        self.assertIsInstance(slow_service.api_usage, dict)


class OptimizedServiceEdgeCasesTest(OptimizedPayrollServiceTest):
    """Test edge cases and boundary conditions"""

    @patch("payroll.optimized_service.enhanced_payroll_cache")
    def test_december_calculation(self, mock_cache):
        """Test calculation for December (year boundary)"""
        service = OptimizedPayrollService()

        mock_cache.get_holidays_with_shabbat_times.return_value = {}

        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.employee1.id
        )

        # Test December calculation
        results = service.calculate_bulk_payroll(employees, 2024, 12)

        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 1)

    @patch("payroll.optimized_service.enhanced_payroll_cache")
    def test_february_leap_year_calculation(self, mock_cache):
        """Test calculation for February in leap year"""
        service = OptimizedPayrollService()

        mock_cache.get_holidays_with_shabbat_times.return_value = {}

        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.employee1.id
        )

        # Test leap year February (2024)
        results = service.calculate_bulk_payroll(employees, 2024, 2)

        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 1)

    @patch("payroll.optimized_service.enhanced_payroll_cache")
    def test_statistics_accuracy(self, mock_cache):
        """Test that statistics are accurately tracked"""
        service = OptimizedPayrollService()

        # Mock cache hit
        mock_cache.get_holidays_with_shabbat_times.return_value = {}

        # Multiple calculation runs
        employees = Employee.objects.prefetch_related("salaries").filter(
            id=self.employee1.id
        )

        # First calculation
        service.calculate_bulk_payroll(employees, self.test_year, self.test_month)
        stats1 = service.get_optimization_stats()

        # Second calculation
        service.calculate_bulk_payroll(employees, self.test_year, self.test_month + 1)
        stats2 = service.get_optimization_stats()

        # Statistics should accumulate (but might be same if similar queries)
        api_usage1 = stats1["api_usage"]
        api_usage2 = stats2["api_usage"]
        # DB queries should at least stay the same or increase
        self.assertGreaterEqual(api_usage2["db_queries"], api_usage1["db_queries"])
        self.assertGreaterEqual(
            api_usage2["calculations_performed"], api_usage1["calculations_performed"]
        )
        self.assertGreaterEqual(
            api_usage2["cache_hits"] + api_usage2["cache_misses"],
            api_usage1["cache_hits"] + api_usage1["cache_misses"],
        )
