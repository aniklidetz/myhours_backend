"""
Progress reporter for bulk payroll calculations.

This module provides real-time progress tracking, statistics collection,
and performance monitoring for bulk payroll operations.

Key features:
- Real-time progress bar using tqdm
- Statistics collection (success/failure counts, timing)
- Detailed error logging
- Performance metrics (calculations/second, avg time)
- Export capabilities (JSON/CSV reports)
"""

import csv
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from tqdm import tqdm

    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    tqdm = None

from .types import EmployeeCalculationError

logger = logging.getLogger(__name__)


@dataclass
class ProgressStats:
    """Statistics for bulk calculation progress."""

    total_employees: int = 0
    completed: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0

    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # Performance
    total_records_saved: int = 0
    total_queries: int = 0
    cache_hits: int = 0
    cache_misses: int = 0

    # Errors
    errors: List[EmployeeCalculationError] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        """Calculate total duration in seconds."""
        if not self.start_time:
            return 0.0

        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()

    @property
    def calculations_per_second(self) -> float:
        """Calculate calculations per second."""
        if self.duration_seconds <= 0:
            return 0.0
        return self.completed / self.duration_seconds

    @property
    def avg_time_per_employee(self) -> float:
        """Calculate average time per employee in seconds."""
        if self.completed <= 0:
            return 0.0
        return self.duration_seconds / self.completed

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.completed <= 0:
            return 0.0
        return (self.successful / self.completed) * 100

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate as percentage."""
        total_cache_ops = self.cache_hits + self.cache_misses
        if total_cache_ops <= 0:
            return 0.0
        return (self.cache_hits / total_cache_ops) * 100

    @property
    def is_complete(self) -> bool:
        """Check if all employees have been processed."""
        return self.completed >= self.total_employees

    @property
    def estimated_time_remaining(self) -> Optional[float]:
        """Estimate remaining time in seconds."""
        if self.completed <= 0 or self.is_complete:
            return None

        remaining = self.total_employees - self.completed
        return remaining * self.avg_time_per_employee

    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary for JSON export."""
        data = asdict(self)

        # Convert datetime to ISO format
        if self.start_time:
            data["start_time"] = self.start_time.isoformat()
        if self.end_time:
            data["end_time"] = self.end_time.isoformat()

        # Add computed metrics
        data["duration_seconds"] = self.duration_seconds
        data["calculations_per_second"] = self.calculations_per_second
        data["avg_time_per_employee"] = self.avg_time_per_employee
        data["success_rate"] = self.success_rate
        data["cache_hit_rate"] = self.cache_hit_rate
        data["estimated_time_remaining"] = self.estimated_time_remaining

        return data


class ProgressReporter:
    """
    Progress reporter for bulk payroll calculations.

    This class provides real-time progress tracking and statistics
    collection for bulk operations.

    Features:
    - Real-time progress bar (if tqdm available)
    - Statistics collection and reporting
    - Error tracking and logging
    - Performance metrics
    - Export to JSON/CSV
    """

    def __init__(
        self,
        total_employees: int,
        show_progress_bar: bool = True,
        log_level: int = logging.INFO,
    ):
        """
        Initialize progress reporter.

        Args:
            total_employees: Total number of employees to process
            show_progress_bar: Show tqdm progress bar (if available)
            log_level: Logging level for progress messages
        """
        self.stats = ProgressStats(total_employees=total_employees)
        self.show_progress_bar = show_progress_bar and TQDM_AVAILABLE
        self.log_level = log_level

        self._progress_bar = None
        self._last_update_time = None

    def start(self):
        """Start progress tracking."""
        self.stats.start_time = datetime.now()
        self._last_update_time = self.stats.start_time

        logger.log(
            self.log_level,
            f"Starting bulk calculation for {self.stats.total_employees} employees",
            extra={
                "total_employees": self.stats.total_employees,
                "action": "bulk_calculation_start",
            },
        )

        # Initialize progress bar if enabled
        if self.show_progress_bar:
            self._progress_bar = tqdm(
                total=self.stats.total_employees,
                desc="Calculating payroll",
                unit="employee",
                ncols=100,
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
            )

    def update(
        self,
        employee_id: int,
        status: str = "success",
        error: Optional[Exception] = None,
    ):
        """
        Update progress for a single employee.

        Args:
            employee_id: Employee ID that was processed
            status: Status of calculation ("success", "error", "skipped")
            error: Exception if calculation failed
        """
        self.stats.completed += 1

        if status == "success":
            self.stats.successful += 1
        elif status == "error":
            self.stats.failed += 1
            if error:
                self.stats.errors.append(
                    EmployeeCalculationError(
                        employee_id=employee_id,
                        error_type=type(error).__name__,
                        error_message=str(error),
                        timestamp=datetime.now(),
                    )
                )
        elif status == "skipped":
            self.stats.skipped += 1

        # Update progress bar
        if self._progress_bar:
            self._progress_bar.update(1)

            # Update description with stats
            success_rate = self.stats.success_rate
            self._progress_bar.set_postfix(
                {"success": f"{success_rate:.1f}%", "failed": self.stats.failed}
            )

        # Log periodic updates (every 10% or every 100 employees)
        if self._should_log_update():
            self._log_progress()

    def _should_log_update(self) -> bool:
        """Check if we should log a progress update."""
        # Log every 10% completion
        progress_percentage = (self.stats.completed / self.stats.total_employees) * 100

        # Log at 10%, 20%, 30%, etc.
        if progress_percentage % 10 < (100 / self.stats.total_employees):
            return True

        # Or log every 100 employees
        if self.stats.completed % 100 == 0:
            return True

        return False

    def _log_progress(self):
        """Log current progress."""
        logger.log(
            self.log_level,
            f"Progress: {self.stats.completed}/{self.stats.total_employees} "
            f"({self.stats.success_rate:.1f}% success, {self.stats.failed} failed)",
            extra={
                "completed": self.stats.completed,
                "total": self.stats.total_employees,
                "successful": self.stats.successful,
                "failed": self.stats.failed,
                "success_rate": self.stats.success_rate,
                "calculations_per_second": self.stats.calculations_per_second,
                "action": "bulk_calculation_progress",
            },
        )

    def finish(self):
        """Finish progress tracking."""
        self.stats.end_time = datetime.now()

        # Close progress bar
        if self._progress_bar:
            self._progress_bar.close()
            self._progress_bar = None

        # Log final summary
        self._log_summary()

    def _log_summary(self):
        """Log final summary."""
        logger.log(
            self.log_level,
            f"Bulk calculation completed: {self.stats.successful} successful, "
            f"{self.stats.failed} failed, {self.stats.skipped} skipped "
            f"in {self.stats.duration_seconds:.2f}s "
            f"({self.stats.calculations_per_second:.2f} calc/s)",
            extra={
                "total_employees": self.stats.total_employees,
                "successful": self.stats.successful,
                "failed": self.stats.failed,
                "skipped": self.stats.skipped,
                "duration_seconds": self.stats.duration_seconds,
                "calculations_per_second": self.stats.calculations_per_second,
                "avg_time_per_employee": self.stats.avg_time_per_employee,
                "success_rate": self.stats.success_rate,
                "total_records_saved": self.stats.total_records_saved,
                "cache_hit_rate": self.stats.cache_hit_rate,
                "action": "bulk_calculation_complete",
            },
        )

        # Log errors if any
        if self.stats.errors:
            logger.warning(
                f"Encountered {len(self.stats.errors)} errors during bulk calculation",
                extra={
                    "error_count": len(self.stats.errors),
                    "action": "bulk_calculation_errors",
                },
            )

            # Log first few errors in detail
            for error in self.stats.errors[:5]:
                logger.error(
                    f"Employee {error.employee_id}: {error.error_type} - {error.error_message}",
                    extra={
                        "employee_id": error.employee_id,
                        "error_type": error.error_type,
                        "error_message": error.error_message,
                        "action": "employee_calculation_error",
                    },
                )

    def update_cache_stats(self, hits: int, misses: int):
        """Update cache statistics."""
        self.stats.cache_hits = hits
        self.stats.cache_misses = misses

    def update_save_stats(self, records_saved: int):
        """Update database save statistics."""
        self.stats.total_records_saved += records_saved

    def get_stats(self) -> ProgressStats:
        """Get current statistics."""
        return self.stats

    def export_to_json(self, output_path: Path) -> bool:
        """
        Export statistics to JSON file.

        Args:
            output_path: Path to output JSON file

        Returns:
            bool: True if export successful
        """
        try:
            with open(output_path, "w") as f:
                json.dump(self.stats.to_dict(), f, indent=2, default=str)

            logger.info(
                f"Exported statistics to {output_path}",
                extra={"output_path": str(output_path), "action": "stats_export_json"},
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to export statistics to JSON: {e}",
                extra={
                    "error": str(e),
                    "output_path": str(output_path),
                    "action": "stats_export_error",
                },
                exc_info=True,
            )
            return False

    def export_errors_to_csv(self, output_path: Path) -> bool:
        """
        Export error details to CSV file.

        Args:
            output_path: Path to output CSV file

        Returns:
            bool: True if export successful
        """
        if not self.stats.errors:
            logger.info("No errors to export")
            return True

        try:
            with open(output_path, "w", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "employee_id",
                        "error_type",
                        "error_message",
                        "timestamp",
                    ],
                )
                writer.writeheader()

                for error in self.stats.errors:
                    writer.writerow(
                        {
                            "employee_id": error.employee_id,
                            "error_type": error.error_type,
                            "error_message": error.error_message,
                            "timestamp": error.timestamp.isoformat(),
                        }
                    )

            logger.info(
                f"Exported {len(self.stats.errors)} errors to {output_path}",
                extra={
                    "error_count": len(self.stats.errors),
                    "output_path": str(output_path),
                    "action": "errors_export_csv",
                },
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to export errors to CSV: {e}",
                extra={
                    "error": str(e),
                    "output_path": str(output_path),
                    "action": "errors_export_error",
                },
                exc_info=True,
            )
            return False

    def get_summary_report(self) -> str:
        """
        Get human-readable summary report.

        Returns:
            str: Formatted summary report
        """
        report_lines = [
            "=" * 60,
            "Bulk Payroll Calculation Summary",
            "=" * 60,
            f"Total Employees: {self.stats.total_employees}",
            f"Completed: {self.stats.completed}",
            f"  - Successful: {self.stats.successful} ({self.stats.success_rate:.1f}%)",
            f"  - Failed: {self.stats.failed}",
            f"  - Skipped: {self.stats.skipped}",
            "",
            "Performance:",
            f"  - Duration: {self.stats.duration_seconds:.2f}s",
            f"  - Calculations/sec: {self.stats.calculations_per_second:.2f}",
            f"  - Avg time/employee: {self.stats.avg_time_per_employee:.3f}s",
            "",
            "Database:",
            f"  - Records saved: {self.stats.total_records_saved}",
            f"  - Total queries: {self.stats.total_queries}",
            "",
            "Cache:",
            f"  - Hit rate: {self.stats.cache_hit_rate:.1f}%",
            f"  - Hits: {self.stats.cache_hits}",
            f"  - Misses: {self.stats.cache_misses}",
            "=" * 60,
        ]

        return "\n".join(report_lines)

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.finish()
        return False
