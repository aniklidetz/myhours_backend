"""
Redis Configuration with High Availability Support
Supports both single Redis instance and Redis Sentinel setups
"""

from urllib.parse import urlparse

from decouple import config


def get_redis_cache_config():
    """
    Get Redis cache configuration with automatic failover support
    Returns appropriate cache configuration based on environment
    """

    # Check if Redis Sentinel is enabled
    USE_REDIS_SENTINEL = config("USE_REDIS_SENTINEL", default=False, cast=bool)
    REDIS_URL = config("REDIS_URL", default="redis://localhost:6379/0")

    if USE_REDIS_SENTINEL:
        # Redis Sentinel Configuration
        SENTINEL_HOSTS = config(
            "REDIS_SENTINEL_HOSTS",
            default="redis-sentinel-1:26379,redis-sentinel-2:26379,redis-sentinel-3:26379",
        )
        SENTINEL_SERVICE_NAME = config(
            "REDIS_SENTINEL_SERVICE", default="myhours-master"
        )
        REDIS_PASSWORD = config("REDIS_PASSWORD", default=None)
        REDIS_DB = config("REDIS_DB", default=0, cast=int)

        # Parse sentinel hosts
        sentinel_hosts = []
        for host_port in SENTINEL_HOSTS.split(","):
            host, port = host_port.strip().split(":")
            sentinel_hosts.append((host, int(port)))

        cache_config = {
            "default": {
                "BACKEND": "django_redis.cache.RedisCache",
                "LOCATION": [
                    f"redis://{sentinel_hosts[0][0]}:{sentinel_hosts[0][1]}/{REDIS_DB}",
                    f"redis://{sentinel_hosts[1][0]}:{sentinel_hosts[1][1]}/{REDIS_DB}",
                    f"redis://{sentinel_hosts[2][0]}:{sentinel_hosts[2][1]}/{REDIS_DB}",
                ],
                "OPTIONS": {
                    "CLIENT_CLASS": "django_redis.client.SentinelClient",
                    "CONNECTION_POOL_KWARGS": {
                        "service_name": SENTINEL_SERVICE_NAME,
                        "socket_connect_timeout": 5,
                        "socket_timeout": 5,
                        "retry_on_timeout": True,
                        "max_connections": 20,
                        "db": REDIS_DB,
                    },
                    "SENTINEL_KWARGS": {
                        "socket_connect_timeout": 3,
                        "socket_timeout": 3,
                    },
                },
                "TIMEOUT": 300,
                "VERSION": 1,
                "KEY_PREFIX": "myhours",
            }
        }

        # Add password if provided
        if REDIS_PASSWORD:
            cache_config["default"]["OPTIONS"]["CONNECTION_POOL_KWARGS"][
                "password"
            ] = REDIS_PASSWORD
            cache_config["default"]["OPTIONS"]["SENTINEL_KWARGS"][
                "password"
            ] = REDIS_PASSWORD

        return cache_config

    else:
        # Single Redis Instance Configuration
        try:
            redis_url = urlparse(REDIS_URL)
            REDIS_HOST = redis_url.hostname or "localhost"
            REDIS_PORT = redis_url.port or 6379
            REDIS_DB = int(redis_url.path.lstrip("/")) if redis_url.path else 0
            REDIS_PASSWORD = redis_url.password
        except Exception:
            # Fallback values if URL parsing fails
            REDIS_HOST = "localhost"
            REDIS_PORT = 6379
            REDIS_DB = 0
            REDIS_PASSWORD = None

        cache_config = {
            "default": {
                "BACKEND": "django_redis.cache.RedisCache",
                "LOCATION": f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
                "OPTIONS": {
                    "CLIENT_CLASS": "django_redis.client.DefaultClient",
                    "CONNECTION_POOL_KWARGS": {
                        "max_connections": 20,
                        "retry_on_timeout": True,
                        "socket_connect_timeout": 5,
                        "socket_timeout": 5,
                    },
                },
                "TIMEOUT": 300,
                "VERSION": 1,
                "KEY_PREFIX": "myhours",
            }
        }

        # Add Redis password if provided
        if REDIS_PASSWORD:
            cache_config["default"]["OPTIONS"]["CONNECTION_POOL_KWARGS"][
                "password"
            ] = REDIS_PASSWORD

        return cache_config


def get_cache_config_with_fallback():
    """
    Get cache configuration with fallback to LocMem for testing/development
    """
    import sys

    TESTING = "test" in sys.argv
    USE_LOCMEM_CACHE = config("USE_LOCMEM_CACHE", default=False, cast=bool)

    # Use LocMem cache for testing or when explicitly requested
    if TESTING or USE_LOCMEM_CACHE:
        return {
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "myhours-cache",
                "TIMEOUT": 300,
                "OPTIONS": {
                    "MAX_ENTRIES": 10000,
                },
            }
        }

    # Try Redis configuration with graceful fallback
    try:
        return get_redis_cache_config()
    except Exception as e:
        print(f"Redis configuration failed: {e}")
        print("Falling back to LocMem cache")
        return {
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "myhours-cache-fallback",
                "TIMEOUT": 300,
            }
        }


# Cache configuration for different cache types
CACHE_TTL = {
    "biometric": 600,  # 10 minutes for face recognition cache
    "shabbat": 7 * 24 * 3600,  # 7 days for Shabbat times
    "holidays": 30 * 24 * 3600,  # 30 days for holiday data
    "api": 3600,  # 1 hour for API responses
    "health": 10,  # 10 seconds for health checks
    "session": 86400,  # 1 day for session data
}

# Cache key patterns
CACHE_KEYS = {
    "biometric_match": "bio:match:{employee_id}:{hash}",
    "shabbat_times": "shabbat:{date}:{lat}:{lng}",
    "holiday_data": "holidays:{year}",
    "api_response": "api:{endpoint}:{params_hash}",
    "health_check": "health:check",
}
