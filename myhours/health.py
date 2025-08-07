"""
Health check views for DevOps monitoring
"""

import logging

import pymongo
import redis

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def health_check(request):
    """
    Comprehensive health check for all services
    """
    status = {"status": "healthy", "timestamp": None, "services": {}}

    # Check Django
    try:
        from django.utils import timezone

        status["timestamp"] = timezone.now().isoformat()
        status["services"]["django"] = {"status": "healthy"}
    except Exception as e:
        logger.exception("Django health check failed")
        status["services"]["django"] = {
            "status": "unhealthy",
            "error": "Service unavailable",
        }
        status["status"] = "unhealthy"

    # Check Database
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        status["services"]["postgresql"] = {"status": "healthy"}
    except Exception as e:
        logger.exception("PostgreSQL health check failed")
        status["services"]["postgresql"] = {
            "status": "unhealthy",
            "error": "Database connection failed",
        }
        status["status"] = "unhealthy"

    # Check Redis
    try:
        cache.set("health_check", "ok", 10)
        cache.get("health_check")
        status["services"]["redis"] = {"status": "healthy"}
    except Exception as e:
        logger.exception("Redis health check failed")
        status["services"]["redis"] = {
            "status": "unhealthy",
            "error": "Cache service unavailable",
        }
        status["status"] = "unhealthy"

    # Check MongoDB
    try:
        mongo_host = getattr(settings, "MONGO_HOST", "localhost")
        mongo_port = getattr(settings, "MONGO_PORT", 27017)
        client = pymongo.MongoClient(
            mongo_host, mongo_port, serverSelectionTimeoutMS=5000
        )
        client.server_info()
        status["services"]["mongodb"] = {"status": "healthy"}
    except Exception as e:
        logger.exception("MongoDB health check failed")
        status["services"]["mongodb"] = {
            "status": "unhealthy",
            "error": "MongoDB service unavailable",
        }
        status["status"] = "unhealthy"

    http_status = 200 if status["status"] == "healthy" else 503
    return JsonResponse(status, status=http_status)
