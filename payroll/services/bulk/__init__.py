"""
Bulk payroll calculation services for high-performance mass processing.

This package provides optimized services for calculating payroll for large
numbers of employees simultaneously, with features including:
- Optimized database queries (prefetch, select_related)
- Parallel processing (multiprocessing/threading)
- Bulk caching (Redis pipeline)
- Bulk persistence (Django bulk operations)
- Progress reporting and monitoring

Main entry point:
    BulkEnhancedPayrollService - High-performance bulk payroll calculator
"""

from .bulk_service import BulkEnhancedPayrollService
from .types import (
    BulkCalculationResult,
    BulkCalculationSummary,
    BulkSaveResult,
    EmployeeData,
    WorkLogData,
)

__all__ = [
    "BulkEnhancedPayrollService",
    "BulkCalculationResult",
    "BulkCalculationSummary",
    "BulkSaveResult",
    "EmployeeData",
    "WorkLogData",
]
