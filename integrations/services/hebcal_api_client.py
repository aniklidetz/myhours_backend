"""
Hebcal API Client - Focused solely on communication with Hebcal API

This service is responsible for:
- Making HTTP requests to Hebcal API
- Parsing and filtering API responses
- Caching API responses
- Handling API errors gracefully
- Rate limiting to respect API limits
- Retry logic with exponential backoff

It does NOT handle:
- Database operations
- Business logic orchestration
- Shabbat time calculations
"""

import logging
import time
from datetime import date

import requests

from django.core.cache import cache

logger = logging.getLogger(__name__)


class HebcalAPIClient:
    """
    Client for interacting with the Hebcal API to retrieve Jewish holiday data.

    This client focuses solely on API communication and response parsing,
    following the single responsibility principle.

    Features:
    - Automatic rate limiting (1 request per second minimum)
    - Retry logic with exponential backoff
    - Response caching (7 days)
    """

    BASE_URL = "https://www.hebcal.com/hebcal"
    CACHE_KEY_PREFIX = "hebcal_holidays_"
    CACHE_TIMEOUT = 60 * 60 * 24 * 7  # 7 days as recommended

    # Rate limiting settings
    MIN_REQUEST_INTERVAL = 1.0  # Minimum 1 second between requests
    _last_request_time = None  # Class variable to track last request time

    # Retry settings
    MAX_RETRIES = 3  # Maximum retry attempts
    RETRY_BACKOFF_BASE = 2  # Base for exponential backoff (2^attempt seconds)
    REQUEST_TIMEOUT = 10  # Request timeout in seconds

    @classmethod
    def _rate_limit(cls):
        """
        Enforce rate limiting to prevent API abuse.

        Ensures minimum time interval between API requests.
        If the last request was too recent, sleeps until enough time has passed.
        """
        if cls._last_request_time is not None:
            elapsed = time.time() - cls._last_request_time
            if elapsed < cls.MIN_REQUEST_INTERVAL:
                sleep_time = cls.MIN_REQUEST_INTERVAL - elapsed
                logger.debug(
                    f"Rate limiting: sleeping {sleep_time:.2f}s before next request"
                )
                time.sleep(sleep_time)

        cls._last_request_time = time.time()

    @classmethod
    def fetch_holidays(cls, year=None, month=None, use_cache=True):
        """
        Fetch holiday data from Hebcal API for a specific year/month.

        Features:
        - Automatic caching (7 days)
        - Rate limiting (1 req/sec minimum)
        - Retry logic with exponential backoff
        - Comprehensive error handling

        Args:
            year (int, optional): Year for the request. Defaults to current year.
            month (int, optional): Month for the request. Defaults to all months.
            use_cache (bool): Whether to use caching. Defaults to True.

        Returns:
            list: List of holiday items filtered by year and category.
                  Returns empty list on error.
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

        # Retry loop with exponential backoff
        last_exception = None
        for attempt in range(cls.MAX_RETRIES):
            try:
                # Apply rate limiting before request
                cls._rate_limit()

                logger.info(
                    f"Fetching holidays from Hebcal API for year {year} "
                    f"(attempt {attempt + 1}/{cls.MAX_RETRIES})"
                )

                response = requests.get(
                    cls.BASE_URL, params=params, timeout=cls.REQUEST_TIMEOUT
                )
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

            except requests.exceptions.Timeout as e:
                last_exception = e
                logger.warning(
                    f"Request timeout on attempt {attempt + 1}/{cls.MAX_RETRIES}: {e}"
                )

            except requests.exceptions.HTTPError as e:
                last_exception = e
                # Don't retry on 4xx client errors (except 429 Too Many Requests)
                if e.response is not None and 400 <= e.response.status_code < 500:
                    if e.response.status_code == 429:
                        logger.warning(
                            f"Rate limit hit (429) on attempt {attempt + 1}/{cls.MAX_RETRIES}"
                        )
                    else:
                        logger.error(f"Client error (4xx): {e}")
                        return []  # Don't retry on client errors
                else:
                    logger.warning(
                        f"HTTP error on attempt {attempt + 1}/{cls.MAX_RETRIES}: {e}"
                    )

            except requests.exceptions.RequestException as e:
                last_exception = e
                logger.warning(
                    f"Network error on attempt {attempt + 1}/{cls.MAX_RETRIES}: {e}"
                )

            except Exception as e:
                last_exception = e
                logger.warning(
                    f"Unexpected error on attempt {attempt + 1}/{cls.MAX_RETRIES}: {e}"
                )

            # Exponential backoff before retry (except on last attempt)
            if attempt < cls.MAX_RETRIES - 1:
                backoff_time = cls.RETRY_BACKOFF_BASE**attempt
                logger.info(f"Waiting {backoff_time}s before retry...")
                time.sleep(backoff_time)

        # All retries failed
        from core.logging_utils import err_tag

        logger.error(
            f"Failed to fetch holidays after {cls.MAX_RETRIES} attempts",
            extra={"err": err_tag(last_exception)} if last_exception else {},
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
