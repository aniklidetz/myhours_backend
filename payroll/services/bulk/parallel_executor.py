"""
Parallel executor for high-performance bulk calculations.

This module provides parallel processing capabilities using multiprocessing
or threading, with automatic worker management and error handling.

Key features:
- Automatic worker count based on CPU cores
- Support for both multiprocessing and threading
- Graceful error handling with continuation
- Timeout support for individual tasks
- Clean shutdown handling
"""

import logging
import multiprocessing
import os
from concurrent.futures import (
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    TimeoutError,
    as_completed,
)
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union

from payroll.services.contracts import CalculationContext, PayrollResult
from payroll.services.enums import CalculationStrategy
from payroll.services.factory import get_payroll_factory

from .types import EmployeeCalculationError

logger = logging.getLogger(__name__)


def _calculate_payroll_worker(
    context: CalculationContext, strategy: CalculationStrategy
) -> PayrollResult:
    """
    Worker function for parallel payroll calculation.

    This function is designed to be serializable for multiprocessing.
    It creates its own factory and calculator instances to avoid
    sharing state between processes.

    Args:
        context: Calculation context for single employee
        strategy: Strategy to use for calculation

    Returns:
        PayrollResult: Calculation result

    Raises:
        Exception: Any error during calculation
    """
    try:
        # Create fresh factory instance for this worker
        factory = get_payroll_factory()

        # Create calculator and perform calculation
        calculator = factory.create_calculator(strategy, context)
        result = calculator.calculate_with_logging()

        return result

    except Exception as e:
        # Re-raise with context for better error tracking
        logger.error(
            f"Worker calculation failed for employee {context.get('employee_id', 'unknown')}",
            extra={
                "employee_id": context.get("employee_id"),
                "error": str(e),
                "error_type": type(e).__name__,
                "action": "worker_calculation_error",
            },
            exc_info=True,
        )
        raise


class ParallelExecutor:
    """
    Parallel executor for bulk payroll calculations.

    This class manages parallel processing of payroll calculations using
    either multiprocessing (CPU-bound) or threading (I/O-bound).

    Features:
    - Automatic worker count determination
    - Graceful error handling
    - Task timeout support
    - Progress tracking
    - Clean shutdown
    """

    def __init__(
        self,
        max_workers: Optional[int] = None,
        use_processes: bool = True,
        task_timeout: Optional[float] = None,
    ):
        """
        Initialize parallel executor.

        Args:
            max_workers: Maximum number of workers (None = auto-detect)
            use_processes: Use processes (True) or threads (False)
            task_timeout: Timeout per task in seconds (None = no timeout)
        """
        self.max_workers = max_workers or self._get_optimal_worker_count()
        self.use_processes = use_processes
        self.task_timeout = task_timeout
        self._executor = None

        logger.info(
            f"ParallelExecutor initialized with {self.max_workers} workers "
            f"({'processes' if use_processes else 'threads'})",
            extra={
                "max_workers": self.max_workers,
                "use_processes": use_processes,
                "task_timeout": task_timeout,
                "action": "parallel_executor_init",
            },
        )

    def _get_optimal_worker_count(self) -> int:
        """
        Determine optimal number of workers based on CPU cores.

        Returns:
            int: Optimal worker count
        """
        try:
            cpu_count = os.cpu_count() or 4

            # For CPU-bound tasks (processes), use all cores
            # For I/O-bound tasks (threads), use 2x cores
            if self.use_processes:
                optimal = max(1, cpu_count - 1)  # Leave one core for system
            else:
                optimal = cpu_count * 2  # Threads can handle more I/O

            return optimal

        except Exception:
            return 4  # Safe default

    def map_calculations(
        self,
        contexts: List[CalculationContext],
        strategy: CalculationStrategy,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[int, Union[PayrollResult, Exception]]:
        """
        Execute calculations in parallel for multiple employees.

        Args:
            contexts: List of calculation contexts
            strategy: Strategy to use for all calculations
            progress_callback: Optional callback(completed, total, status)

        Returns:
            Dict mapping employee_id to result or error
        """
        if not contexts:
            return {}

        start_time = datetime.now()
        results: Dict[int, Union[PayrollResult, Exception]] = {}

        logger.info(
            f"Starting parallel calculation for {len(contexts)} employees",
            extra={
                "total_contexts": len(contexts),
                "strategy": strategy.value,
                "max_workers": self.max_workers,
                "action": "parallel_calculation_start",
            },
        )

        # Choose executor type
        executor_class = (
            ProcessPoolExecutor if self.use_processes else ThreadPoolExecutor
        )

        try:
            with executor_class(max_workers=self.max_workers) as executor:
                # Submit all tasks
                future_to_context = {
                    executor.submit(
                        _calculate_payroll_worker, context, strategy
                    ): context
                    for context in contexts
                }

                total_tasks = len(future_to_context)
                completed_tasks = 0

                # Process completed tasks
                for future in as_completed(future_to_context):
                    context = future_to_context[future]
                    employee_id = context["employee_id"]

                    try:
                        # Get result with optional timeout
                        result = future.result(timeout=self.task_timeout)
                        results[employee_id] = result

                        completed_tasks += 1

                        # Call progress callback if provided
                        if progress_callback:
                            progress_callback(completed_tasks, total_tasks, "success")

                        logger.debug(
                            f"Calculation completed for employee {employee_id}",
                            extra={
                                "employee_id": employee_id,
                                "completed": completed_tasks,
                                "total": total_tasks,
                                "action": "calculation_completed",
                            },
                        )

                    except TimeoutError:
                        error = TimeoutError(
                            f"Calculation timed out after {self.task_timeout}s"
                        )
                        results[employee_id] = error
                        completed_tasks += 1

                        if progress_callback:
                            progress_callback(completed_tasks, total_tasks, "timeout")

                        logger.error(
                            f"Calculation timeout for employee {employee_id}",
                            extra={
                                "employee_id": employee_id,
                                "timeout": self.task_timeout,
                                "action": "calculation_timeout",
                            },
                        )

                    except Exception as e:
                        results[employee_id] = e
                        completed_tasks += 1

                        if progress_callback:
                            progress_callback(completed_tasks, total_tasks, "error")

                        logger.error(
                            f"Calculation error for employee {employee_id}: {e}",
                            extra={
                                "employee_id": employee_id,
                                "error": str(e),
                                "error_type": type(e).__name__,
                                "action": "calculation_error",
                            },
                        )

        except Exception as e:
            logger.error(
                f"Parallel executor failed: {e}",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "action": "parallel_executor_error",
                },
                exc_info=True,
            )

            # Return errors for all remaining contexts
            for context in contexts:
                employee_id = context["employee_id"]
                if employee_id not in results:
                    results[employee_id] = e

        duration = (datetime.now() - start_time).total_seconds()

        # Count successes and failures
        success_count = sum(1 for r in results.values() if not isinstance(r, Exception))
        error_count = len(results) - success_count

        logger.info(
            f"Parallel calculation completed: {success_count} success, {error_count} errors in {duration:.2f}s",
            extra={
                "total_contexts": len(contexts),
                "success_count": success_count,
                "error_count": error_count,
                "duration_seconds": duration,
                "avg_time_per_employee": duration / len(contexts) if contexts else 0,
                "action": "parallel_calculation_complete",
            },
        )

        return results

    def shutdown(self, wait: bool = True):
        """
        Shutdown the executor gracefully.

        Args:
            wait: Wait for pending tasks to complete
        """
        if self._executor:
            logger.info(
                "Shutting down parallel executor",
                extra={"wait": wait, "action": "parallel_executor_shutdown"},
            )
            self._executor.shutdown(wait=wait)
            self._executor = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.shutdown(wait=True)
        return False


class AdaptiveExecutor(ParallelExecutor):
    """
    Adaptive parallel executor that automatically chooses between
    processes and threads based on batch size and task characteristics.
    """

    # Thresholds for adaptive selection
    PROCESS_THRESHOLD = 10  # Use processes for 10+ employees
    THREAD_THRESHOLD = 50  # Switch to threads for 50+ (if I/O heavy)

    def __init__(
        self,
        max_workers: Optional[int] = None,
        task_timeout: Optional[float] = None,
        prefer_processes: bool = True,
    ):
        """
        Initialize adaptive executor.

        Args:
            max_workers: Maximum number of workers (None = auto)
            task_timeout: Timeout per task in seconds
            prefer_processes: Prefer processes over threads when uncertain
        """
        # Start with preferred mode
        super().__init__(
            max_workers=max_workers,
            use_processes=prefer_processes,
            task_timeout=task_timeout,
        )
        self.prefer_processes = prefer_processes

    def map_calculations(
        self,
        contexts: List[CalculationContext],
        strategy: CalculationStrategy,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict[int, Union[PayrollResult, Exception]]:
        """
        Execute calculations with adaptive worker selection.

        Automatically chooses between processes and threads based on
        batch size and task characteristics.
        """
        batch_size = len(contexts)

        # Adaptive selection logic
        if batch_size < self.PROCESS_THRESHOLD:
            # Small batch: use threads (lower overhead)
            self.use_processes = False
            logger.info(
                f"Using threads for small batch ({batch_size} employees)",
                extra={"batch_size": batch_size, "action": "adaptive_select_threads"},
            )
        elif batch_size >= self.THREAD_THRESHOLD:
            # Large batch: use processes if preferred (better CPU utilization)
            self.use_processes = self.prefer_processes
            logger.info(
                f"Using {'processes' if self.use_processes else 'threads'} for large batch ({batch_size} employees)",
                extra={"batch_size": batch_size, "action": "adaptive_select"},
            )
        else:
            # Medium batch: use preference
            self.use_processes = self.prefer_processes

        # Recalculate optimal workers for chosen mode
        self.max_workers = self._get_optimal_worker_count()

        # Execute with selected mode
        return super().map_calculations(contexts, strategy, progress_callback)
