"""
Tests for Celery task idempotency utilities
"""

import time
from datetime import timedelta
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from core.idempotency import (
    check_idempotency_status,
    clear_idempotency_key,
    idempotent_daily_task,
    idempotent_once,
    idempotent_task,
    make_idempotency_key,
)


class IdempotencyKeyTest(TestCase):
    """Test idempotency key generation"""

    def test_basic_key_generation(self):
        """Test basic key generation without date"""
        key = make_idempotency_key(
            task_name="test.task", args=(1, 2), kwargs={"foo": "bar"}, date_based=False
        )

        self.assertIsInstance(key, str)
        self.assertIn("idempotent", key)
        self.assertIn("test.task", key)

    def test_date_based_key(self):
        """Test date-based key includes current date"""
        key = make_idempotency_key(
            task_name="test.task", args=(1,), kwargs={}, date_based=True
        )

        today = timezone.now().date().isoformat()
        self.assertIn(today, key)

    def test_same_args_same_key(self):
        """Test same arguments produce same key"""
        key1 = make_idempotency_key(
            task_name="test.task", args=(1, 2), kwargs={"foo": "bar"}, date_based=False
        )
        key2 = make_idempotency_key(
            task_name="test.task", args=(1, 2), kwargs={"foo": "bar"}, date_based=False
        )

        self.assertEqual(key1, key2)

    def test_different_args_different_key(self):
        """Test different arguments produce different keys"""
        key1 = make_idempotency_key(
            task_name="test.task", args=(1,), kwargs={}, date_based=False
        )
        key2 = make_idempotency_key(
            task_name="test.task", args=(2,), kwargs={}, date_based=False
        )

        self.assertNotEqual(key1, key2)

    def test_kwargs_order_independent(self):
        """Test kwargs order doesn't affect key"""
        key1 = make_idempotency_key(
            task_name="test.task",
            args=(),
            kwargs={"a": 1, "b": 2},
            date_based=False,
        )
        key2 = make_idempotency_key(
            task_name="test.task",
            args=(),
            kwargs={"b": 2, "a": 1},
            date_based=False,
        )

        self.assertEqual(key1, key2)


class IdempotentTaskDecoratorTest(TestCase):
    """Test idempotent_task decorator"""

    def setUp(self):
        """Clear cache before each test"""
        cache.clear()

    def tearDown(self):
        """Clear cache after each test"""
        cache.clear()

    def test_first_execution_runs(self):
        """Test task executes on first call"""
        execution_count = {"count": 0}

        @idempotent_task(ttl_hours=1, date_based=False)
        def test_task(self):
            execution_count["count"] += 1
            return {"result": "success"}

        # Mock self with name
        mock_self = Mock()
        mock_self.name = "test.task"

        result = test_task(mock_self)

        self.assertEqual(execution_count["count"], 1)
        self.assertEqual(result["result"], "success")

    def test_duplicate_execution_skipped(self):
        """Test duplicate execution is skipped"""
        execution_count = {"count": 0}

        @idempotent_task(ttl_hours=1, date_based=False)
        def test_task(self):
            execution_count["count"] += 1
            return {"result": "success", "count": execution_count["count"]}

        mock_self = Mock()
        mock_self.name = "test.task.duplicate"

        # First execution
        result1 = test_task(mock_self)
        self.assertEqual(execution_count["count"], 1)
        self.assertEqual(result1["count"], 1)

        # Second execution (should be skipped)
        result2 = test_task(mock_self)
        self.assertEqual(execution_count["count"], 1)  # Still 1
        self.assertEqual(result2["count"], 1)  # Cached result

    def test_different_args_both_execute(self):
        """Test tasks with different args both execute"""
        execution_count = {"count": 0}

        @idempotent_task(ttl_hours=1, date_based=False)
        def test_task(self, arg1):
            execution_count["count"] += 1
            return {"result": arg1}

        mock_self = Mock()
        mock_self.name = "test.task.args"

        # Execute with arg=1
        result1 = test_task(mock_self, 1)
        self.assertEqual(execution_count["count"], 1)

        # Execute with arg=2 (different args, should execute)
        result2 = test_task(mock_self, 2)
        self.assertEqual(execution_count["count"], 2)

    def test_exception_not_cached(self):
        """Test failed execution doesn't cache result"""
        execution_count = {"count": 0}

        @idempotent_task(ttl_hours=1, date_based=False)
        def failing_task(self):
            execution_count["count"] += 1
            if execution_count["count"] == 1:
                raise ValueError("First execution fails")
            return {"result": "success"}

        mock_self = Mock()
        mock_self.name = "test.failing.task"

        # First execution fails
        with self.assertRaises(ValueError):
            failing_task(mock_self)

        self.assertEqual(execution_count["count"], 1)

        # Second execution succeeds (failure wasn't cached)
        result = failing_task(mock_self)
        self.assertEqual(execution_count["count"], 2)
        self.assertEqual(result["result"], "success")

    def test_skip_on_duplicate_false_raises_error(self):
        """Test skip_on_duplicate=False raises error on duplicate"""

        @idempotent_task(ttl_hours=1, date_based=False, skip_on_duplicate=False)
        def strict_task(self):
            return {"result": "success"}

        mock_self = Mock()
        mock_self.name = "test.strict.task"

        # First execution succeeds
        result1 = strict_task(mock_self)
        self.assertEqual(result1["result"], "success")

        # Second execution raises error
        with self.assertRaises(RuntimeError) as cm:
            strict_task(mock_self)

        self.assertIn("already executed", str(cm.exception))

    def test_date_based_idempotency(self):
        """Test date-based idempotency allows execution on different days"""
        execution_count = {"count": 0}

        @idempotent_task(ttl_hours=1, date_based=True)
        def daily_task(self):
            execution_count["count"] += 1
            return {"result": execution_count["count"]}

        mock_self = Mock()
        mock_self.name = "test.daily.task"

        # First execution
        result1 = daily_task(mock_self)
        self.assertEqual(result1["result"], 1)

        # Second execution same day (skipped)
        result2 = daily_task(mock_self)
        self.assertEqual(result2["result"], 1)

        # Would execute on different day (simulated by clearing cache)
        cache.clear()
        result3 = daily_task(mock_self)
        self.assertEqual(result3["result"], 2)


class ConvenienceDecoratorsTest(TestCase):
    """Test convenience decorators"""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_idempotent_daily_task(self):
        """Test idempotent_daily_task decorator"""
        execution_count = {"count": 0}

        @idempotent_daily_task(ttl_hours=48)
        def daily_task(self):
            execution_count["count"] += 1
            return {"result": "daily"}

        mock_self = Mock()
        mock_self.name = "daily.task"

        # First execution
        result1 = daily_task(mock_self)
        self.assertEqual(execution_count["count"], 1)

        # Duplicate skipped
        result2 = daily_task(mock_self)
        self.assertEqual(execution_count["count"], 1)

    def test_idempotent_once(self):
        """Test idempotent_once decorator"""
        execution_count = {"count": 0}

        @idempotent_once(ttl_hours=24)
        def once_task(self, data):
            execution_count["count"] += 1
            return {"result": data}

        mock_self = Mock()
        mock_self.name = "once.task"

        # First execution with data=1
        result1 = once_task(mock_self, 1)
        self.assertEqual(execution_count["count"], 1)

        # Duplicate with data=1 (skipped)
        result2 = once_task(mock_self, 1)
        self.assertEqual(execution_count["count"], 1)

        # Different data executes
        result3 = once_task(mock_self, 2)
        self.assertEqual(execution_count["count"], 2)


class IdempotencyUtilsTest(TestCase):
    """Test utility functions"""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_clear_idempotency_key(self):
        """Test manual key clearing"""

        @idempotent_once(ttl_hours=1)
        def test_task(self, arg):
            return {"result": arg}

        mock_self = Mock()
        mock_self.name = "clearable.task"

        # Execute task
        test_task(mock_self, 1)

        # Verify it won't execute again
        status = check_idempotency_status(
            task_name="clearable.task", args=(1,), kwargs={}, date_based=False
        )
        self.assertTrue(status["executed"])

        # Clear the key
        cleared = clear_idempotency_key(
            task_name="clearable.task", args=(1,), kwargs={}, date_based=False
        )
        self.assertTrue(cleared)

        # Verify it's cleared
        status = check_idempotency_status(
            task_name="clearable.task", args=(1,), kwargs={}, date_based=False
        )
        self.assertFalse(status["executed"])

    def test_check_idempotency_status(self):
        """Test checking execution status"""

        @idempotent_once(ttl_hours=1)
        def test_task(self):
            return {"result": "done"}

        mock_self = Mock()
        mock_self.name = "status.task"

        # Before execution
        status = check_idempotency_status(
            task_name="status.task", args=(), kwargs={}, date_based=False
        )
        self.assertFalse(status["executed"])

        # Execute task
        result = test_task(mock_self)

        # After execution
        status = check_idempotency_status(
            task_name="status.task", args=(), kwargs={}, date_based=False
        )
        self.assertTrue(status["executed"])
        self.assertIsNotNone(status["completed_at"])
        self.assertEqual(status["result"]["result"], "done")


class RetryScenarioTest(TestCase):
    """Test real-world retry scenarios"""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_retry_after_failure_executes(self):
        """Test task retries after failure (not cached)"""
        attempts = {"count": 0}

        @idempotent_once(ttl_hours=1)
        def retry_task(self):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise ConnectionError("Network error")
            return {"result": "success", "attempts": attempts["count"]}

        mock_self = Mock()
        mock_self.name = "retry.task"

        # First two attempts fail
        with self.assertRaises(ConnectionError):
            retry_task(mock_self)
        with self.assertRaises(ConnectionError):
            retry_task(mock_self)

        # Third attempt succeeds
        result = retry_task(mock_self)
        self.assertEqual(result["attempts"], 3)

        # Fourth attempt skipped (success was cached)
        result2 = retry_task(mock_self)
        self.assertEqual(result2["attempts"], 3)

    def test_partial_completion_prevents_rerun(self):
        """Test task that completes but Celery fails to ACK"""
        side_effects = {"database_writes": 0, "emails_sent": 0}

        @idempotent_once(ttl_hours=1)
        def critical_task(self):
            # Simulate writing to database
            side_effects["database_writes"] += 1

            # Simulate sending email
            side_effects["emails_sent"] += 1

            return {"status": "completed"}

        mock_self = Mock()
        mock_self.name = "critical.task"

        # First execution completes
        result1 = critical_task(mock_self)
        self.assertEqual(side_effects["database_writes"], 1)
        self.assertEqual(side_effects["emails_sent"], 1)

        # Simulated retry (Celery didn't ACK) - should be skipped
        result2 = critical_task(mock_self)
        # Side effects didn't happen again
        self.assertEqual(side_effects["database_writes"], 1)
        self.assertEqual(side_effects["emails_sent"], 1)


class PerformanceTest(TestCase):
    """Test performance characteristics"""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_cache_hit_is_fast(self):
        """Test cached result retrieval is fast"""

        @idempotent_once(ttl_hours=1)
        def slow_task(self):
            time.sleep(0.1)  # Simulate slow operation
            return {"result": "done"}

        mock_self = Mock()
        mock_self.name = "slow.task"

        # First execution (slow)
        start = time.time()
        slow_task(mock_self)
        first_duration = time.time() - start
        self.assertGreater(first_duration, 0.1)

        # Second execution (fast cache hit)
        start = time.time()
        slow_task(mock_self)
        second_duration = time.time() - start
        self.assertLess(second_duration, 0.05)  # Much faster
