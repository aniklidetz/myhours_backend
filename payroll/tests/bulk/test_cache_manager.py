"""
Tests for BulkCacheManager.
"""

import json
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

from django.test import TestCase

from payroll.services.bulk.cache_manager import BulkCacheManager
from payroll.services.bulk.types import CacheStats


class BulkCacheManagerTestCase(TestCase):
    """Tests for BulkCacheManager class."""

    def setUp(self):
        """Set up test fixtures."""
        self.cache_manager = BulkCacheManager()

    def test_make_key(self):
        """Test cache key generation."""
        key = self.cache_manager._make_key("monthly_summary", 1, 2025, 10)
        self.assertEqual(key, "monthly_summary:1:2025:10")

        key2 = self.cache_manager._make_key("daily_calc", 5, "2025-10-09")
        self.assertEqual(key2, "daily_calc:5:2025-10-09")

    def test_serialize_decimal(self):
        """Test Decimal serialization."""
        result = self.cache_manager._serialize_decimal(Decimal("123.45"))
        self.assertEqual(result, 123.45)
        self.assertIsInstance(result, float)

    def test_serialize_decimal_raises_for_non_decimal(self):
        """Test that non-Decimal objects raise TypeError."""
        with self.assertRaises(TypeError):
            self.cache_manager._serialize_decimal(object())

    @patch("payroll.services.bulk.cache_manager.redis.Redis")
    def test_get_many_monthly_summaries_cache_available(self, mock_redis_class):
        """Test bulk get with cache available."""
        # Mock Redis client
        mock_redis = MagicMock()
        mock_redis.mget.return_value = [
            json.dumps({"total_salary": 5000}),
            json.dumps({"total_salary": 6000}),
            None,  # Cache miss for employee 3
        ]
        mock_redis.ping.return_value = True

        # Inject mock
        cache_manager = BulkCacheManager()
        cache_manager.redis_client = mock_redis
        cache_manager.cache_available = True

        # Test bulk get
        employee_ids = [1, 2, 3]
        results = cache_manager.get_many_monthly_summaries(employee_ids, 2025, 10)

        # Verify Redis MGET was called
        mock_redis.mget.assert_called_once()
        call_args = mock_redis.mget.call_args[0][0]
        self.assertEqual(len(call_args), 3)

        # Verify results
        self.assertEqual(len(results), 2)  # Only 2 hits
        self.assertIn(1, results)
        self.assertIn(2, results)
        self.assertNotIn(3, results)  # Cache miss

        # Verify stats
        stats = cache_manager.get_cache_stats()
        self.assertEqual(stats.hits, 2)
        self.assertEqual(stats.misses, 1)
        self.assertEqual(stats.total_keys, 3)

    @patch("payroll.services.bulk.cache_manager.redis.Redis")
    def test_set_many_monthly_summaries_cache_available(self, mock_redis_class):
        """Test bulk set with cache available."""
        # Mock Redis client and pipeline
        mock_pipeline = MagicMock()
        mock_redis = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_redis.ping.return_value = True

        # Inject mock
        cache_manager = BulkCacheManager()
        cache_manager.redis_client = mock_redis
        cache_manager.cache_available = True

        # Test bulk set
        results = {
            1: {"total_salary": Decimal("5000.00")},
            2: {"total_salary": Decimal("6000.00")},
        }

        success = cache_manager.set_many_monthly_summaries(results, 2025, 10, ttl=3600)

        # Verify pipeline was used
        mock_redis.pipeline.assert_called_once()
        self.assertTrue(success)

        # Verify setex was called for each result
        self.assertEqual(mock_pipeline.setex.call_count, 2)

        # Verify pipeline execute was called
        mock_pipeline.execute.assert_called_once()

        # Verify stats
        stats = cache_manager.get_cache_stats()
        self.assertEqual(stats.sets, 2)

    def test_get_many_cache_unavailable(self):
        """Test bulk get when cache is unavailable."""
        cache_manager = BulkCacheManager()
        cache_manager.cache_available = False

        results = cache_manager.get_many_monthly_summaries([1, 2, 3], 2025, 10)

        # Should return empty dict when cache unavailable
        self.assertEqual(results, {})

    def test_set_many_cache_unavailable(self):
        """Test bulk set when cache is unavailable."""
        cache_manager = BulkCacheManager()
        cache_manager.cache_available = False

        results = {1: {"total_salary": 5000}}
        success = cache_manager.set_many_monthly_summaries(results, 2025, 10)

        # Should return False when cache unavailable
        self.assertFalse(success)

    @patch("payroll.services.bulk.cache_manager.redis.Redis")
    def test_invalidate_employees(self, mock_redis_class):
        """Test bulk invalidation."""
        # Mock Redis client
        mock_redis = MagicMock()
        mock_redis.keys.return_value = [
            "daily_calc:1:2025-10-09",
            "daily_calc:1:2025-10-10",
        ]
        mock_redis.delete.return_value = 4  # 2 monthly + 2 daily
        mock_redis.ping.return_value = True

        # Inject mock
        cache_manager = BulkCacheManager()
        cache_manager.redis_client = mock_redis
        cache_manager.cache_available = True

        # Test invalidation
        deleted_count = cache_manager.invalidate_employees([1, 2], 2025, 10)

        # Verify keys were deleted
        self.assertGreater(deleted_count, 0)
        mock_redis.delete.assert_called()

    @patch("payroll.services.bulk.cache_manager.redis.Redis")
    def test_warm_up_cache(self, mock_redis_class):
        """Test cache warming (alias for set_many)."""
        # Mock Redis
        mock_pipeline = MagicMock()
        mock_redis = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_redis.ping.return_value = True

        cache_manager = BulkCacheManager()
        cache_manager.redis_client = mock_redis
        cache_manager.cache_available = True

        # Test cache warming
        results = {1: {"total_salary": 5000}}
        success = cache_manager.warm_up_cache(results, 2025, 10)

        self.assertTrue(success)
        mock_pipeline.execute.assert_called_once()

    def test_reset_stats(self):
        """Test resetting cache statistics."""
        cache_manager = BulkCacheManager()

        # Manually set some stats
        cache_manager._stats.hits = 10
        cache_manager._stats.misses = 5
        cache_manager._stats.sets = 3

        # Reset
        cache_manager.reset_stats()

        # Verify stats are reset
        stats = cache_manager.get_cache_stats()
        self.assertEqual(stats.hits, 0)
        self.assertEqual(stats.misses, 0)
        self.assertEqual(stats.sets, 0)

    @patch("payroll.services.bulk.cache_manager.redis.Redis")
    def test_check_availability(self, mock_redis_class):
        """Test checking cache availability."""
        # Test when available
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True

        cache_manager = BulkCacheManager()
        cache_manager.redis_client = mock_redis
        cache_manager.cache_available = True

        self.assertTrue(cache_manager.check_availability())

        # Test when unavailable
        cache_manager.cache_available = False
        self.assertFalse(cache_manager.check_availability())

    @patch("payroll.services.bulk.cache_manager.redis.Redis")
    def test_flush_pattern(self, mock_redis_class):
        """Test flushing keys by pattern."""
        # Mock Redis
        mock_redis = MagicMock()
        mock_redis.keys.return_value = [
            "monthly_summary:1:2025:10",
            "monthly_summary:2:2025:10",
            "monthly_summary:3:2025:10",
        ]
        mock_redis.delete.return_value = 3
        mock_redis.ping.return_value = True

        cache_manager = BulkCacheManager()
        cache_manager.redis_client = mock_redis
        cache_manager.cache_available = True

        # Test pattern flush
        deleted_count = cache_manager.flush_pattern("monthly_summary:*")

        self.assertEqual(deleted_count, 3)
        mock_redis.keys.assert_called_with("monthly_summary:*")
        mock_redis.delete.assert_called_once()

    @patch("payroll.services.bulk.cache_manager.redis.Redis")
    def test_get_many_handles_json_decode_error(self, mock_redis_class):
        """Test that JSON decode errors are handled gracefully."""
        # Mock Redis with invalid JSON
        mock_redis = MagicMock()
        mock_redis.mget.return_value = [
            "invalid json{",  # This will cause JSONDecodeError
            json.dumps({"total_salary": 6000}),
        ]
        mock_redis.ping.return_value = True

        cache_manager = BulkCacheManager()
        cache_manager.redis_client = mock_redis
        cache_manager.cache_available = True

        employee_ids = [1, 2]
        results = cache_manager.get_many_monthly_summaries(employee_ids, 2025, 10)

        # Should only return the valid result
        self.assertEqual(len(results), 1)
        self.assertIn(2, results)
        self.assertNotIn(1, results)

        # Both should count as misses (1 decode error + 1 valid = 1 hit + 1 miss)
        stats = cache_manager.get_cache_stats()
        self.assertEqual(stats.hits, 1)
        self.assertEqual(stats.misses, 1)

    @patch("payroll.services.bulk.cache_manager.redis.Redis")
    def test_get_many_handles_redis_error(self, mock_redis_class):
        """Test that Redis errors are handled gracefully."""
        # Mock Redis to raise exception
        mock_redis = MagicMock()
        mock_redis.mget.side_effect = Exception("Redis connection error")
        mock_redis.ping.return_value = True

        cache_manager = BulkCacheManager()
        cache_manager.redis_client = mock_redis
        cache_manager.cache_available = True

        employee_ids = [1, 2, 3]
        results = cache_manager.get_many_monthly_summaries(employee_ids, 2025, 10)

        # Should return empty dict on error
        self.assertEqual(results, {})

    @patch("payroll.services.bulk.cache_manager.redis.Redis")
    def test_set_many_handles_redis_error(self, mock_redis_class):
        """Test that Redis errors during set are handled gracefully."""
        # Mock Redis to raise exception
        mock_pipeline = MagicMock()
        mock_pipeline.execute.side_effect = Exception("Redis write error")

        mock_redis = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline
        mock_redis.ping.return_value = True

        cache_manager = BulkCacheManager()
        cache_manager.redis_client = mock_redis
        cache_manager.cache_available = True

        results = {1: {"total_salary": 5000}}
        success = cache_manager.set_many_monthly_summaries(results, 2025, 10)

        # Should return False on error
        self.assertFalse(success)
