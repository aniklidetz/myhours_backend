# Test Runners Comparison

## Overview

The MyHours backend project supports two test runners with different characteristics. Understanding these differences helps explain why test results may vary between different execution methods.

## Test Runner Comparison

### 1. Django's `manage.py test` (unittest)

**Command:**
```bash
python manage.py test
# or
DATABASE_URL="..." python manage.py test
```

**Characteristics:**
- Uses Django's built-in unittest test runner
- Discovers tests using Django's test discovery mechanism
- Default settings: Uses `myhours.settings` unless overridden
- Test count: **1531 tests**
- Test discovery: Only finds tests in Django app directories
- Coverage: No built-in coverage reporting
- Speed: Generally faster due to fewer tests
- Exit behavior: Runs all tests unless `--failfast` is specified

**Pros:**
- Simpler, fewer dependencies
- Standard Django approach
- Faster for quick local testing

**Cons:**
- Less flexible test discovery
- No built-in coverage
- Limited test filtering options

### 2. pytest (pre-push.sh uses this)

**Command:**
```bash
pytest
# or via pre-push
FULL=0 scripts/pre-push.sh
```

**Characteristics:**
- Uses pytest test runner
- Advanced test discovery with more patterns
- Settings: Uses `pytest.ini` configuration (`DJANGO_SETTINGS_MODULE=myhours.settings_ci`)
- Test count: **1770 tests** (239 more tests)
- Test discovery: Finds tests in multiple locations including `tests/` directory
- Coverage: Built-in coverage via `pytest-cov`
- Speed: Slower due to more tests and coverage calculation
- Exit behavior: Stops after `--maxfail=5` failures by default

**Pros:**
- More powerful test discovery
- Built-in coverage reporting
- Better test filtering and markers
- More detailed output options
- Parallel execution support

**Cons:**
- Additional dependency
- Slightly slower
- More configuration needed

## Why Test Results Differ

### 1. Different Test Count
- **pytest**: 1770 tests (finds tests in `tests/` directory + app tests)
- **manage.py test**: 1531 tests (only app tests)
- **Difference**: 239 additional tests found by pytest

### 2. Different Settings Files
- **pytest**: Uses `myhours.settings_ci` (from `pytest.ini`)
  - `LocMemCache` for caching (isolated, in-memory)
  - `MOCK_EXTERNAL_APIS=True` (mocks external API calls)
  - CI-optimized database configuration

- **manage.py test**: Uses `myhours.settings` (default)
  - May use Redis or other cache backends
  - External APIs may make real HTTP calls
  - Production-like configuration

### 3. External API Behavior

**Both test runners make real API calls by default:**
- Hebcal API (Jewish calendar)
- Sunrise-Sunset API (astronomical data)

**Why tests might fail:**
- Rate limiting (especially with 1770 tests)
- Network issues
- API changes or unexpected responses
- API returning `{'ok': True}` instead of actual data

**Solution:**
Tests that depend on external APIs should use pytest mocks/fixtures:
```python
@pytest.fixture
def mock_sunrise_sunset_api(mocker):
    return mocker.patch('requests.get')
```

**Note:** The service has built-in fallback to estimated times when API fails, so most tests should still pass even with API failures.

### 4. Cache Isolation

**pytest with LocMemCache:**
- Fresh cache for each test session
- No interference between tests
- Predictable cache behavior

**manage.py test with Redis:**
- Shared cache state
- May have stale data
- Tests may interfere with each other

## Common Test Failures in pre-push.sh

### 1. External API Errors (Sunrise-Sunset)

**Error:**
```
Sunrise-sunset API error for 2026-09-11: {'ok': True}
RuntimeError: Failed to get Friday sunset from API
```

**Cause:** Real HTTP calls to external API returning unexpected format

**Solution:** Ensure `MOCK_EXTERNAL_APIS=True` in `.env.test`

### 2. Shabbat/Holiday Test Failures

**Error:**
```
AssertionError: 'Shabbat' != 'Test Holiday'
```

**Cause:** Different Shabbat detection logic or database state

**Solution:** Use `--create-db` flag to ensure clean database

### 3. Rate Limiting Failures

**Error:**
```
AssertionError: 65 not less than or equal to 50 : Raw HTTP calls should be limited by caches
```

**Cause:** Cache not working or external APIs not mocked

**Solution:** Verify cache configuration in settings_ci.py

## Best Practices

### For Local Development

**Quick iteration (fastest):**
```bash
python manage.py test app_name
```

**Full validation before commit:**
```bash
FULL=0 scripts/pre-push.sh
```

### For Pre-Commit / Pre-Push

**Quick check (no coverage):**
```bash
FULL=0 scripts/pre-push.sh
```

**Full check with coverage:**
```bash
scripts/pre-push.sh
# or
FULL=1 scripts/pre-push.sh
```

### For CI/CD

Always use pytest with settings_ci:
```bash
pytest --cov=. --create-db
```

## Configuration Files

### pytest.ini
- Test discovery patterns
- Default markers
- Coverage settings
- Django settings module: `myhours.settings_ci`

### .env.test
- Used by `pre-push.sh`
- Database configuration
- External API mocking: `MOCK_EXTERNAL_APIS=True`

### myhours/settings_ci.py
- CI-specific Django settings
- `LocMemCache` for caching
- External API mocking support
- Lightweight configuration

### myhours/settings.py
- Production-like settings
- Used by `manage.py test` by default
- Real external API calls (unless mocked in tests)

## Troubleshooting

### "More tests in pytest than manage.py test"

This is normal. pytest discovers tests in additional locations:
- `tests/` directory (root level)
- Additional test patterns in `pytest.ini`

### "Tests pass with manage.py test but fail with pre-push.sh"

Common causes:
1. External API calls not mocked
2. Different cache behavior
3. Different database state
4. Additional tests found by pytest

**Solution:**
1. Ensure `MOCK_EXTERNAL_APIS=True` in `.env.test`
2. Use `--create-db` flag
3. Check `settings_ci.py` configuration

### "Tests fail with manage.py test but pass with pytest"

Common causes:
1. Cache contamination
2. Real API calls failing
3. Database state issues

**Solution:**
1. Clear cache before testing
2. Use test-specific database
3. Mock external APIs in test code

## Summary

| Feature | manage.py test | pytest (pre-push) |
|---------|---------------|-------------------|
| Test Count | 1531 | 1770 |
| Settings | settings.py | settings_ci.py |
| Cache | Redis (may vary) | LocMemCache |
| External APIs | Real calls | Mocked (if configured) |
| Coverage | No | Yes |
| Speed | Faster | Slower |
| Best For | Quick local testing | Pre-commit validation |

## Recommendations

1. **Use `manage.py test`** for quick local testing during development
2. **Use `FULL=0 scripts/pre-push.sh`** before committing
3. **Use `scripts/pre-push.sh`** before creating PR
4. **Always ensure** `MOCK_EXTERNAL_APIS=True` in `.env.test`
5. **Use `--create-db`** when debugging test failures
