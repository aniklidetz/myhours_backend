# External API Testing Strategy

## Problem

Tests that depend on external APIs (Hebcal, Sunrise-Sunset) can fail due to:
- Network issues
- Rate limiting
- API changes
- Unexpected API responses (e.g., `{'ok': True}` instead of actual data)

**Example error:**
```
Sunrise-sunset API error for 2026-01-02: {'ok': True}
RuntimeError: Failed to get Friday sunset from API
```

## Wrong Approach (What NOT to Do)

**❌ DO NOT mock APIs in production code:**

```python
# WRONG - Don't do this in services
def _get_api_times(self, date_obj):
    if settings.MOCK_EXTERNAL_APIS:  # ❌ Bad!
        return None
    # ... real API call
```

**Why this is wrong:**
- Production code should not have test-specific logic
- Violates separation of concerns
- Can accidentally disable APIs in production
- Makes it impossible to test real API integration

## Correct Approach

### 1. Production Code: No Mocking

Production services should make real API calls:

```python
# integrations/services/unified_shabbat_service.py
def _get_api_times(self, date_obj, lat, lng):
    """Make API call to sunrise-sunset.org"""
    response = requests.get(self.BASE_URL, params=params, timeout=10)
    # ... handle response
```

### 2. Tests: Use Pytest Fixtures with autouse

**SOLUTION:** Add autouse fixture in `payroll/tests/conftest.py`:

```python
from unittest.mock import Mock, patch
import pytest

@pytest.fixture(autouse=True)
def mock_sunrise_sunset_api_payroll():
    """
    Auto-mock sunrise-sunset API for all payroll tests to prevent real HTTP calls.

    This prevents external API failures during test runs.
    Tests that need specific responses can override this by patching again.
    """
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "OK",
        "results": {
            "sunrise": "2025-01-17T06:30:00+00:00",
            "sunset": "2025-01-17T16:45:00+00:00",
            "solar_noon": "2025-01-17T11:37:30+00:00",
            "day_length": "10:15:00",
        },
    }

    with patch(
        "integrations.services.unified_shabbat_service.requests.get",
        return_value=mock_response,
    ) as mock_get:
        yield mock_get
```

Mock external APIs **only in tests** using pytest fixtures:

```python
# tests/conftest.py or test file
@pytest.fixture
def mock_sunrise_sunset_api(mocker):
    """Mock sunrise-sunset API for tests"""
    mock_response = mocker.Mock()
    mock_response.json.return_value = {
        "status": "OK",
        "results": {
            "sunset": "2024-01-05T16:30:15+00:00",
            "sunrise": "2024-01-05T06:45:00+00:00"
        }
    }
    mock_response.status_code = 200

    return mocker.patch(
        'integrations.services.unified_shabbat_service.requests.get',
        return_value=mock_response
    )

# In test
def test_get_shabbat_times(mock_sunrise_sunset_api):
    service = UnifiedShabbatService()
    result = service.get_shabbat_times(date(2024, 1, 5))
    assert result["shabbat_start"] is not None
```

### 3. Built-in Fallbacks

The production code already has fallback mechanisms:

```python
def get_shabbat_times(self, date_obj):
    try:
        # Try API call
        result = self._calculate_precise_times(...)
        return result
    except Exception:
        # Fallback to estimated times
        return create_fallback_shabbat_times(...)
```

This means:
- Tests can still pass even if API fails
- Production continues to work with estimated times
- No need for test-specific code in production

## When Tests Fail Due to External APIs

### Symptoms

```
Sunrise-sunset API error for 2026-09-11: {'ok': True}
RuntimeError: Failed to get Friday sunset from API
```

### Why This Happens

1. **Real API calls in tests** - Tests are making actual HTTP requests
2. **Rate limiting** - Too many requests (1770 tests × multiple API calls)
3. **API changes** - External API returns unexpected format
4. **Network issues** - API is down or unreachable

### Solutions

**Option 1: Use VCR.py (Recommended for integration tests)**

Record real API responses once, replay in tests:

```python
# pip install vcrpy pytest-vcr

@pytest.mark.vcr()
def test_shabbat_integration():
    # First run: makes real API call and records
    # Subsequent runs: replays recorded response
    service = UnifiedShabbatService()
    result = service.get_shabbat_times(date(2024, 1, 5))
```

**Option 2: Mock in specific tests**

```python
@pytest.fixture(autouse=True)
def mock_external_apis(mocker):
    """Auto-mock for all tests in this file"""
    mocker.patch('requests.get', side_effect=mock_api_response)
```

**Option 3: Accept fallback behavior**

Some tests can accept fallback times:

```python
def test_handles_api_failure():
    # This test verifies fallback works
    service = UnifiedShabbatService()
    result = service.get_shabbat_times(date(2024, 1, 5))
    # Even with API failure, we get valid times
    assert result["is_estimated"] == True
```

## Best Practices

### DO:
✅ Mock external APIs in test fixtures
✅ Use VCR.py for integration tests
✅ Test both success and failure scenarios
✅ Keep production code free of test logic
✅ Use fallback mechanisms in production code

### DON'T:
❌ Add `if settings.MOCK_...` in production code
❌ Make production behavior depend on test settings
❌ Disable real API calls globally
❌ Ignore test failures due to external APIs
❌ Commit test-specific code to production services

## Example: Complete Test Setup

```python
# tests/integrations/conftest.py
import pytest
from datetime import datetime

@pytest.fixture
def mock_hebcal_api(mocker):
    """Mock Hebcal API responses"""
    def mock_fetch(year=None, month=None, use_cache=True):
        return [
            {
                "date": "2024-09-11",
                "title": "Rosh Hashana",
                "category": "holiday"
            }
        ]

    return mocker.patch(
        'integrations.services.hebcal_api_client.HebcalAPIClient.fetch_holidays',
        side_effect=mock_fetch
    )

@pytest.fixture
def mock_sunrise_api(mocker):
    """Mock Sunrise-Sunset API"""
    mock_resp = mocker.Mock()
    mock_resp.json.return_value = {
        "status": "OK",
        "results": {
            "sunset": datetime.now().isoformat(),
            "sunrise": datetime.now().isoformat()
        }
    }
    mock_resp.status_code = 200
    return mocker.patch('requests.get', return_value=mock_resp)

# tests/integrations/test_shabbat_service.py
def test_get_shabbat_times_with_api(mock_sunrise_api, mock_hebcal_api):
    """Test with mocked external APIs"""
    service = UnifiedShabbatService()
    result = service.get_shabbat_times(date(2024, 1, 5))

    assert result["is_estimated"] == False
    assert "shabbat_start" in result
```

## Summary

- **Production code**: Make real API calls, handle failures gracefully
- **Test code**: Mock APIs using pytest fixtures with `autouse=True` in conftest.py
- **Integration tests**: Use VCR.py to record/replay real responses (optional)
- **Never**: Add test-specific logic to production code

## Implementation Status

✅ **FIXED (2025-10-14):**
- Added `@pytest.fixture(autouse=True)` in root `conftest.py`
- Mocks `requests.get` in `unified_shabbat_service.py` to return correct API format
- All tests across ALL modules now use mocked API responses by default
- Tests no longer fail with `{'ok': True}` error from external API

**Files changed:**
- `/conftest.py` - Made `mock_sunrise_sunset_api` fixture autouse (applies globally to all tests)
- `/payroll/tests/conftest.py` - Removed duplicate fixture (now using global one)
- `/payroll/tests/test_api_integrations.py` - Fixed mock response format in `test_api_rate_limiting_respect`

**Why root conftest.py?**
- Fixtures in root `conftest.py` apply to ALL test directories (payroll/, integrations/, worktime/, etc.)
- Fixtures in module-specific conftest.py only apply to that module
- We need API mocking everywhere, not just in payroll tests
