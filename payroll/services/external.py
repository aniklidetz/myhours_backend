# External API gateway for payroll services
# This module provides a unified interface for external API calls
# and supports test mocking through standard import paths

from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

# Global cache to prevent API rate limiting issues in tests
_api_cache = {}

def get_holidays(year: int, month: int) -> Dict[str, Any]:
    """
    Get holiday data from external API (HebCal).
    
    Args:
        year: Year to get holidays for
        month: Month to get holidays for
        
    Returns:
        Dict containing holiday data
    """
    cache_key = f"holidays_{year}_{month}"
    
    if cache_key in _api_cache:
        return _api_cache[cache_key]
    
    try:
        # Import here to allow mocking
        from integrations.services.hebcal_service import HebcalService
        
        hebcal_service = HebcalService()
        holidays = hebcal_service.get_holidays(year, month)
        
        _api_cache[cache_key] = holidays
        return holidays
    except Exception as e:
        logger.warning(f"Failed to get holidays from external API: {e}")
        return {}


def get_sabbath_times(year: int, month: int) -> Dict[str, Any]:
    """
    Get Sabbath times from external API (Sunrise/Sunset Service).
    
    Args:
        year: Year to get Sabbath times for
        month: Month to get Sabbath times for
        
    Returns:
        Dict containing Sabbath times data
    """
    cache_key = f"sabbath_{year}_{month}"
    
    if cache_key in _api_cache:
        return _api_cache[cache_key]
    
    try:
        # Import here to allow mocking
        from integrations.services.unified_shabbat_service import get_shabbat_times
        from datetime import date

        # For unified service, we need a specific date, not year/month
        # Use first day of month as reference
        date_obj = date(year, month, 1)
        sabbath_times = get_shabbat_times(date_obj)
        
        _api_cache[cache_key] = sabbath_times
        return sabbath_times
    except Exception as e:
        logger.warning(f"Failed to get sabbath times from external API: {e}")
        return {}


def clear_cache():
    """Clear the API cache. Useful for tests."""
    global _api_cache
    _api_cache.clear()