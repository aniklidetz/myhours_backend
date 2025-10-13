"""
Hebcal API Client - Focused solely on communication with Hebcal API

This service is responsible for:
- Making HTTP requests to Hebcal API
- Parsing and filtering API responses
- Caching API responses
- Handling API errors gracefully

It does NOT handle:
- Database operations
- Business logic orchestration
- Shabbat time calculations
"""

import logging
from datetime import date

import requests

from django.core.cache import cache

logger = logging.getLogger(__name__)


class HebcalAPIClient:
    """
    Client for interacting with the Hebcal API to retrieve Jewish holiday data.

    This client focuses solely on API communication and response parsing,
    following the single responsibility principle.
    """

    BASE_URL = "https://www.hebcal.com/hebcal"
    CACHE_KEY_PREFIX = "hebcal_holidays_"
    CACHE_TIMEOUT = 60 * 60 * 24 * 7  # 7 days as recommended

    @classmethod
    def fetch_holidays(cls, year=None, month=None, use_cache=True):
        """
        Fetch holiday data from Hebcal API for a specific year/month.

        Args:
            year (int, optional): Year for the request. Defaults to current year.
            month (int, optional): Month for the request. Defaults to all months.
            use_cache (bool): Whether to use caching. Defaults to True.

        Returns:
            list: List of holiday items filtered by year and category
        """
        if year is None:
            year = date.today().year

        # Generate cache key
        cache_key = f"{cls.CACHE_KEY_PREFIX}{year}"
        if month:
            cache_key += f"_{month}"

        # Check cache if enabled
        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.debug(f"Using cached holiday data for {year}")
                return cached_data

        # Prepare request parameters
        params = cls._build_request_params(year, month)

        try:
            logger.info(f"Fetching holidays from Hebcal API for year {year}")
            response = requests.get(cls.BASE_URL, params=params)
            response.raise_for_status()

            # Parse response
            from integrations.utils import safe_to_json

            raw_data = safe_to_json(response)

            # Filter and parse holiday items
            holidays = cls._parse_holiday_items(raw_data, year)

            logger.info(f"Successfully retrieved {len(holidays)} holidays")

            # Cache results if enabled
            if use_cache:
                cache.set(cache_key, holidays, cls.CACHE_TIMEOUT)

            return holidays

        except Exception as e:
            from core.logging_utils import err_tag

            logger.error(
                "Error fetching holidays from Hebcal API", extra={"err": err_tag(e)}
            )
            return []

    @classmethod
    def _build_request_params(cls, year, month=None):
        """Build request parameters for Hebcal API."""
        params = {
            "v": 1,
            "cfg": "json",
            "year": year,
            "ss": "on",  # Include Shabbats
            "c": "on",  # Use Gregorian calendar
            "maj": "on",  # Major holidays
            "min": "on",  # Minor holidays
            "nx": "on",  # Modern holidays
            "i": "on",  # Israel holidays (not diaspora)
        }

        if month:
            params["month"] = month

        return params

    @classmethod
    def _parse_holiday_items(cls, raw_data, year):
        """
        Parse and filter holiday items from API response.

        Args:
            raw_data (dict): Raw API response data
            year (int): Year to filter by

        Returns:
            list: Filtered holiday items
        """
        items = [
            item
            for item in raw_data.get("items", [])
            if item.get("category") == "holiday" and item["date"].startswith(str(year))
        ]

        # Log filtering for debugging
        total_items = len(raw_data.get("items", []))
        if total_items != len(items):
            logger.debug(f"Filtered {total_items} → {len(items)} items for year {year}")

        return items
