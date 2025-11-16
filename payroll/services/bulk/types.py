"""
Type definitions for bulk payroll operations.

This module defines all data structures used in bulk payroll calculations,
ensuring type safety and clear contracts between components.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from payroll.services.contracts import PayrollResult


class ProcessingStatus(Enum):
    """Status of bulk processing operation."""

    PENDING = "pending"
    LOADING_DATA = "loading_data"
    CHECKING_CACHE = "checking_cache"
    CALCULATING = "calculating"
    PERSISTING = "persisting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class EmployeeData:
    """
    Serializable employee data for multiprocessing.

    This is a lightweight, pickleable alternative to Django Employee model.
    Contains only the data needed for payroll calculations.
    """

    employee_id: int
    user_id: int
    first_name: str
    last_name: str

    # Salary info
    salary_id: int
    calculation_type: str  # 'hourly' or 'monthly'
    hourly_rate: Optional[Decimal] = None
    base_salary: Optional[Decimal] = None
    is_active: bool = True

    def __repr__(self):
        return f"EmployeeData(id={self.employee_id}, name={self.first_name} {self.last_name}, type={self.calculation_type})"


@dataclass
class WorkLogData:
    """
    Serializable work log data for multiprocessing.

    Lightweight alternative to Django WorkLog model.
    """

    worklog_id: int
    employee_id: int
    check_in: datetime
    check_out: datetime
    work_date: date

    @property
    def total_hours(self) -> Decimal:
        """Calculate total hours worked."""
        if not self.check_out:
            return Decimal("0")
        duration = self.check_out - self.check_in
        return Decimal(str(duration.total_seconds() / 3600))

    def __repr__(self):
        return f"WorkLogData(id={self.worklog_id}, employee={self.employee_id}, date={self.work_date}, hours={self.total_hours})"


@dataclass
class HolidayData:
    """Serializable holiday data."""

    date: date
    name: str
    is_paid: bool = True
    source: str = "database"


@dataclass
class ShabbatTimesData:
    """Serializable Shabbat times data."""

    friday_date: date
    shabbat_start: datetime
    shabbat_end: datetime
    source: str = "api"


@dataclass
class BulkLoadedData:
    """
    Container for all bulk-loaded data.

    This structure holds all data loaded by BulkDataLoader,
    organized for efficient access during parallel processing.
    """

    employees: Dict[int, EmployeeData]
    work_logs: Dict[int, List[WorkLogData]]  # Keyed by employee_id
    holidays: Dict[date, HolidayData]
    shabbat_times: Dict[date, ShabbatTimesData]  # Keyed by Friday date

    year: int
    month: int

    def get_employee(self, employee_id: int) -> Optional[EmployeeData]:
        """Get employee data by ID."""
        return self.employees.get(employee_id)

    def get_work_logs(self, employee_id: int) -> List[WorkLogData]:
        """Get work logs for employee."""
        return self.work_logs.get(employee_id, [])

    def __repr__(self):
        return (
            f"BulkLoadedData(employees={len(self.employees)}, "
            f"work_logs={sum(len(logs) for logs in self.work_logs.values())}, "
            f"holidays={len(self.holidays)}, period={self.year}-{self.month})"
        )


@dataclass
class EmployeeCalculationError:
    """Details about a calculation error for a specific employee."""

    employee_id: int
    error_type: str
    error_message: str
    traceback: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class BulkCalculationResult:
    """
    Result of bulk payroll calculation operation.

    Contains all calculated results, statistics, and error information.
    """

    # Results by employee_id
    results: Dict[int, PayrollResult]

    # Errors by employee_id
    errors: Dict[int, EmployeeCalculationError]

    # Statistics
    total_count: int
    successful_count: int
    failed_count: int
    cached_count: int
    calculated_count: int

    # Performance metrics
    duration_seconds: float
    start_time: datetime
    end_time: datetime

    # Cache statistics
    cache_hit_rate: float  # Percentage

    # Database statistics
    db_queries_count: int = 0

    # Processing details
    status: ProcessingStatus = ProcessingStatus.COMPLETED

    def get_successful_results(self) -> Dict[int, PayrollResult]:
        """Get only successful calculation results."""
        return {
            emp_id: result
            for emp_id, result in self.results.items()
            if emp_id not in self.errors
        }

    def get_failed_employee_ids(self) -> List[int]:
        """Get list of employee IDs that failed."""
        return list(self.errors.keys())

    def get_detailed_report(self) -> "BulkCalculationSummary":
        """Generate detailed summary report."""
        return BulkCalculationSummary(
            total_employees=self.total_count,
            successful=self.successful_count,
            failed=self.failed_count,
            cached=self.cached_count,
            calculated=self.calculated_count,
            duration_seconds=self.duration_seconds,
            cache_hit_rate=self.cache_hit_rate,
            db_queries=self.db_queries_count,
            avg_time_per_employee=(
                self.duration_seconds / self.total_count if self.total_count > 0 else 0
            ),
            errors=[
                {
                    "employee_id": emp_id,
                    "error_type": err.error_type,
                    "error_message": err.error_message,
                }
                for emp_id, err in self.errors.items()
            ],
        )

    def __repr__(self):
        return (
            f"BulkCalculationResult(total={self.total_count}, "
            f"successful={self.successful_count}, failed={self.failed_count}, "
            f"cached={self.cached_count}, duration={self.duration_seconds:.2f}s)"
        )


@dataclass
class BulkCalculationSummary:
    """
    Detailed summary of bulk calculation operation.

    Used for reporting and monitoring.
    """

    total_employees: int
    successful: int
    failed: int
    cached: int
    calculated: int

    duration_seconds: float
    cache_hit_rate: float
    db_queries: int
    avg_time_per_employee: float

    errors: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_employees": self.total_employees,
            "successful": self.successful,
            "failed": self.failed,
            "cached": self.cached,
            "calculated": self.calculated,
            "duration_seconds": self.duration_seconds,
            "cache_hit_rate": self.cache_hit_rate,
            "db_queries": self.db_queries,
            "avg_time_per_employee": self.avg_time_per_employee,
            "errors": self.errors,
        }

    def __repr__(self):
        success_rate = (
            (self.successful / self.total_employees * 100)
            if self.total_employees > 0
            else 0
        )
        return (
            f"BulkCalculationSummary(employees={self.total_employees}, "
            f"success_rate={success_rate:.1f}%, cache_hit={self.cache_hit_rate:.1f}%, "
            f"duration={self.duration_seconds:.2f}s)"
        )


@dataclass
class BulkSaveResult:
    """
    Result of bulk save operation.

    Contains information about persisted records.
    """

    monthly_summaries_created: int = 0
    monthly_summaries_updated: int = 0
    daily_calculations_created: int = 0
    compensatory_days_created: int = 0

    errors: List[Dict[str, Any]] = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def total_records(self) -> int:
        """Total number of records created/updated."""
        return (
            self.monthly_summaries_created
            + self.monthly_summaries_updated
            + self.daily_calculations_created
            + self.compensatory_days_created
        )

    def __repr__(self):
        return (
            f"BulkSaveResult(monthly={self.monthly_summaries_created + self.monthly_summaries_updated}, "
            f"daily={self.daily_calculations_created}, "
            f"compensatory={self.compensatory_days_created}, "
            f"duration={self.duration_seconds:.2f}s)"
        )


@dataclass
class CacheStats:
    """Cache operation statistics."""

    total_keys: int = 0
    hits: int = 0
    misses: int = 0
    sets: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate percentage."""
        if self.total_keys == 0:
            return 0.0
        return (self.hits / self.total_keys) * 100

    def __repr__(self):
        return f"CacheStats(keys={self.total_keys}, hits={self.hits}, misses={self.misses}, hit_rate={self.hit_rate:.1f}%)"
