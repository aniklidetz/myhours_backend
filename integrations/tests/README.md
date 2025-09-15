# Integration Tests

This directory contains tests for all integration services.

## Test Files

### Core Service Tests
1. **test_hebcal_api_client.py** - Tests for HebcalAPIClient service (11 tests)
   - API communication and response parsing
   - Caching mechanisms and cache invalidation
   - Error handling and retries
   - Parameter validation

2. **test_holiday_sync_service.py** - Tests for HolidaySyncService (12 tests)
   - Holiday synchronization orchestration
   - Database operations and data preservation
   - Special Shabbat and weekly Shabbat syncing
   - Error recovery and transaction handling

3. **test_holiday_utility_service.py** - Tests for HolidayUtilityService (30 tests)
   - Holiday query utilities
   - Database lookups with API fallback
   - Holiday type checking (is_holiday, is_shabbat, is_special_shabbat)
   - Comprehensive error handling

### Integration Tests
4. **test_integration_apis.py** - Cross-service integration tests (17 tests)
   - Cache behavior across services
   - Error handling in service interactions
   - Performance with real-world scenarios
   - API rate limiting and fallback mechanisms

5. **test_unified_shabbat_service.py** - Comprehensive tests for UnifiedShabbatService (18 tests)
6. **test_external_apis.py** - Tests for external API integrations: Hebcal, Sunrise/Sunset (25 tests)
7. **test_utils.py** - Tests for utility functions, specifically safe_to_json (27 tests)
8. **test_shabbat_service_reliability.py** - Performance and reliability tests
9. **test_unified_shabbat_service_no_db.py** - Database-free logic tests

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

### Holiday Service Tests (test_hebcal_api_client.py, test_holiday_sync_service.py, test_holiday_utility_service.py)
- **HebcalAPIClient** - 11 tests for API communication and caching
- **HolidaySyncService** - 12 tests for synchronization orchestration
- **HolidayUtilityService** - 30 tests for utility functions and queries

### External API Tests (test_external_apis.py)
- **HebcalServiceTest** - 9 tests for Jewish holiday API integration
- **SunriseSunsetServiceTest** - Tests for sunrise/sunset API

### Integration Tests (test_integration_apis.py)
- **IntegrationCacheTest** - 2 tests for caching mechanisms
- **IntegrationErrorHandlingTest** - 5 tests for error scenarios
- **IntegrationPerformanceTest** - 2 tests for performance monitoring

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

**All tests passing** (140+ tests total)
- HebcalAPIClient: 11/11
- HolidaySyncService: 12/12
- HolidayUtilityService: 30/30
- Integration APIs: 17/17
- UnifiedShabbatService: 18/18
- External APIs: 25/25
- Utils: 27/27
- Reliability: 15/15 (includes 1 slow performance test)
- No-DB tests: 11/11

**Performance Note:**
- Fast tests: ~70 tests in ~50s
- Slow tests: 1 test (~90s) - makes ~104 real API calls for comprehensive testing 

**Current Coverage Areas:**
- Holiday API communication and response parsing
- Holiday synchronization and database operations
- Holiday query utilities with fallback mechanisms
- Shabbat time calculations with Jewish law compliance
- External API integrations (Hebcal, Sunrise/Sunset)
- JSON parsing utilities
- Caching mechanisms across services
- Error handling and fallbacks
- Performance validation

**Migration Status:**
- HebcalService refactored into specialized services (HebcalAPIClient, HolidaySyncService, HolidayUtilityService)
- UnifiedShabbatService ready for production migration
- All legacy service calls migrated to new architecture