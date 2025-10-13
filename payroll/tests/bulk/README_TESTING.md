# Bulk Payroll Testing Guide

## Important: Multiprocessing in Tests

### The Problem

Django tests + `ProcessPoolExecutor` (multiprocessing) can cause test hangs due to:

1. **Database Connection Issues**: Each subprocess tries to access the test database, causing connection conflicts
2. **Transaction Isolation**: Django's test framework uses transactions that don't propagate to subprocesses
3. **Fork Safety**: Forking after Django setup can cause unpredictable behavior

### Solution

**All bulk service tests should use `use_parallel=False`** to avoid these issues:

```python
# CORRECT - Tests will complete
service = BulkEnhancedPayrollService(
    use_cache=False,
    use_parallel=False  # Disable parallel in tests
)

# WRONG - Tests will hang indefinitely
service = BulkEnhancedPayrollService(
    use_cache=False,
    use_parallel=True  # Will cause hanging in Django tests
)
```

### Testing Parallel Mode

To test parallel execution:

1. **Unit tests**: Mock the executor and verify it's called correctly
2. **Integration tests**: Run separate standalone scripts (not Django tests)
3. **Manual testing**: Use the management command with real data

Example standalone test script:

```python
# test_parallel_standalone.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from payroll.services.bulk import BulkEnhancedPayrollService

# This can safely use parallel mode outside of Django test framework
service = BulkEnhancedPayrollService(use_parallel=True)
result = service.calculate_bulk([1, 2, 3], 2025, 10)
print(f"Success: {result.successful_count}")
```

### Management Command Testing

The safest way to test parallel mode:

```bash
# Small batch (uses threads)
python manage.py bulk_calculate_payroll --year 2025 --month 10 --employees 1,2,3,4,5

# Large batch (uses processes)
python manage.py bulk_calculate_payroll --year 2025 --month 10

# Force sequential for comparison
python manage.py bulk_calculate_payroll --year 2025 --month 10 --no-parallel
```

## Test Guidelines

### DO:
- Always use `use_parallel=False` in Django tests
- Test bulk logic with sequential processing
- Mock the executor to verify parallel code paths
- Test parallel mode with management commands
- Document multiprocessing limitations

### DON'T:
- Enable `use_parallel=True` in Django tests
- Use `ProcessPoolExecutor` directly in tests
- Fork processes after Django test setup
- Expect test database access from subprocesses

## Common Test Patterns

### Testing Bulk Calculations (Sequential)

```python
def test_bulk_calculation(self):
    service = BulkEnhancedPayrollService(
        use_cache=False,
        use_parallel=False  # Critical for tests
    )

    result = service.calculate_bulk(
        employee_ids=[1, 2, 3],
        year=2025,
        month=10,
        save_to_db=False
    )

    self.assertEqual(result.successful_count, 3)
```

### Mocking Parallel Executor

```python
@patch('payroll.services.bulk.bulk_service.AdaptiveExecutor')
def test_parallel_executor_called(self, mock_executor_class):
    """Test that parallel executor is instantiated correctly."""
    mock_instance = MagicMock()
    mock_executor_class.return_value = mock_instance

    service = BulkEnhancedPayrollService(use_parallel=True)

    # This won't actually run in parallel due to mocking
    # but verifies the code path is correct
    # ...
```

## Why This Matters

Without this fix:
- Tests hang indefinitely waiting for subprocess responses
- CI/CD pipelines timeout
- Developers can't run tests locally
- Coverage drops because tests are skipped

With this fix:
- All tests complete successfully
- Bulk logic is properly tested (sequentially)
- Parallel mode can be tested separately
- CI/CD pipelines work reliably
