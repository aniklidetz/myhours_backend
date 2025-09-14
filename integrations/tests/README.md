# Integration Tests

This directory contains tests for all integration services.

## Test Files

1. **test_unified_shabbat_service.py** - Comprehensive tests for UnifiedShabbatService (18 tests)
2. **test_external_apis.py** - Tests for external API integrations: Hebcal, Sunrise/Sunset (25 tests)
3. **test_utils.py** - Tests for utility functions, specifically safe_to_json (27 tests)
4. **test_shabbat_service_reliability.py** - Performance and reliability tests
5. **test_unified_shabbat_service_no_db.py** - Database-free logic tests

## Running Tests

### Prerequisites
- Docker containers must be running: `docker-compose up -d`
- Check containers status: `docker-compose ps`

### Quick Start - Use Convenience Scripts

```bash
# Run fast integration tests (excludes slow performance tests)
./scripts/test_integrations.sh

# Run ALL integration tests including slow ones (95+ tests)
export DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_db"
python -m pytest integrations/tests/ -v --no-cov

# Run specific test file
./scripts/test_integrations.sh test_utils.py
./scripts/test_integrations.sh test_external_apis.py
./scripts/test_integrations.sh test_unified_shabbat_service.py

# Run Shabbat-specific tests only
./scripts/test_shabbat_with_db.sh

# Run only slow tests
python -m pytest integrations/tests/ -v --no-cov -m "slow"
```

### Manual Execution with Correct Database

```bash
# Set database URL (required for Django TestCase)
export DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_db"

# Run all integration tests
python -m pytest integrations/tests/ -v --no-cov

# Run specific test file
python -m pytest integrations/tests/test_utils.py -v --no-cov
python -m pytest integrations/tests/test_external_apis.py -v --no-cov

# Run specific test class
python -m pytest integrations/tests/test_external_apis.py::HebcalServiceTest -v --no-cov

# Run specific test method
python -m pytest integrations/tests/test_utils.py::SafeToJsonTest::test_dict_input_returned_as_is -v --no-cov
```

## Test Categories

### Shabbat Service Tests (test_unified_shabbat_service.py)
- **Contract Tests** - Verify ShabbatTimes TypedDict compliance
- **Correctness Tests** - Verify Jewish law compliance (18/42 min buffers)
- **Comparison Tests** - Compare with old services for migration validation
- **Performance Tests** - Check response times and caching
- **Edge Cases** - API failures, invalid dates, fallback behavior

### External API Tests (test_external_apis.py)
- **HebcalServiceTest** - 9 tests for Jewish holiday API integration
- **SunriseSunsetServiceTest** - 7 tests for sunset/sunrise API
- **IntegrationCacheTest** - 3 tests for caching mechanisms
- **IntegrationErrorHandlingTest** - 4 tests for error scenarios
- **IntegrationPerformanceTest** - 2 tests for performance validation

### Utility Tests (test_utils.py)
- **SafeToJsonTest** - 27 tests covering all edge cases of JSON parsing
  - Dict inputs
  - Bytes/bytearray inputs
  - String inputs
  - Response object handling
  - Unicode error handling
  - Fallback scenarios

## Database Configuration

These tests use Django's TestCase which requires database access.

**Default credentials (from docker-compose.yml):**
- User: `myhours_user`
- Password: `secure_password_123`
- Database: `myhours_db`
- Host: `localhost`
- Port: `5432`

## Troubleshooting

### Database Connection Issues
If you see `password authentication failed`:
1. Ensure Docker is running: `docker-compose ps`
2. Use correct credentials: `myhours_user` / `secure_password_123`
3. Use convenience scripts which set DATABASE_URL automatically

### Test Timeouts
Some tests make real API calls and may timeout:
- Use `--timeout=300` flag for longer timeout
- API tests are mocked by default but can be run live

### Permission Issues
```bash
chmod +x scripts/test_integrations.sh
chmod +x scripts/test_shabbat_with_db.sh
```

## Test Status

✅ **All tests passing** (95+ tests total)
- UnifiedShabbatService: 18/18 ✅
- External APIs: 25/25 ✅
- Utils: 27/27 ✅
- Reliability: 15/15 ✅ (includes 1 slow performance test)
- No-DB tests: 11/11 ✅

**Performance Note:**
- Fast tests: ~70 tests in ~50s
- Slow tests: 1 test (~90s) - makes ~104 real API calls for comprehensive testing 

**Current Coverage Areas:**
- Shabbat time calculations with Jewish law compliance
- External API integrations (Hebcal, Sunrise/Sunset)
- JSON parsing utilities
- Caching mechanisms
- Error handling and fallbacks
- Performance validation

**Migration Status:**
 UnifiedShabbatService ready for production migration