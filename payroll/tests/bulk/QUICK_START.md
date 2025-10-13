# Bulk Payroll - Quick Start Guide

Quick guide for testing bulk module (5 minutes).

---

## Quick Verification

### 1. Run All Tests (30 seconds)

```bash
# All bulk tests
DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_db" \
./venv/bin/pytest payroll/tests/bulk/ -v --tb=line
```

**Expected result:** All tests PASSED

---

### 2. Performance Benchmark (1 minute)

```bash
# Main benchmark
DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_db" \
./venv/bin/pytest payroll/tests/bulk/test_performance_benchmarks.py::PerformanceBenchmarkTestCase::test_benchmark_sequential_vs_bulk -v -s
```

**Expected result:**
```
Sequential processing: ~4s
Bulk processing:       ~0.6s
Speedup:               6-7x
Throughput:            70-80 employees/sec
```

---

### 3. Load Test (2 minutes)

```bash
# Basic load test
DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_db" \
./venv/bin/python scripts/testing/load_test_bulk_payroll.py --employees 30 --iterations 2
```

**Expected result:**
```
Iteration 1 (cold cache): ~3-5s
Iteration 2 (warm cache): ~0.02s
Success rate: 100%
```

---

## All Performance Benchmarks (5 minutes)

```bash
# All 4 benchmark tests
DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_db" \
./venv/bin/pytest payroll/tests/bulk/test_performance_benchmarks.py -v -s
```

**What is tested:**
1. Sequential vs Bulk (6x speedup)
2. Cache Effectiveness (350x speedup)
3. Database Queries (3 queries regardless of batch size)
4. Memory Efficiency (~400KB per employee)

---

## Main Commands

### Unit Tests
```bash
# All bulk unit tests
DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_db" \
./venv/bin/pytest payroll/tests/bulk/test_*.py -v

# Specific test
DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_db" \
./venv/bin/pytest payroll/tests/bulk/test_bulk_service.py -v
```

### Load Testing
```bash
# Basic test
./venv/bin/python scripts/testing/load_test_bulk_payroll.py --employees 50 --iterations 3

# Mode comparison
./venv/bin/python scripts/testing/load_test_bulk_payroll.py --employees 100 --compare-modes

# Stress test (caution! creates lots of data)
./venv/bin/python scripts/testing/load_test_bulk_payroll.py --stress-test --max-employees 200
```

### Management Command

#### Basic Usage
```bash
# Calculate for all active employees
python manage.py bulk_calculate_payroll --year 2025 --month 10

# Dry run (without saving to DB)
python manage.py bulk_calculate_payroll --year 2025 --month 10 --dry-run

# Specific employees
python manage.py bulk_calculate_payroll --year 2025 --month 10 --employees 1,2,3,4,5

# Without cache
python manage.py bulk_calculate_payroll --year 2025 --month 10 --no-cache

# Sequential mode (for debugging)
python manage.py bulk_calculate_payroll --year 2025 --month 10 --no-parallel
```

#### Cache Testing
```bash
# Step 1: Clear cache and run (cold cache)
python manage.py bulk_calculate_payroll \
  --year 2025 \
  --month 10 \
  --invalidate-cache \
  --dry-run
# Expected output: Cache hit rate: 0.0%

# Step 2: Run again (warm cache)
python manage.py bulk_calculate_payroll \
  --year 2025 \
  --month 10 \
  --dry-run
# Expected output: Cache hit rate: 100.0%
```

**Note:** Both commands take ~12s due to Django startup overhead. To see actual cache speedup (250-435x), use the load test script which keeps Django running between iterations.

### API Testing
```bash
# Health check
curl -X GET http://localhost:8000/api/v1/payroll/bulk/status/ \
  -H "Authorization: Token YOUR_TOKEN"

# Bulk calculation (5 employees)
curl -X POST http://localhost:8000/api/v1/payroll/bulk/calculate/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "year": 2025,
    "month": 10,
    "employee_ids": [1, 2, 3, 4, 5],
    "use_cache": true,
    "use_parallel": false,
    "save_to_db": false
  }'
```

---

## Expected Results

| Metric | Expected Value |
|---------|----------------|
| **Throughput (bulk)** | > 50 employees/sec |
| **Throughput (cached)** | > 500 employees/sec |
| **Cache speedup** | 200-400x |
| **DB queries** | 3-5 (regardless of batch size) |
| **Success rate** | 100% |
| **Memory/employee** | < 500KB |

---

## Troubleshooting

### Problem: Tests hang indefinitely

**Cause:** Multiprocessing + Django tests are incompatible

**Solution:** Always use `use_parallel=False` in tests
```python
service = BulkEnhancedPayrollService(use_parallel=False)
```

**Details:** See `README_TESTING.md`

---

### Problem: Test database already exists

**Solution:**
```bash
# Kill active connections
PGPASSWORD=secure_password_123 psql -U myhours_user -h localhost -d myhours_db \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'test_myhours_test';"

# Drop test database
PGPASSWORD=secure_password_123 psql -U myhours_user -h localhost -d myhours_db \
  -c "DROP DATABASE IF EXISTS test_myhours_test;"
```

---

### Problem: Redis connection errors

**Verification:**
```bash
# Check Redis availability
redis-cli ping

# Check keys
redis-cli keys "payroll:*"
```

**Solution:** Make sure Redis is running:
```bash
# macOS
brew services start redis

# Linux
sudo systemctl start redis
```

---

### Problem: Slow performance

**Diagnostics:**
```bash
# Check SQL query count
DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_db" \
./venv/bin/pytest payroll/tests/bulk/test_performance_benchmarks.py::PerformanceBenchmarkTestCase::test_benchmark_database_queries -v -s
```

**Expected:** 3 queries regardless of batch size

---

## Documentation

- **`TESTING_SUMMARY.md`** - Complete summary of all tests and results
- **`LOAD_TESTING_GUIDE.md`** - Detailed load testing guide
- **`README_TESTING.md`** - Django tests + multiprocessing issues
- **`../services/bulk/README.md`** - Bulk module architecture

---

## Quick Checklist

Before deployment verify:

- [ ] All tests pass (`pytest payroll/tests/bulk/`)
- [ ] Performance benchmarks show > 50 emp/sec
- [ ] Cache works (hit rate > 80%)
- [ ] DB queries optimized (< 5 queries)
- [ ] Load test successful (100% success rate)
- [ ] Management command works
- [ ] API endpoints respond

---

## Next Steps

After verification:

1. **Staging Deployment**
   - Deploy to staging environment
   - Test with real data
   - Measure production-like metrics

2. **Production Monitoring**
   - Configure logging
   - Configure alerting (throughput, error rate)
   - Dashboard for metrics

3. **Gradual Rollout**
   - Start with small batch (10-20 employees)
   - Gradually increase
   - Monitor errors and performance

---

**Questions?** See full documentation in `LOAD_TESTING_GUIDE.md`
