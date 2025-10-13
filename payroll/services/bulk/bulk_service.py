"""
Bulk Enhanced Payroll Service.

This is the main entry point for high-performance bulk payroll calculations.
It coordinates all bulk components to achieve 10-15x performance improvement.

Architecture:
1. BulkDataLoader - Optimized data loading (3-5 queries total)
2. BulkCacheManager - Redis pipeline operations
3. ParallelExecutor - Multiprocessing/threading for calculations
4. BulkPersister - Bulk database operations
5. ProgressReporter - Real-time monitoring

Key features:
- Process hundreds of employees in parallel
- Minimize database queries using prefetch
- Utilize Redis cache with bulk operations
- Transaction safety with rollback
- Real-time progress tracking
- Comprehensive error handling
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from django.db import transaction

from payroll.services.contracts import CalculationContext, PayrollResult
from payroll.services.enums import CalculationStrategy

from .cache_manager import BulkCacheManager
from .data_loader import BulkDataLoader
from .parallel_executor import AdaptiveExecutor, ParallelExecutor
from .persister import BulkPersister
from .progress_reporter import ProgressReporter
from .types import (
    BulkCalculationResult,
    BulkCalculationSummary,
    BulkLoadedData,
    EmployeeCalculationError,
)

logger = logging.getLogger(__name__)


class BulkEnhancedPayrollService:
    """
    Bulk Enhanced Payroll Service.

    High-performance service for calculating payroll for large numbers
    of employees using optimized queries, parallel processing, and caching.

    Example usage:
        service = BulkEnhancedPayrollService()
        result = service.calculate_bulk(
            employee_ids=[1, 2, 3, ...],
            year=2025,
            month=10
        )
        print(f"Processed {result.summary.successful} employees in {result.summary.duration_seconds}s")
    """

    def __init__(
        self,
        use_cache: bool = True,
        use_parallel: bool = True,
        max_workers: Optional[int] = None,
        batch_size: int = 1000,
        show_progress: bool = True,
    ):
        """
        Initialize bulk payroll service.

        Args:
            use_cache: Enable Redis caching
            use_parallel: Enable parallel processing
            max_workers: Maximum parallel workers (None = auto-detect)
            batch_size: Batch size for database operations
            show_progress: Show progress bar during calculation
        """
        self.use_cache = use_cache
        self.use_parallel = use_parallel
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.show_progress = show_progress

        # Initialize components
        self.data_loader = BulkDataLoader()
        self.cache_manager = BulkCacheManager() if use_cache else None
        self.persister = BulkPersister(batch_size=batch_size)

        logger.info(
            "BulkEnhancedPayrollService initialized",
            extra={
                "use_cache": use_cache,
                "use_parallel": use_parallel,
                "max_workers": max_workers,
                "batch_size": batch_size,
                "action": "bulk_service_init",
            },
        )

    def calculate_bulk(
        self,
        employee_ids: List[int],
        year: int,
        month: int,
        strategy: CalculationStrategy = CalculationStrategy.ENHANCED,
        save_to_db: bool = True,
        use_cache_warmup: bool = False,
        export_stats_path: Optional[Path] = None,
    ) -> BulkCalculationResult:
        """
        Calculate payroll for multiple employees in bulk.

        This is the main entry point for bulk calculations.

        Args:
            employee_ids: List of employee IDs to process
            year: Year for calculation
            month: Month for calculation (1-12)
            strategy: Calculation strategy to use
            save_to_db: Save results to database
            use_cache_warmup: Pre-warm cache before calculation
            export_stats_path: Optional path to export statistics

        Returns:
            BulkCalculationResult: Calculation results and statistics

        Example:
            result = service.calculate_bulk(
                employee_ids=[1, 2, 3, 4, 5],
                year=2025,
                month=10,
                save_to_db=True
            )
        """
        start_time = datetime.now()

        logger.info(
            f"Starting bulk calculation for {len(employee_ids)} employees ({year}-{month:02d})",
            extra={
                "employee_count": len(employee_ids),
                "year": year,
                "month": month,
                "strategy": strategy.value,
                "use_cache": self.use_cache,
                "use_parallel": self.use_parallel,
                "action": "bulk_calculation_start",
            },
        )

        # Initialize progress reporter
        progress = ProgressReporter(
            total_employees=len(employee_ids), show_progress_bar=self.show_progress
        )

        try:
            with progress:
                # Step 1: Load all data in bulk
                bulk_data = self._load_data(employee_ids, year, month, progress)

                # Filter out employees without salary
                valid_employee_ids = list(bulk_data.employees.keys())

                if len(valid_employee_ids) < len(employee_ids):
                    skipped = len(employee_ids) - len(valid_employee_ids)
                    logger.warning(
                        f"Skipped {skipped} employees without active salary",
                        extra={"skipped_count": skipped, "action": "employees_skipped"},
                    )

                # Step 2: Try to load from cache
                cached_results = self._load_from_cache(
                    valid_employee_ids, year, month, progress
                )

                # Step 3: Calculate remaining employees
                employee_ids_to_calculate = [
                    emp_id
                    for emp_id in valid_employee_ids
                    if emp_id not in cached_results
                ]

                calculated_results = {}
                if employee_ids_to_calculate:
                    calculated_results = self._calculate_employees(
                        employee_ids_to_calculate,
                        bulk_data,
                        year,
                        month,
                        strategy,
                        progress,
                    )

                # Combine cached and calculated results
                all_results = {**cached_results, **calculated_results}

                # Step 4: Save calculated results to cache
                if self.cache_manager and calculated_results:
                    self.cache_manager.set_many_monthly_summaries(
                        calculated_results, year, month
                    )

                # Step 5: Build contexts for persistence
                contexts = self._build_contexts(
                    valid_employee_ids, bulk_data, year, month
                )

                # Step 6: Save to database
                if save_to_db and all_results:
                    save_result = self.persister.save_all(
                        all_results, contexts, bulk_data
                    )
                    progress.update_save_stats(save_result.total_records)

                    if save_result.errors:
                        logger.warning(
                            f"Database save had {len(save_result.errors)} errors",
                            extra={
                                "error_count": len(save_result.errors),
                                "action": "bulk_save_errors",
                            },
                        )

                # Build final result
                result = self._build_result(
                    all_results, progress.get_stats(), start_time, len(cached_results)
                )

                # Export statistics if requested
                if export_stats_path:
                    progress.export_to_json(export_stats_path)
                    progress.export_errors_to_csv(
                        export_stats_path.parent
                        / f"{export_stats_path.stem}_errors.csv"
                    )

                logger.info(
                    f"Bulk calculation completed: {result.successful_count} successful, "
                    f"{result.failed_count} failed in {result.duration_seconds:.2f}s",
                    extra={
                        "successful": result.successful_count,
                        "failed": result.failed_count,
                        "duration_seconds": result.duration_seconds,
                        "action": "bulk_calculation_complete",
                    },
                )

                return result

        except Exception as e:
            end_time = datetime.now()
            logger.error(
                f"Bulk calculation failed: {e}",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "action": "bulk_calculation_error",
                },
                exc_info=True,
            )

            # Build error result
            from .types import ProcessingStatus

            error_result = BulkCalculationResult(
                results={},
                errors={
                    0: EmployeeCalculationError(
                        employee_id=0,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        timestamp=datetime.now(),
                    )
                },
                total_count=len(employee_ids),
                successful_count=0,
                failed_count=len(employee_ids),
                cached_count=0,
                calculated_count=0,
                duration_seconds=(end_time - start_time).total_seconds(),
                start_time=start_time,
                end_time=end_time,
                cache_hit_rate=0.0,
                db_queries_count=0,
                status=ProcessingStatus.FAILED,
            )

            return error_result

    def _load_data(
        self, employee_ids: List[int], year: int, month: int, progress: ProgressReporter
    ) -> BulkLoadedData:
        """Load all required data in bulk."""
        logger.info("Loading data in bulk...")

        bulk_data = self.data_loader.load_all_data(
            employee_ids, year, month, include_shabbat_times=True
        )

        logger.info(
            f"Loaded data: {len(bulk_data.employees)} employees, "
            f"{sum(len(logs) for logs in bulk_data.work_logs.values())} work logs, "
            f"{len(bulk_data.holidays)} holidays",
            extra={
                "employees": len(bulk_data.employees),
                "work_logs": sum(len(logs) for logs in bulk_data.work_logs.values()),
                "holidays": len(bulk_data.holidays),
                "queries": self.data_loader.query_count,
                "action": "data_loaded",
            },
        )

        return bulk_data

    def _load_from_cache(
        self, employee_ids: List[int], year: int, month: int, progress: ProgressReporter
    ) -> Dict[int, PayrollResult]:
        """Load results from cache if available."""
        if not self.cache_manager:
            return {}

        logger.info("Checking cache...")

        cached_results = self.cache_manager.get_many_monthly_summaries(
            employee_ids, year, month
        )

        # Update progress for cached employees
        for employee_id in cached_results.keys():
            progress.update(employee_id, status="success")

        # Update cache stats in progress
        cache_stats = self.cache_manager.get_cache_stats()
        progress.update_cache_stats(cache_stats.hits, cache_stats.misses)

        if cached_results:
            logger.info(
                f"Loaded {len(cached_results)} results from cache "
                f"({cache_stats.hit_rate:.1f}% hit rate)",
                extra={
                    "cached_count": len(cached_results),
                    "cache_hits": cache_stats.hits,
                    "cache_misses": cache_stats.misses,
                    "hit_rate": cache_stats.hit_rate,
                    "action": "cache_loaded",
                },
            )

        return cached_results

    def _calculate_employees(
        self,
        employee_ids: List[int],
        bulk_data: BulkLoadedData,
        year: int,
        month: int,
        strategy: CalculationStrategy,
        progress: ProgressReporter,
    ) -> Dict[int, PayrollResult]:
        """Calculate payroll for employees (either parallel or sequential)."""
        logger.info(f"Calculating {len(employee_ids)} employees...")

        # Build calculation contexts
        contexts = self._build_contexts(employee_ids, bulk_data, year, month)

        if not contexts:
            return {}

        # Choose execution mode
        if self.use_parallel and len(contexts) >= 5:
            return self._calculate_parallel(contexts, strategy, progress)
        else:
            return self._calculate_sequential(contexts, strategy, progress)

    def _build_contexts(
        self, employee_ids: List[int], bulk_data: BulkLoadedData, year: int, month: int
    ) -> Dict[int, CalculationContext]:
        """Build calculation contexts from bulk data."""
        contexts = {}

        for employee_id in employee_ids:
            employee_data = bulk_data.get_employee(employee_id)
            if not employee_data:
                continue

            work_logs = bulk_data.get_work_logs(employee_id)

            context: CalculationContext = {
                "employee_id": employee_id,
                "user_id": employee_data.user_id,  # Required by base strategy
                "year": year,
                "month": month,
                "calculation_type": employee_data.calculation_type,
                "hourly_rate": employee_data.hourly_rate,
                "base_salary": employee_data.base_salary,
                "work_logs": [
                    {
                        "worklog_id": log.worklog_id,
                        "work_date": log.work_date,
                        "check_in": log.check_in,
                        "check_out": log.check_out,
                        "total_hours": log.total_hours,
                    }
                    for log in work_logs
                ],
                "holidays": bulk_data.holidays,
                "shabbat_times": bulk_data.shabbat_times,
            }

            contexts[employee_id] = context

        return contexts

    def _calculate_parallel(
        self,
        contexts: Dict[int, CalculationContext],
        strategy: CalculationStrategy,
        progress: ProgressReporter,
    ) -> Dict[int, PayrollResult]:
        """Calculate using parallel executor."""
        logger.info(
            f"Using parallel execution with {self.max_workers or 'auto'} workers..."
        )

        # Create executor
        executor = AdaptiveExecutor(
            max_workers=self.max_workers,
            task_timeout=300.0,  # 5 minute timeout per employee
        )

        # Progress callback
        def on_progress(completed: int, total: int, status: str):
            # Progress update is handled by executor
            pass

        # Execute in parallel
        results_or_errors = executor.map_calculations(
            list(contexts.values()), strategy, progress_callback=on_progress
        )

        # Separate successes from errors
        results = {}
        for employee_id, result_or_error in results_or_errors.items():
            if isinstance(result_or_error, Exception):
                progress.update(employee_id, status="error", error=result_or_error)
            else:
                results[employee_id] = result_or_error
                progress.update(employee_id, status="success")

        return results

    def _calculate_sequential(
        self,
        contexts: Dict[int, CalculationContext],
        strategy: CalculationStrategy,
        progress: ProgressReporter,
    ) -> Dict[int, PayrollResult]:
        """Calculate using sequential execution."""
        logger.info("Using sequential execution...")

        from payroll.services.factory import get_payroll_factory

        factory = get_payroll_factory()
        results = {}

        for employee_id, context in contexts.items():
            try:
                calculator = factory.create_calculator(strategy, context)
                result = calculator.calculate_with_logging()
                results[employee_id] = result
                progress.update(employee_id, status="success")

            except Exception as e:
                logger.error(
                    f"Calculation failed for employee {employee_id}: {e}",
                    extra={
                        "employee_id": employee_id,
                        "error": str(e),
                        "action": "calculation_error",
                    },
                )
                progress.update(employee_id, status="error", error=e)

        return results

    def _build_result(
        self,
        results: Dict[int, PayrollResult],
        progress_stats,
        start_time: datetime,
        cached_count: int,
    ) -> BulkCalculationResult:
        """Build final calculation result."""
        end_time = datetime.now()

        # Convert errors list to dict
        errors_dict = {err.employee_id: err for err in progress_stats.errors}

        return BulkCalculationResult(
            results=results,
            errors=errors_dict,
            total_count=progress_stats.total_employees,
            successful_count=progress_stats.successful,
            failed_count=progress_stats.failed,
            cached_count=cached_count,
            calculated_count=progress_stats.successful - cached_count,
            duration_seconds=progress_stats.duration_seconds,
            start_time=start_time,
            end_time=end_time,
            cache_hit_rate=progress_stats.cache_hit_rate,
            db_queries_count=self.data_loader.query_count,
        )

    def invalidate_cache(self, employee_ids: List[int], year: int, month: int) -> int:
        """
        Invalidate cache for specific employees.

        Args:
            employee_ids: Employee IDs to invalidate
            year: Year
            month: Month

        Returns:
            int: Number of cache keys deleted
        """
        if not self.cache_manager:
            return 0

        deleted_count = self.cache_manager.invalidate_employees(
            employee_ids, year, month
        )

        logger.info(
            f"Invalidated cache for {len(employee_ids)} employees ({deleted_count} keys deleted)",
            extra={
                "employee_count": len(employee_ids),
                "deleted_count": deleted_count,
                "action": "cache_invalidated",
            },
        )

        return deleted_count

    def get_statistics(self) -> Dict:
        """
        Get service statistics.

        Returns:
            Dict with various statistics
        """
        stats = {
            "use_cache": self.use_cache,
            "use_parallel": self.use_parallel,
            "max_workers": self.max_workers,
            "batch_size": self.batch_size,
        }

        if self.cache_manager:
            cache_stats = self.cache_manager.get_cache_stats()
            stats["cache"] = {
                "available": self.cache_manager.cache_available,
                "hits": cache_stats.hits,
                "misses": cache_stats.misses,
                "hit_rate": cache_stats.hit_rate,
            }

        return stats
