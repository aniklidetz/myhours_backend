"""
Tests for ProgressReporter.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import TestCase

from payroll.services.bulk.progress_reporter import ProgressReporter, ProgressStats
from payroll.services.bulk.types import EmployeeCalculationError


class ProgressStatsTestCase(TestCase):
    """Tests for ProgressStats dataclass."""

    def test_progress_stats_initialization(self):
        """Test ProgressStats initialization."""
        stats = ProgressStats(total_employees=100)

        self.assertEqual(stats.total_employees, 100)
        self.assertEqual(stats.completed, 0)
        self.assertEqual(stats.successful, 0)
        self.assertEqual(stats.failed, 0)
        self.assertEqual(stats.skipped, 0)
        self.assertIsNone(stats.start_time)
        self.assertIsNone(stats.end_time)

    def test_duration_seconds(self):
        """Test duration calculation."""
        stats = ProgressStats()
        stats.start_time = datetime(2025, 10, 9, 10, 0, 0)
        stats.end_time = datetime(2025, 10, 9, 10, 5, 30)

        self.assertEqual(stats.duration_seconds, 330.0)  # 5 minutes 30 seconds

    def test_duration_seconds_without_end_time(self):
        """Test duration calculation uses current time if end_time is None."""
        stats = ProgressStats()
        stats.start_time = datetime.now()

        # Duration should be very small (just now)
        self.assertLess(stats.duration_seconds, 1.0)

    def test_calculations_per_second(self):
        """Test calculations per second metric."""
        stats = ProgressStats()
        stats.start_time = datetime(2025, 10, 9, 10, 0, 0)
        stats.end_time = datetime(2025, 10, 9, 10, 1, 0)  # 1 minute = 60 seconds
        stats.completed = 120

        self.assertEqual(stats.calculations_per_second, 2.0)  # 120 / 60

    def test_avg_time_per_employee(self):
        """Test average time per employee metric."""
        stats = ProgressStats()
        stats.start_time = datetime(2025, 10, 9, 10, 0, 0)
        stats.end_time = datetime(2025, 10, 9, 10, 1, 0)  # 60 seconds
        stats.completed = 10

        self.assertEqual(stats.avg_time_per_employee, 6.0)  # 60 / 10

    def test_success_rate(self):
        """Test success rate calculation."""
        stats = ProgressStats()
        stats.completed = 100
        stats.successful = 95

        self.assertEqual(stats.success_rate, 95.0)

    def test_cache_hit_rate(self):
        """Test cache hit rate calculation."""
        stats = ProgressStats()
        stats.cache_hits = 80
        stats.cache_misses = 20

        self.assertEqual(stats.cache_hit_rate, 80.0)

    def test_is_complete(self):
        """Test completion check."""
        stats = ProgressStats(total_employees=100)
        stats.completed = 50

        self.assertFalse(stats.is_complete)

        stats.completed = 100
        self.assertTrue(stats.is_complete)

    def test_estimated_time_remaining(self):
        """Test estimated time remaining calculation."""
        stats = ProgressStats(total_employees=100)
        stats.completed = 25
        stats.start_time = datetime(2025, 10, 9, 10, 0, 0)
        stats.end_time = datetime(2025, 10, 9, 10, 1, 0)  # 60 seconds for 25 employees

        # Average time per employee = 60 / 25 = 2.4 seconds
        # Remaining = 75 employees * 2.4 = 180 seconds
        self.assertEqual(stats.estimated_time_remaining, 180.0)

    def test_to_dict(self):
        """Test conversion to dictionary."""
        stats = ProgressStats(total_employees=100)
        stats.completed = 50
        stats.successful = 48
        stats.failed = 2
        stats.start_time = datetime(2025, 10, 9, 10, 0, 0)

        data = stats.to_dict()

        self.assertIsInstance(data, dict)
        self.assertEqual(data["total_employees"], 100)
        self.assertEqual(data["completed"], 50)
        self.assertEqual(data["successful"], 48)
        self.assertEqual(data["failed"], 2)
        self.assertIn("start_time", data)
        self.assertIn("duration_seconds", data)
        self.assertIn("calculations_per_second", data)


class ProgressReporterTestCase(TestCase):
    """Tests for ProgressReporter class."""

    def test_reporter_initialization(self):
        """Test reporter initialization."""
        reporter = ProgressReporter(total_employees=100)

        self.assertEqual(reporter.stats.total_employees, 100)
        # show_progress_bar may be False if tqdm is not available
        self.assertIsInstance(reporter.show_progress_bar, bool)
        self.assertIsNone(reporter._progress_bar)

    def test_reporter_start(self):
        """Test starting progress tracking."""
        reporter = ProgressReporter(total_employees=100, show_progress_bar=False)

        reporter.start()

        self.assertIsNotNone(reporter.stats.start_time)
        self.assertIsNotNone(reporter._last_update_time)

    def test_reporter_update_success(self):
        """Test updating progress with success."""
        reporter = ProgressReporter(total_employees=100, show_progress_bar=False)
        reporter.start()

        reporter.update(employee_id=1, status="success")

        self.assertEqual(reporter.stats.completed, 1)
        self.assertEqual(reporter.stats.successful, 1)
        self.assertEqual(reporter.stats.failed, 0)

    def test_reporter_update_error(self):
        """Test updating progress with error."""
        reporter = ProgressReporter(total_employees=100, show_progress_bar=False)
        reporter.start()

        error = ValueError("Test error")
        reporter.update(employee_id=1, status="error", error=error)

        self.assertEqual(reporter.stats.completed, 1)
        self.assertEqual(reporter.stats.successful, 0)
        self.assertEqual(reporter.stats.failed, 1)
        self.assertEqual(len(reporter.stats.errors), 1)

        # Check error details
        error_record = reporter.stats.errors[0]
        self.assertEqual(error_record.employee_id, 1)
        self.assertEqual(error_record.error_type, "ValueError")
        self.assertEqual(error_record.error_message, "Test error")

    def test_reporter_update_skipped(self):
        """Test updating progress with skipped."""
        reporter = ProgressReporter(total_employees=100, show_progress_bar=False)
        reporter.start()

        reporter.update(employee_id=1, status="skipped")

        self.assertEqual(reporter.stats.completed, 1)
        self.assertEqual(reporter.stats.successful, 0)
        self.assertEqual(reporter.stats.skipped, 1)

    def test_reporter_finish(self):
        """Test finishing progress tracking."""
        reporter = ProgressReporter(total_employees=10, show_progress_bar=False)
        reporter.start()

        for i in range(10):
            reporter.update(employee_id=i, status="success")

        reporter.finish()

        self.assertIsNotNone(reporter.stats.end_time)
        self.assertGreater(reporter.stats.duration_seconds, 0)

    def test_reporter_update_cache_stats(self):
        """Test updating cache statistics."""
        reporter = ProgressReporter(total_employees=100, show_progress_bar=False)

        reporter.update_cache_stats(hits=80, misses=20)

        self.assertEqual(reporter.stats.cache_hits, 80)
        self.assertEqual(reporter.stats.cache_misses, 20)
        self.assertEqual(reporter.stats.cache_hit_rate, 80.0)

    def test_reporter_update_save_stats(self):
        """Test updating save statistics."""
        reporter = ProgressReporter(total_employees=100, show_progress_bar=False)

        reporter.update_save_stats(records_saved=50)
        reporter.update_save_stats(records_saved=30)

        self.assertEqual(reporter.stats.total_records_saved, 80)

    def test_reporter_get_stats(self):
        """Test getting current statistics."""
        reporter = ProgressReporter(total_employees=100, show_progress_bar=False)
        reporter.start()

        stats = reporter.get_stats()

        self.assertIsInstance(stats, ProgressStats)
        self.assertEqual(stats.total_employees, 100)

    def test_export_to_json(self):
        """Test exporting statistics to JSON."""
        reporter = ProgressReporter(total_employees=10, show_progress_bar=False)
        reporter.start()

        for i in range(10):
            reporter.update(employee_id=i, status="success")

        reporter.finish()

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            output_path = Path(f.name)

        try:
            success = reporter.export_to_json(output_path)

            self.assertTrue(success)
            self.assertTrue(output_path.exists())

            # Read and verify JSON
            with open(output_path, "r") as f:
                data = json.load(f)

            self.assertEqual(data["total_employees"], 10)
            self.assertEqual(data["successful"], 10)

        finally:
            # Cleanup
            if output_path.exists():
                output_path.unlink()

    def test_export_errors_to_csv(self):
        """Test exporting errors to CSV."""
        reporter = ProgressReporter(total_employees=10, show_progress_bar=False)
        reporter.start()

        # Add some errors
        for i in range(3):
            error = ValueError(f"Error {i}")
            reporter.update(employee_id=i, status="error", error=error)

        reporter.finish()

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            output_path = Path(f.name)

        try:
            success = reporter.export_errors_to_csv(output_path)

            self.assertTrue(success)
            self.assertTrue(output_path.exists())

            # Read and verify CSV
            import csv

            with open(output_path, "r") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["employee_id"], "0")
            self.assertEqual(rows[0]["error_type"], "ValueError")

        finally:
            # Cleanup
            if output_path.exists():
                output_path.unlink()

    def test_export_errors_to_csv_no_errors(self):
        """Test exporting when there are no errors."""
        reporter = ProgressReporter(total_employees=10, show_progress_bar=False)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            output_path = Path(f.name)

        try:
            success = reporter.export_errors_to_csv(output_path)

            # Should return True even with no errors
            self.assertTrue(success)

        finally:
            if output_path.exists():
                output_path.unlink()

    def test_get_summary_report(self):
        """Test getting human-readable summary report."""
        reporter = ProgressReporter(total_employees=100, show_progress_bar=False)
        reporter.start()

        for i in range(95):
            reporter.update(employee_id=i, status="success")

        for i in range(95, 100):
            reporter.update(employee_id=i, status="error", error=ValueError("Test"))

        reporter.finish()

        report = reporter.get_summary_report()

        self.assertIsInstance(report, str)
        self.assertIn("Bulk Payroll Calculation Summary", report)
        self.assertIn("Total Employees: 100", report)
        self.assertIn("Successful: 95", report)
        self.assertIn("Failed: 5", report)

    def test_context_manager(self):
        """Test using reporter as context manager."""
        reporter = ProgressReporter(total_employees=10, show_progress_bar=False)

        with reporter:
            self.assertIsNotNone(reporter.stats.start_time)

            for i in range(10):
                reporter.update(employee_id=i, status="success")

        # After context exit, should be finished
        self.assertIsNotNone(reporter.stats.end_time)

    @patch("payroll.services.bulk.progress_reporter.TQDM_AVAILABLE", True)
    @patch("payroll.services.bulk.progress_reporter.tqdm")
    def test_progress_bar_with_tqdm(self, mock_tqdm_class):
        """Test progress bar updates with tqdm."""
        mock_progress_bar = MagicMock()
        mock_tqdm_class.return_value = mock_progress_bar

        reporter = ProgressReporter(total_employees=10, show_progress_bar=True)
        reporter.start()

        # Verify tqdm was created
        mock_tqdm_class.assert_called_once()

        # Update progress
        reporter.update(employee_id=1, status="success")

        # Verify progress bar was updated
        mock_progress_bar.update.assert_called_with(1)
        mock_progress_bar.set_postfix.assert_called_once()

        reporter.finish()

        # Verify progress bar was closed
        mock_progress_bar.close.assert_called_once()

    def test_should_log_update(self):
        """Test periodic logging logic."""
        reporter = ProgressReporter(total_employees=100, show_progress_bar=False)
        reporter.start()

        # Should log at 10% intervals
        reporter.stats.completed = 10
        self.assertTrue(reporter._should_log_update())

        # Should log every 100 employees
        reporter.stats.completed = 100
        self.assertTrue(reporter._should_log_update())
