"""
Bulk cache manager for optimized Redis operations.

This module handles bulk caching operations using Redis pipelines
to minimize round-trips and maximize performance for mass operations.

Key features:
- Bulk get (MGET) for multiple cache keys in one operation
- Bulk set (pipeline) for multiple cache writes
- Compatible with PayrollRedisCache key format
- Cache warming and invalidation
"""

import json
import logging
import os
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

try:
    import redis

    from django.conf import settings

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from payroll.services.contracts import PayrollResult

from .types import CacheStats

logger = logging.getLogger(__name__)


class BulkCacheManager:
    """
    Bulk cache manager for high-performance Redis operations.

    Uses Redis pipeline to batch multiple operations into single round-trips,
    significantly improving performance for bulk calculations.
    """

    def __init__(self):
        """Initialize the bulk cache manager."""
        self.redis_client = None
        self.cache_available = False
        self._stats = CacheStats()

        if REDIS_AVAILABLE:
            try:
                # Try to use REDIS_URL from environment (Docker) or Django settings
                redis_url = os.environ.get("REDIS_URL") or getattr(
                    settings, "CELERY_BROKER_URL", None
                )

                if redis_url:
                    # Use redis.from_url() for URL-based connection (Docker-compatible)
                    self.redis_client = redis.from_url(
                        redis_url,
                        decode_responses=True,
                        socket_connect_timeout=5,
                        socket_timeout=5,
                    )
                    logger.info(
                        f"🔗 Connecting to Redis via URL: {redis_url.split('@')[0]}@..."
                    )
                else:
                    # Fallback to REDIS_CONFIG or defaults (for non-Docker setups)
                    redis_config = getattr(
                        settings,
                        "REDIS_CONFIG",
                        {
                            "host": "localhost",
                            "port": 6379,
                            "db": 0,
                            "decode_responses": True,
                        },
                    )
                    self.redis_client = redis.Redis(**redis_config)
                    logger.info(
                        f"🔗 Connecting to Redis via config: {redis_config.get('host')}:{redis_config.get('port')}"
                    )

                # Test connection
                self.redis_client.ping()
                self.cache_available = True
                logger.info("✅ BulkCacheManager initialized successfully")

            except Exception as e:
                logger.warning(f"⚠️ Redis not available for BulkCacheManager: {e}")
                self.cache_available = False
        else:
            logger.warning("⚠️ Redis package not installed for BulkCacheManager")

    def _make_key(self, prefix: str, *args) -> str:
        """
        Generate cache key compatible with PayrollRedisCache.

        Args:
            prefix: Key prefix (e.g., 'monthly_summary', 'daily_calc')
            *args: Additional key components

        Returns:
            str: Formatted cache key
        """
        key_parts = [prefix] + [str(arg) for arg in args]
        return ":".join(key_parts)

    def _serialize_decimal(self, obj):
        """Custom JSON serializer for Decimal objects."""
        if isinstance(obj, Decimal):
            return float(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    def get_many_monthly_summaries(
        self, employee_ids: List[int], year: int, month: int
    ) -> Dict[int, PayrollResult]:
        """
        Get cached monthly summaries for multiple employees in one operation.

        Uses MGET for efficient batch retrieval.

        Args:
            employee_ids: List of employee IDs
            year: Year of the period
            month: Month of the period

        Returns:
            Dict mapping employee_id to PayrollResult (only cached results)
        """
        if not self.cache_available or not employee_ids:
            return {}

        # Build cache keys
        keys = [
            self._make_key("monthly_summary", emp_id, year, month)
            for emp_id in employee_ids
        ]

        self._stats.total_keys += len(keys)

        try:
            # Use MGET for bulk retrieval (single round-trip)
            cached_values = self.redis_client.mget(keys)

            results = {}
            for emp_id, cached_value in zip(employee_ids, cached_values):
                if cached_value:
                    try:
                        results[emp_id] = json.loads(cached_value)
                        self._stats.hits += 1
                    except json.JSONDecodeError as e:
                        logger.warning(
                            f"Failed to decode cache for employee {emp_id}: {e}"
                        )
                        self._stats.misses += 1
                else:
                    self._stats.misses += 1

            logger.info(
                f"Bulk cache get: {len(results)}/{len(employee_ids)} hits",
                extra={
                    "cache_hits": len(results),
                    "cache_misses": len(employee_ids) - len(results),
                    "total_keys": len(employee_ids),
                    "action": "bulk_cache_get",
                },
            )

            return results

        except Exception as e:
            logger.error(f"Bulk cache get failed: {e}", exc_info=True)
            return {}

    def set_many_monthly_summaries(
        self, results: Dict[int, PayrollResult], year: int, month: int, ttl: int = 3600
    ) -> bool:
        """
        Cache monthly summaries for multiple employees using pipeline.

        Uses Redis pipeline to batch all SET operations into one round-trip.

        Args:
            results: Dict mapping employee_id to PayrollResult
            year: Year of the period
            month: Month of the period
            ttl: Time-to-live in seconds (default: 1 hour)

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.cache_available or not results:
            return False

        try:
            # Use pipeline for bulk write (single round-trip)
            pipeline = self.redis_client.pipeline()

            for emp_id, result in results.items():
                cache_key = self._make_key("monthly_summary", emp_id, year, month)

                # Serialize result to JSON
                serialized_data = json.dumps(result, default=self._serialize_decimal)

                # Add to pipeline
                pipeline.setex(cache_key, ttl, serialized_data)
                self._stats.sets += 1

            # Execute all operations at once
            pipeline.execute()

            logger.info(
                f"Bulk cache set: {len(results)} results cached",
                extra={"count": len(results), "ttl": ttl, "action": "bulk_cache_set"},
            )

            return True

        except Exception as e:
            logger.error(f"Bulk cache set failed: {e}", exc_info=True)
            return False

    def invalidate_employees(
        self, employee_ids: List[int], year: int, month: int
    ) -> int:
        """
        Invalidate cache for multiple employees.

        Args:
            employee_ids: List of employee IDs to invalidate
            year: Year of the period
            month: Month of the period

        Returns:
            int: Number of keys deleted
        """
        if not self.cache_available or not employee_ids:
            return 0

        try:
            # Build all keys to delete
            keys_to_delete = []

            for emp_id in employee_ids:
                # Monthly summary key
                monthly_key = self._make_key("monthly_summary", emp_id, year, month)
                keys_to_delete.append(monthly_key)

                # Daily calculation keys (using scan for pattern matching)
                # Note: This is slower, only use if necessary
                daily_pattern = self._make_key("daily_calc", emp_id, "*")
                daily_keys = self.redis_client.keys(daily_pattern)
                keys_to_delete.extend(daily_keys)

            # Delete all keys
            if keys_to_delete:
                deleted_count = self.redis_client.delete(*keys_to_delete)
                logger.info(
                    f"Invalidated {deleted_count} cache keys for {len(employee_ids)} employees",
                    extra={
                        "deleted_count": deleted_count,
                        "employee_count": len(employee_ids),
                        "action": "bulk_cache_invalidate",
                    },
                )
                return deleted_count

            return 0

        except Exception as e:
            logger.error(f"Bulk cache invalidation failed: {e}", exc_info=True)
            return 0

    def warm_up_cache(
        self, results: Dict[int, PayrollResult], year: int, month: int, ttl: int = 3600
    ) -> bool:
        """
        Warm up cache with calculation results.

        Alias for set_many_monthly_summaries with semantic meaning.

        Args:
            results: Calculation results to cache
            year: Year of the period
            month: Month of the period
            ttl: Time-to-live in seconds

        Returns:
            bool: True if successful
        """
        return self.set_many_monthly_summaries(results, year, month, ttl)

    def get_cache_stats(self) -> CacheStats:
        """
        Get cache statistics for this session.

        Returns:
            CacheStats: Statistics object with hits, misses, sets
        """
        return self._stats

    def reset_stats(self):
        """Reset cache statistics."""
        self._stats = CacheStats()

    def check_availability(self) -> bool:
        """
        Check if Redis cache is available.

        Returns:
            bool: True if cache is available and working
        """
        if not self.cache_available:
            return False

        try:
            self.redis_client.ping()
            return True
        except Exception:
            return False

    def flush_pattern(self, pattern: str) -> int:
        """
        Flush all keys matching a pattern.

        CAUTION: Use with care in production!

        Args:
            pattern: Redis key pattern (e.g., "monthly_summary:*")

        Returns:
            int: Number of keys deleted
        """
        if not self.cache_available:
            return 0

        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                deleted_count = self.redis_client.delete(*keys)
                logger.warning(
                    f"Flushed {deleted_count} keys matching pattern: {pattern}",
                    extra={"pattern": pattern, "deleted_count": deleted_count},
                )
                return deleted_count
            return 0

        except Exception as e:
            logger.error(f"Pattern flush failed: {e}", exc_info=True)
            return 0


# Global instance for convenience
bulk_cache = BulkCacheManager()
