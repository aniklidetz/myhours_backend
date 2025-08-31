"""
Global pytest configuration and fixtures
"""

import pytest

from django.core.cache import cache


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before each test to avoid stale data"""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def enable_project_payroll(settings):
    """Enable PROJECT_PAYROLL feature flag for tests that need it"""
    settings.FEATURE_FLAGS = getattr(settings, "FEATURE_FLAGS", {})
    settings.FEATURE_FLAGS["ENABLE_PROJECT_PAYROLL"] = True
    return settings
