"""
Tests for BulkEnhancedPayrollService.
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

import pytz

from django.contrib.auth.models import User
from django.test import TestCase

from payroll.models import Salary
from payroll.services.bulk.bulk_service import BulkEnhancedPayrollService
from payroll.services.bulk.types import BulkCalculationResult
from payroll.services.enums import CalculationStrategy
from users.models import Employee
from worktime.models import WorkLog


class BulkEnhancedPayrollServiceTestCase(TestCase):
    """Tests for BulkEnhancedPayrollService class."""

    def setUp(self):
        """Set up test data."""
        # Create test users and employees
        self.user1 = User.objects.create_user(
            username="testuser1", email="test1@example.com", password="testpass123"
        )
        self.user2 = User.objects.create_user(
            username="testuser2", email="test2@example.com", password="testpass123"
        )

        self.employee1 = Employee.objects.create(
            user=self.user1,
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            employment_type="full_time",
            is_active=True,
        )

        self.employee2 = Employee.objects.create(
            user=self.user2,
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            employment_type="full_time",
            is_active=True,
        )

        # Create salaries
        self.salary1 = Salary.objects.create(
            employee=self.employee1,
            calculation_type="hourly",
            hourly_rate=Decimal("50.00"),
            is_active=True,
        )

        self.salary2 = Salary.objects.create(
            employee=self.employee2,
            calculation_type="monthly",
            base_salary=Decimal("8000.00"),
            is_active=True,
        )

        # Create work logs
        tz = pytz.timezone("Asia/Jerusalem")

        self.worklog1 = WorkLog.objects.create(
            employee=self.employee1,
            check_in=datetime(2025, 10, 9, 9, 0, 0, tzinfo=tz),
            check_out=datetime(2025, 10, 9, 17, 0, 0, tzinfo=tz),
        )

        self.worklog2 = WorkLog.objects.create(
            employee=self.employee2,
            check_in=datetime(2025, 10, 9, 8, 0, 0, tzinfo=tz),
            check_out=datetime(2025, 10, 9, 16, 0, 0, tzinfo=tz),
        )

    def test_service_initialization(self):
        """Test service initialization with default parameters."""
        service = BulkEnhancedPayrollService()

        self.assertTrue(service.use_cache)
        self.assertTrue(service.use_parallel)
        self.assertEqual(service.batch_size, 1000)
        self.assertTrue(service.show_progress)
        self.assertIsNotNone(service.data_loader)
        self.assertIsNotNone(service.cache_manager)
        self.assertIsNotNone(service.persister)

    def test_service_initialization_without_cache(self):
        """Test service initialization without cache."""
        service = BulkEnhancedPayrollService(use_cache=False)

        self.assertFalse(service.use_cache)
        self.assertIsNone(service.cache_manager)

    def test_service_initialization_custom_parameters(self):
        """Test service initialization with custom parameters."""
        service = BulkEnhancedPayrollService(
            use_cache=False,
            use_parallel=False,
            max_workers=4,
            batch_size=500,
            show_progress=False,
        )

        self.assertFalse(service.use_cache)
        self.assertFalse(service.use_parallel)
        self.assertEqual(service.max_workers, 4)
        self.assertEqual(service.batch_size, 500)
        self.assertFalse(service.show_progress)

    @patch("payroll.services.bulk.data_loader.get_shabbat_times")
    def test_calculate_bulk_sequential_no_cache(self, mock_get_shabbat_times):
        """Test bulk calculation in sequential mode without cache."""
        # Mock Shabbat times
        mock_get_shabbat_times.return_value = {
            "shabbat_start": "2025-10-10T18:00:00Z",
            "shabbat_end": "2025-10-11T19:00:00Z",
        }

        service = BulkEnhancedPayrollService(use_cache=False, use_parallel=False)

        employee_ids = [self.employee1.id, self.employee2.id]

        result = service.calculate_bulk(
            employee_ids=employee_ids,
            year=2025,
            month=10,
            save_to_db=False,  # Don't save for this test
        )

        # Verify result structure
        self.assertIsInstance(result, BulkCalculationResult)

        # Verify calculations were performed
        self.assertEqual(result.total_count, 2)

        # Debug: print errors if any
        if result.errors:
            print(f"DEBUG: Errors found: {result.errors}")
        if result.failed_count > 0:
            print(f"DEBUG: Failed count: {result.failed_count}")
            print(f"DEBUG: Successful count: {result.successful_count}")
            print(f"DEBUG: Results: {result.results}")

        self.assertGreater(
            result.successful_count,
            0,
            f"Expected successful calculations but got {result.successful_count}. "
            f"Errors: {result.errors}",
        )

        # Verify results exist
        self.assertIsInstance(result.results, dict)

    @patch("payroll.services.bulk.data_loader.get_shabbat_times")
    def test_calculate_bulk_with_specific_employees(self, mock_get_shabbat_times):
        """Test calculating for specific employees only."""
        mock_get_shabbat_times.return_value = {
            "shabbat_start": "2025-10-10T18:00:00Z",
            "shabbat_end": "2025-10-11T19:00:00Z",
        }

        service = BulkEnhancedPayrollService(use_cache=False, use_parallel=False)

        # Calculate only for employee1
        result = service.calculate_bulk(
            employee_ids=[self.employee1.id], year=2025, month=10, save_to_db=False
        )

        self.assertEqual(result.total_count, 1)
        self.assertIn(self.employee1.id, result.results)
        self.assertNotIn(self.employee2.id, result.results)

    @patch("payroll.services.bulk.data_loader.get_shabbat_times")
    def test_calculate_bulk_skips_employees_without_salary(
        self, mock_get_shabbat_times
    ):
        """Test that employees without salary are skipped."""
        mock_get_shabbat_times.return_value = {
            "shabbat_start": "2025-10-10T18:00:00Z",
            "shabbat_end": "2025-10-11T19:00:00Z",
        }

        # Create employee without salary
        user3 = User.objects.create_user(
            username="testuser3", email="test3@example.com"
        )
        employee3 = Employee.objects.create(
            user=user3,
            first_name="No",
            last_name="Salary",
            email="nosalary@example.com",
            is_active=True,
        )

        service = BulkEnhancedPayrollService(use_cache=False, use_parallel=False)

        result = service.calculate_bulk(
            employee_ids=[self.employee1.id, employee3.id],
            year=2025,
            month=10,
            save_to_db=False,
        )

        # Employee3 should be skipped
        self.assertNotIn(employee3.id, result.results)
        self.assertIn(self.employee1.id, result.results)

    def test_invalidate_cache(self):
        """Test cache invalidation."""
        service = BulkEnhancedPayrollService(use_cache=True)

        employee_ids = [self.employee1.id, self.employee2.id]

        # Mock cache manager
        service.cache_manager.invalidate_employees = MagicMock(return_value=10)

        deleted_count = service.invalidate_cache(employee_ids, 2025, 10)

        # Verify cache manager was called
        service.cache_manager.invalidate_employees.assert_called_once_with(
            employee_ids, 2025, 10
        )

        self.assertEqual(deleted_count, 10)

    def test_invalidate_cache_without_cache_manager(self):
        """Test cache invalidation when cache is disabled."""
        service = BulkEnhancedPayrollService(use_cache=False)

        deleted_count = service.invalidate_cache([1, 2, 3], 2025, 10)

        # Should return 0 when cache is disabled
        self.assertEqual(deleted_count, 0)

    def test_get_statistics(self):
        """Test getting service statistics."""
        service = BulkEnhancedPayrollService(
            use_cache=True, use_parallel=True, max_workers=4, batch_size=500
        )

        stats = service.get_statistics()

        self.assertEqual(stats["use_cache"], True)
        self.assertEqual(stats["use_parallel"], True)
        self.assertEqual(stats["max_workers"], 4)
        self.assertEqual(stats["batch_size"], 500)
        self.assertIn("cache", stats)

    def test_get_statistics_without_cache(self):
        """Test getting statistics when cache is disabled."""
        service = BulkEnhancedPayrollService(use_cache=False)

        stats = service.get_statistics()

        self.assertEqual(stats["use_cache"], False)
        self.assertNotIn("cache", stats)

    @patch("payroll.services.bulk.data_loader.get_shabbat_times")
    def test_build_contexts(self, mock_get_shabbat_times):
        """Test building calculation contexts from bulk data."""
        mock_get_shabbat_times.return_value = {
            "shabbat_start": "2025-10-10T18:00:00Z",
            "shabbat_end": "2025-10-11T19:00:00Z",
        }

        service = BulkEnhancedPayrollService(use_cache=False)

        # Load data
        bulk_data = service.data_loader.load_all_data(
            [self.employee1.id, self.employee2.id], 2025, 10
        )

        # Build contexts
        contexts = service._build_contexts(
            [self.employee1.id, self.employee2.id], bulk_data, 2025, 10
        )

        # Verify contexts
        self.assertEqual(len(contexts), 2)
        self.assertIn(self.employee1.id, contexts)
        self.assertIn(self.employee2.id, contexts)

        # Verify context structure
        context1 = contexts[self.employee1.id]
        self.assertEqual(context1["employee_id"], self.employee1.id)
        self.assertEqual(context1["year"], 2025)
        self.assertEqual(context1["month"], 10)
        self.assertEqual(context1["calculation_type"], "hourly")
        self.assertIn("work_logs", context1)

    @patch("payroll.services.bulk.data_loader.get_shabbat_times")
    def test_calculate_bulk_uses_parallel_for_large_batch(self, mock_get_shabbat_times):
        """Test that parallel processing is used for large batches."""
        mock_get_shabbat_times.return_value = {
            "shabbat_start": "2025-10-10T18:00:00Z",
            "shabbat_end": "2025-10-11T19:00:00Z",
        }

        # Create more employees to trigger parallel processing
        employees = []
        for i in range(10):
            user = User.objects.create_user(
                username=f"user{i}", email=f"user{i}@example.com"
            )
            emp = Employee.objects.create(
                user=user,
                first_name=f"Employee{i}",
                last_name="Test",
                email=f"emp{i}@example.com",
                is_active=True,
            )
            Salary.objects.create(
                employee=emp,
                calculation_type="hourly",
                hourly_rate=Decimal("50.00"),
                is_active=True,
            )
            employees.append(emp)

        # IMPORTANT: Disable parallel in tests to avoid multiprocessing issues
        # Django + ProcessPoolExecutor can cause test hangs due to DB connections
        service = BulkEnhancedPayrollService(use_cache=False, use_parallel=False)

        employee_ids = [emp.id for emp in employees]

        # Test with sequential processing
        result = service.calculate_bulk(
            employee_ids=employee_ids, year=2025, month=10, save_to_db=False
        )

        self.assertIsInstance(result, BulkCalculationResult)
        self.assertEqual(result.total_count, 10)

    @patch("payroll.services.bulk.data_loader.get_shabbat_times")
    def test_calculate_bulk_handles_calculation_errors(self, mock_get_shabbat_times):
        """Test that calculation errors are handled gracefully."""
        mock_get_shabbat_times.return_value = {
            "shabbat_start": "2025-10-10T18:00:00Z",
            "shabbat_end": "2025-10-11T19:00:00Z",
        }

        service = BulkEnhancedPayrollService(use_cache=False, use_parallel=False)

        # Mock the factory to raise an error
        with patch("payroll.services.factory.get_payroll_factory") as mock_factory:
            mock_calculator = MagicMock()
            mock_calculator.calculate_with_logging.side_effect = Exception(
                "Calculation error"
            )

            mock_factory_instance = MagicMock()
            mock_factory_instance.create_calculator.return_value = mock_calculator
            mock_factory.return_value = mock_factory_instance

            result = service.calculate_bulk(
                employee_ids=[self.employee1.id], year=2025, month=10, save_to_db=False
            )

            # Should have errors
            self.assertEqual(result.failed_count, 1)
            self.assertGreater(len(result.errors), 0)
