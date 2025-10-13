"""
Tests for bulk payroll types.
"""

from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase

from payroll.services.bulk.types import (
    BulkCalculationResult,
    BulkCalculationSummary,
    BulkLoadedData,
    BulkSaveResult,
    CacheStats,
    EmployeeCalculationError,
    EmployeeData,
    HolidayData,
    ProcessingStatus,
    ShabbatTimesData,
    WorkLogData,
)


class EmployeeDataTestCase(TestCase):
    """Tests for EmployeeData dataclass."""

    def test_employee_data_creation(self):
        """Test creating EmployeeData instance."""
        emp_data = EmployeeData(
            employee_id=1,
            user_id=100,
            first_name="John",
            last_name="Doe",
            salary_id=10,
            calculation_type="hourly",
            hourly_rate=Decimal("50.00"),
            base_salary=None,
            is_active=True,
        )

        self.assertEqual(emp_data.employee_id, 1)
        self.assertEqual(emp_data.user_id, 100)
        self.assertEqual(emp_data.first_name, "John")
        self.assertEqual(emp_data.last_name, "Doe")
        self.assertEqual(emp_data.calculation_type, "hourly")
        self.assertEqual(emp_data.hourly_rate, Decimal("50.00"))
        self.assertIsNone(emp_data.base_salary)
        self.assertTrue(emp_data.is_active)

    def test_employee_data_repr(self):
        """Test EmployeeData string representation."""
        emp_data = EmployeeData(
            employee_id=1,
            user_id=100,
            first_name="John",
            last_name="Doe",
            salary_id=10,
            calculation_type="monthly",
            base_salary=Decimal("8000.00"),
        )

        repr_str = repr(emp_data)
        self.assertIn("EmployeeData", repr_str)
        self.assertIn("id=1", repr_str)
        self.assertIn("John Doe", repr_str)
        self.assertIn("monthly", repr_str)


class WorkLogDataTestCase(TestCase):
    """Tests for WorkLogData dataclass."""

    def test_worklog_data_creation(self):
        """Test creating WorkLogData instance."""
        check_in = datetime(2025, 10, 9, 9, 0, 0)
        check_out = datetime(2025, 10, 9, 17, 0, 0)

        log_data = WorkLogData(
            worklog_id=1,
            employee_id=10,
            check_in=check_in,
            check_out=check_out,
            work_date=date(2025, 10, 9),
        )

        self.assertEqual(log_data.worklog_id, 1)
        self.assertEqual(log_data.employee_id, 10)
        self.assertEqual(log_data.check_in, check_in)
        self.assertEqual(log_data.check_out, check_out)
        self.assertEqual(log_data.work_date, date(2025, 10, 9))

    def test_total_hours_calculation(self):
        """Test total hours calculation."""
        check_in = datetime(2025, 10, 9, 9, 0, 0)
        check_out = datetime(2025, 10, 9, 17, 0, 0)  # 8 hours

        log_data = WorkLogData(
            worklog_id=1,
            employee_id=10,
            check_in=check_in,
            check_out=check_out,
            work_date=date(2025, 10, 9),
        )

        self.assertEqual(log_data.total_hours, Decimal("8.0"))

    def test_total_hours_with_partial_hour(self):
        """Test total hours with partial hour."""
        check_in = datetime(2025, 10, 9, 9, 0, 0)
        check_out = datetime(2025, 10, 9, 17, 30, 0)  # 8.5 hours

        log_data = WorkLogData(
            worklog_id=1,
            employee_id=10,
            check_in=check_in,
            check_out=check_out,
            work_date=date(2025, 10, 9),
        )

        self.assertEqual(log_data.total_hours, Decimal("8.5"))


class BulkLoadedDataTestCase(TestCase):
    """Tests for BulkLoadedData dataclass."""

    def test_bulk_loaded_data_creation(self):
        """Test creating BulkLoadedData instance."""
        employees = {
            1: EmployeeData(
                employee_id=1,
                user_id=100,
                first_name="John",
                last_name="Doe",
                salary_id=10,
                calculation_type="hourly",
                hourly_rate=Decimal("50.00"),
            )
        }

        work_logs = {
            1: [
                WorkLogData(
                    worklog_id=1,
                    employee_id=1,
                    check_in=datetime(2025, 10, 9, 9, 0, 0),
                    check_out=datetime(2025, 10, 9, 17, 0, 0),
                    work_date=date(2025, 10, 9),
                )
            ]
        }

        holidays = {
            date(2025, 10, 10): HolidayData(
                date=date(2025, 10, 10), name="Yom Kippur", is_paid=True
            )
        }

        bulk_data = BulkLoadedData(
            employees=employees,
            work_logs=work_logs,
            holidays=holidays,
            shabbat_times={},
            year=2025,
            month=10,
        )

        self.assertEqual(len(bulk_data.employees), 1)
        self.assertEqual(len(bulk_data.work_logs), 1)
        self.assertEqual(len(bulk_data.holidays), 1)
        self.assertEqual(bulk_data.year, 2025)
        self.assertEqual(bulk_data.month, 10)

    def test_get_employee(self):
        """Test getting employee by ID."""
        emp_data = EmployeeData(
            employee_id=1,
            user_id=100,
            first_name="John",
            last_name="Doe",
            salary_id=10,
            calculation_type="hourly",
            hourly_rate=Decimal("50.00"),
        )

        bulk_data = BulkLoadedData(
            employees={1: emp_data},
            work_logs={},
            holidays={},
            shabbat_times={},
            year=2025,
            month=10,
        )

        retrieved_emp = bulk_data.get_employee(1)
        self.assertIsNotNone(retrieved_emp)
        self.assertEqual(retrieved_emp.employee_id, 1)

        # Test non-existent employee
        non_existent = bulk_data.get_employee(999)
        self.assertIsNone(non_existent)

    def test_get_work_logs(self):
        """Test getting work logs for employee."""
        log_data = WorkLogData(
            worklog_id=1,
            employee_id=1,
            check_in=datetime(2025, 10, 9, 9, 0, 0),
            check_out=datetime(2025, 10, 9, 17, 0, 0),
            work_date=date(2025, 10, 9),
        )

        bulk_data = BulkLoadedData(
            employees={},
            work_logs={1: [log_data]},
            holidays={},
            shabbat_times={},
            year=2025,
            month=10,
        )

        logs = bulk_data.get_work_logs(1)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].worklog_id, 1)

        # Test employee with no logs
        empty_logs = bulk_data.get_work_logs(999)
        self.assertEqual(len(empty_logs), 0)


class BulkCalculationResultTestCase(TestCase):
    """Tests for BulkCalculationResult dataclass."""

    def test_bulk_result_creation(self):
        """Test creating BulkCalculationResult."""
        start_time = datetime.now()
        end_time = datetime.now()

        result = BulkCalculationResult(
            results={1: {}, 2: {}},
            errors={},
            total_count=2,
            successful_count=2,
            failed_count=0,
            cached_count=0,
            calculated_count=2,
            duration_seconds=1.5,
            start_time=start_time,
            end_time=end_time,
            cache_hit_rate=0.0,
        )

        self.assertEqual(result.total_count, 2)
        self.assertEqual(result.successful_count, 2)
        self.assertEqual(result.failed_count, 0)
        self.assertEqual(result.duration_seconds, 1.5)

    def test_get_successful_results(self):
        """Test getting only successful results."""
        result = BulkCalculationResult(
            results={1: {"total_salary": 5000}, 2: {"total_salary": 6000}},
            errors={
                2: EmployeeCalculationError(
                    employee_id=2, error_type="ValueError", error_message="Test error"
                )
            },
            total_count=2,
            successful_count=1,
            failed_count=1,
            cached_count=0,
            calculated_count=1,
            duration_seconds=1.0,
            start_time=datetime.now(),
            end_time=datetime.now(),
            cache_hit_rate=0.0,
        )

        successful = result.get_successful_results()
        self.assertEqual(len(successful), 1)
        self.assertIn(1, successful)
        self.assertNotIn(2, successful)

    def test_get_failed_employee_ids(self):
        """Test getting failed employee IDs."""
        result = BulkCalculationResult(
            results={},
            errors={
                2: EmployeeCalculationError(
                    employee_id=2, error_type="ValueError", error_message="Test error"
                ),
                3: EmployeeCalculationError(
                    employee_id=3, error_type="TypeError", error_message="Another error"
                ),
            },
            total_count=3,
            successful_count=1,
            failed_count=2,
            cached_count=0,
            calculated_count=1,
            duration_seconds=1.0,
            start_time=datetime.now(),
            end_time=datetime.now(),
            cache_hit_rate=0.0,
        )

        failed_ids = result.get_failed_employee_ids()
        self.assertEqual(len(failed_ids), 2)
        self.assertIn(2, failed_ids)
        self.assertIn(3, failed_ids)

    def test_get_detailed_report(self):
        """Test generating detailed summary report."""
        result = BulkCalculationResult(
            results={1: {}},
            errors={},
            total_count=1,
            successful_count=1,
            failed_count=0,
            cached_count=0,
            calculated_count=1,
            duration_seconds=0.5,
            start_time=datetime.now(),
            end_time=datetime.now(),
            cache_hit_rate=0.0,
            db_queries_count=5,
        )

        summary = result.get_detailed_report()
        self.assertIsInstance(summary, BulkCalculationSummary)
        self.assertEqual(summary.total_employees, 1)
        self.assertEqual(summary.successful, 1)
        self.assertEqual(summary.failed, 0)
        self.assertEqual(summary.db_queries, 5)


class BulkCalculationSummaryTestCase(TestCase):
    """Tests for BulkCalculationSummary dataclass."""

    def test_summary_to_dict(self):
        """Test converting summary to dictionary."""
        summary = BulkCalculationSummary(
            total_employees=10,
            successful=9,
            failed=1,
            cached=3,
            calculated=6,
            duration_seconds=2.5,
            cache_hit_rate=30.0,
            db_queries=5,
            avg_time_per_employee=0.25,
            errors=[{"employee_id": 5, "error": "Test error"}],
        )

        summary_dict = summary.to_dict()
        self.assertEqual(summary_dict["total_employees"], 10)
        self.assertEqual(summary_dict["successful"], 9)
        self.assertEqual(summary_dict["failed"], 1)
        self.assertEqual(summary_dict["cached"], 3)
        self.assertEqual(summary_dict["cache_hit_rate"], 30.0)
        self.assertEqual(len(summary_dict["errors"]), 1)


class BulkSaveResultTestCase(TestCase):
    """Tests for BulkSaveResult dataclass."""

    def test_total_records_calculation(self):
        """Test total records calculation."""
        save_result = BulkSaveResult(
            monthly_summaries_created=5,
            monthly_summaries_updated=3,
            daily_calculations_created=150,
            compensatory_days_created=10,
            duration_seconds=0.5,
        )

        total = save_result.total_records
        self.assertEqual(total, 168)  # 5 + 3 + 150 + 10


class CacheStatsTestCase(TestCase):
    """Tests for CacheStats dataclass."""

    def test_hit_rate_calculation(self):
        """Test cache hit rate calculation."""
        stats = CacheStats(total_keys=100, hits=80, misses=20, sets=50)

        self.assertEqual(stats.hit_rate, 80.0)

    def test_hit_rate_with_zero_keys(self):
        """Test cache hit rate with zero keys."""
        stats = CacheStats()
        self.assertEqual(stats.hit_rate, 0.0)

    def test_hit_rate_repr(self):
        """Test CacheStats string representation."""
        stats = CacheStats(total_keys=100, hits=75, misses=25)

        repr_str = repr(stats)
        self.assertIn("CacheStats", repr_str)
        self.assertIn("keys=100", repr_str)
        self.assertIn("hits=75", repr_str)
        self.assertIn("hit_rate=75.0%", repr_str)
