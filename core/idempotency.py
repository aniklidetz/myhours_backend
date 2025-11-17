"""
Celery task idempotency utilities

Provides Redis-based idempotency protection for Celery tasks to prevent
duplicate execution on retries or network failures.
"""

import hashlib
import json
import logging
from datetime import timedelta
from functools import wraps

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


def make_idempotency_key(task_name, args=None, kwargs=None, date_based=True):
    """
    Generate unique idempotency key for a task execution.

    Args:
        task_name: Name of the Celery task
        args: Positional arguments tuple
        kwargs: Keyword arguments dict
        date_based: Include current date in key (for daily tasks)

    Returns:
        String key for Redis storage
    """
    # Create deterministic hash from arguments
    args_str = json.dumps(args or [], sort_keys=True, default=str)
    kwargs_str = json.dumps(kwargs or {}, sort_keys=True, default=str)
    combined = f"{args_str}:{kwargs_str}"

    arg_hash = hashlib.sha256(combined.encode()).hexdigest()[:16]

    # Build key
    key_parts = ["idempotent", task_name, arg_hash]

    if date_based:
        # Include date for daily tasks (separate execution each day)
        today = timezone.now().date().isoformat()
        key_parts.append(today)

    return ":".join(key_parts)


def idempotent_task(ttl_hours=24, date_based=True, skip_on_duplicate=True):
    """
    Decorator to make Celery tasks idempotent using Redis keys.

    Prevents duplicate execution when:
    - Task retries after partial completion
    - Celery crashes before ACK
    - Network issues cause duplicate delivery

    Usage:
        @shared_task(bind=True, max_retries=3)
        @idempotent_task(ttl_hours=24, date_based=True)
        def my_task(self, arg1, arg2):
            # Task logic here
            return result

    Args:
        ttl_hours: How long to remember task completion (hours)
        date_based: Include date in key (True for daily tasks)
        skip_on_duplicate: Skip execution if already completed (vs raise error)

    Returns:
        Decorated function with idempotency protection
    """

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Generate idempotency key
            task_name = self.name if hasattr(self, "name") else func.__name__
            idempotency_key = make_idempotency_key(
                task_name=task_name, args=args, kwargs=kwargs, date_based=date_based
            )

            # Check if task already completed
            cached_result = cache.get(idempotency_key)

            if cached_result is not None:
                logger.info(
                    f"Task {task_name} already completed (idempotency key: {idempotency_key}). "
                    f"Skipping execution."
                )

                if skip_on_duplicate:
                    # Return cached result
                    return cached_result.get("result")
                else:
                    # Raise error to alert about duplicate
                    raise RuntimeError(
                        f"Task {task_name} already executed. "
                        f"Idempotency violation detected."
                    )

            # Execute task
            logger.debug(
                f"Executing task {task_name} with idempotency key: {idempotency_key}"
            )

            try:
                result = func(self, *args, **kwargs)

                # Store completion in cache
                completion_data = {
                    "result": result,
                    "completed_at": timezone.now().isoformat(),
                    "task_name": task_name,
                    "args": args,
                    "kwargs": kwargs,
                }

                ttl_seconds = ttl_hours * 3600
                cache.set(idempotency_key, completion_data, timeout=ttl_seconds)

                logger.info(
                    f"Task {task_name} completed successfully. "
                    f"Idempotency key cached for {ttl_hours}h."
                )

                return result

            except Exception as exc:
                # On failure, don't cache (allow retry)
                logger.warning(
                    f"Task {task_name} failed. Not caching result to allow retry.",
                    exc_info=True,
                )
                raise

        return wrapper

    return decorator


def clear_idempotency_key(task_name, args=None, kwargs=None, date_based=True):
    """
    Manually clear idempotency key (for testing or manual retry).

    Args:
        task_name: Name of the Celery task
        args: Positional arguments tuple
        kwargs: Keyword arguments dict
        date_based: Include current date in key

    Returns:
        True if key was cleared, False if not found
    """
    idempotency_key = make_idempotency_key(
        task_name=task_name, args=args, kwargs=kwargs, date_based=date_based
    )

    result = cache.delete(idempotency_key)
    if result:
        logger.info(f"Cleared idempotency key: {idempotency_key}")
    else:
        logger.warning(f"Idempotency key not found: {idempotency_key}")

    return bool(result)


def check_idempotency_status(task_name, args=None, kwargs=None, date_based=True):
    """
    Check if task has already been executed.

    Args:
        task_name: Name of the Celery task
        args: Positional arguments tuple
        kwargs: Keyword arguments dict
        date_based: Include current date in key

    Returns:
        Dict with status or None if not executed
    """
    idempotency_key = make_idempotency_key(
        task_name=task_name, args=args, kwargs=kwargs, date_based=date_based
    )

    cached_result = cache.get(idempotency_key)

    if cached_result:
        return {
            "executed": True,
            "completed_at": cached_result.get("completed_at"),
            "result": cached_result.get("result"),
        }
    else:
        return {"executed": False}


# Convenience decorator for daily tasks
def idempotent_daily_task(ttl_hours=48):
    """
    Decorator for daily tasks (date-based idempotency).

    Tasks can execute once per day. Idempotency key expires after 48h.
    """
    return idempotent_task(ttl_hours=ttl_hours, date_based=True)


# Convenience decorator for non-daily tasks
def idempotent_once(ttl_hours=24):
    """
    Decorator for tasks that should run once with given arguments.

    Not date-based - task with same arguments can only run once until TTL expires.
    """
    return idempotent_task(ttl_hours=ttl_hours, date_based=False)
