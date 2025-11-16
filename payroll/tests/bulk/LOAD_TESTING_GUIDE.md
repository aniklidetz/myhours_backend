# Bulk Payroll Load Testing Guide

Complete guide for performance and load testing of the bulk module.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Performance Benchmarking](#performance-benchmarking)
3. [Load Testing](#load-testing)
4. [Production Testing](#production-testing)
5. [Monitoring & Metrics](#monitoring--metrics)
6. [Troubleshooting](#troubleshooting)

---

## Quick Start

### 1. Run All Tests

```bash
# All bulk tests (including unit tests)
DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_db" \
./venv/bin/pytest payroll/tests/bulk/ -v

# Performance benchmarks only
DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_db" \
./venv/bin/pytest payroll/tests/bulk/test_performance_benchmarks.py -v -s
```

### 2. Quick Performance Check

```bash
# Create test data and measure time
python scripts/testing/load_test_bulk_payroll.py --employees 50 --iterations 3
```

### 3. API Check

```bash
# Get service status
curl -X GET http://localhost:8000/api/v1/payroll/bulk/status/ \
   -H "Authorization: Token YOUR_TOKEN" 
   #the command above with Token prefix:     -H "Authorization: Token aa899f41ce8*****************44eae7f3b"

# Run bulk calculation
curl -X POST http://localhost:8000/api/v1/payroll/bulk/calculate/ \
  -H "Authorization: Token YOUR_TOKEN" \ 
     #the command above with Token prefix:     -H "Authorization: Token aa899f41ce8*****************44eae7f3b"
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

## Performance Benchmarking

### Unit Tests with Performance Measurement

Use specialized test suite for benchmarking:

```bash
# Run all benchmarks
DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_db" \
./venv/bin/pytest payroll/tests/bulk/test_performance_benchmarks.py -v -s

# Specific benchmark
DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_db" \
./venv/bin/pytest payroll/tests/bulk/test_performance_benchmarks.py::PerformanceBenchmarkTestCase::test_benchmark_sequential_vs_bulk -v -s
```

### What is Tested

#### 1. Sequential vs Bulk Processing
Compares sequential processing with bulk processing:

```
Testing with 50 employees
==============================================================
Sequential processing: 8.45s
Bulk processing:       2.31s
Speedup:               3.66x
Throughput (seq):      5.9 employees/sec
Throughput (bulk):     21.6 employees/sec
==============================================================
```

**Expected Results:**
- Bulk should be faster for batches > 10 employees
- Speedup: 2-5x for batches of 50-100 employees
- Throughput: 15-30 employees/sec on local machine

#### 2. Cache Effectiveness
Tests caching efficiency:

```
==============================================================
CACHE BENCHMARK RESULTS
==============================================================
Cold cache (calculated): 2.340s
Warm cache (from cache): 0.123s
Cache speedup:           19.02x
Cache hit rate:          100.0%
Cached results:          20/20
==============================================================
```

**Expected Results:**
- Cache speedup: 10-20x
- Cache hit rate: 100% on repeated requests
- Warm cache: < 0.2s for 20 employees

#### 3. Database Query Efficiency
Tests SQL query count:

```
==============================================================
DATABASE QUERY BENCHMARK
==============================================================
Batch size:   5 | Queries:   8 | Per employee: 1.60
Batch size:  10 | Queries:   8 | Per employee: 0.80
Batch size:  20 | Queries:   9 | Per employee: 0.45
Batch size:  50 | Queries:  10 | Per employee: 0.20
==============================================================
```

**Expected Results:**
- Total queries: 3-10 regardless of batch size
- Queries per employee: should decrease with batch size
- For 100+ employees: < 0.1 queries per employee

#### 4. Memory Efficiency
Tests memory usage:

```
==============================================================
MEMORY BENCHMARK RESULTS
==============================================================
Employees processed: 50
Current memory:      12.45 MB
Peak memory:         18.23 MB
Memory per employee: 373.22 KB
==============================================================
```

**Expected Results:**
- Peak memory: < 100MB for 50 employees
- Memory per employee: 200-500 KB
- Linear memory growth (not quadratic)

---

## Load Testing

### Standalone Load Testing Script

Specialized script for realistic load testing.

#### Basic Test

```bash
# 50 employees, 3 iterations
python scripts/testing/load_test_bulk_payroll.py \
  --employees 50 \
  --iterations 3
```

**What Happens:**
1. Creates 50 test employees with salary and work logs
2. Performs bulk calculation 3 times
3. Outputs statistics for each iteration
4. Test data is cleaned up

**Expected Output:**
```
==============================================================
LOAD TEST
==============================================================
Employees:     50
Period:        2025-10
Cache:         Enabled
Parallel:      Disabled
Iterations:    3
==============================================================

--- Iteration 1/3 (Cold cache) ---
Duration:     8-10s
Throughput:   5-6 employees/sec
Success rate: 50/50
Cache hits:   0/50 (0.0%)
Note: Slower due to push notifications and initial data processing

--- Iteration 2/3 (Warm cache) ---
Duration:     0.03-0.05s
Throughput:   1000-1600 employees/sec
Success rate: 50/50
Cache hits:   50/50 (50.0%)

--- Iteration 3/3 (Hot cache) ---
Duration:     0.02-0.03s
Throughput:   1600-2100 employees/sec
Success rate: 50/50
Cache hits:   50/50 (66.7%)

==============================================================
SUMMARY
==============================================================
Average duration:  2.7-3.5s
Min duration:      0.02s
Max duration:      10s
Average throughput: 800-1200 employees/sec (with cache)
==============================================================

Note: First iteration is slower due to:
- Push notification processing
- Database writes for WorkLog creation
- Initial data processing
Subsequent iterations benefit from Redis cache (350-400x speedup)
```

#### Mode Comparison

```bash
# Compare sequential with/without cache
python scripts/testing/load_test_bulk_payroll.py \
  --employees 100 \
  --compare-modes
```

**What is Tested:**
1. Sequential without cache (baseline)
2. Sequential with cache (cold) - calculates and stores in cache
3. Sequential with cache (warm) - retrieves from cache

**Expected Result (100 employees):**
```
==============================================================
COMPARISON RESULTS
==============================================================
sequential_no_cache          :  10.0s  (  10 emp/sec)    ← Baseline
sequential_cold_cache        :   1.3s  (  77 emp/sec)    ← 8x faster
sequential_warm_cache        :   0.04s (2300 emp/sec)    ← 250x faster!
==============================================================

Cache effectiveness: 31-32x speedup (cold → warm)
Overall improvement: 250x speedup (no cache → warm cache)
Cache hit rate: 100%
```

**Key Insights:**
- **Bulk processing** (cold cache) provides 8x speedup vs sequential
- **Warm cache** provides additional 32x speedup vs cold cache
- **Combined effect**: 250x speedup with optimized queries + cache
- Perfect cache hit rate (100%) demonstrates reliable caching

#### Stress Test

```bash
# Test with increasing load
python scripts/testing/load_test_bulk_payroll.py \
  --stress-test \
  --max-employees 200

# With result saving
python scripts/testing/load_test_bulk_payroll.py \
  --stress-test \
  --max-employees 300 \
  --output /tmp/stress_test_results.json
```

**What Happens:**
- Testing in steps of 50: 50, 100, 150, 200 employees
- For each batch size: create data → calculate → delete
- Measures duration and throughput

**Expected Result:**
```
==============================================================
STRESS TEST SUMMARY
==============================================================
   Employees |  Duration (s) | Throughput (emp/s)
----------------------------------------------------------------------
          50 |          2.45 |                 20.4
         100 |          4.82 |                 20.7
         150 |          7.15 |                 21.0
         200 |          9.67 |                 20.7
==============================================================
```

**Success Criteria:**
- Throughput remains stable (± 20%)
- Linear duration growth with employee count
- No OutOfMemory or Database timeout errors

---

## Production Testing

### Management Command Testing

Safest way to test parallel mode in production-like conditions.

#### 1. Testing on Real Data

```bash
# Calculate for all active employees
python manage.py bulk_calculate_payroll \
  --year 2025 \
  --month 10 \
  --strategy enhanced

# Only for specific employees
python manage.py bulk_calculate_payroll \
  --year 2025 \
  --month 10 \
  --employees 1,2,3,4,5

# Without saving to DB (dry run)
python manage.py bulk_calculate_payroll \
  --year 2025 \
  --month 10 \
  --dry-run
```

#### 2. Performance Comparison

```bash
# Sequential mode (baseline)
time python manage.py bulk_calculate_payroll \
  --year 2025 \
  --month 10 \
  --no-parallel \
  --no-cache

# With cache
time python manage.py bulk_calculate_payroll \
  --year 2025 \
  --month 10 \
  --no-parallel

# With parallel (if safe)
time python manage.py bulk_calculate_payroll \
  --year 2025 \
  --month 10
```

#### 3. Cache Testing

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

# Step 3: Invalidate cache (optional cleanup)
python manage.py bulk_calculate_payroll \
  --year 2025 \
  --month 10 \
  --invalidate-cache
```

**Note:** Both Step 1 and Step 2 take ~12s due to Django startup overhead. To see actual cache speedup (250-435x), use the load test script which keeps Django running between iterations.

#### 4. Docker Environment Testing

If running in Docker (via `make up` or `docker-compose up`), use these commands to test cache:

```bash
# Check Redis keys in container
docker exec myhours_redis redis-cli -a redis_password_123 keys "monthly_summary:*"

# Expected output:
# monthly_summary:1:2025:10
# monthly_summary:2:2025:10
# monthly_summary:85:2025:10

# Run calculation inside container (cold cache)
docker exec myhours_web python manage.py bulk_calculate_payroll \
  --year 2025 \
  --month 10 \
  --invalidate-cache \
  --dry-run

# Expected output: Cache hit rate: 0.0%

# Run again (warm cache)
docker exec myhours_web python manage.py bulk_calculate_payroll \
  --year 2025 \
  --month 10 \
  --dry-run

# Expected output: Cache hit rate: 100.0%

# Monitor Redis activity in container
docker exec myhours_redis redis-cli -a redis_password_123 monitor

# Check application logs for cache activity
docker logs myhours_web 2>&1 | grep "Bulk cache"

# Expected logs:
# INFO 🔗 Connecting to Redis via URL: redis://:redis_password_123@...
# INFO ✅ BulkCacheManager initialized successfully
# INFO Bulk cache get: 3/3 hits
```

**Docker-specific Notes:**

- Redis runs in a separate container (`myhours_redis`) on Docker network
- Application connects to Redis via service name (`redis`), not `localhost`
- Host machine `redis-cli` connects to different Redis than Docker containers
- Always use `docker exec` commands to check container Redis
- Cache manager uses `REDIS_URL` environment variable from docker-compose.yml

**Troubleshooting Docker Cache:**

If cache hit rate shows 0% in Docker:

1. **Check Redis connection in logs:**
```bash
docker logs myhours_web 2>&1 | grep -i "redis\|cache"
```

Expected: `🔗 Connecting to Redis via URL: redis://:redis_password_123@...`

2. **Verify Redis is running:**
```bash
docker ps | grep redis
docker exec myhours_redis redis-cli -a redis_password_123 ping
```

Expected: `PONG`

3. **Check environment variables:**
```bash
docker exec myhours_web env | grep REDIS
```

Expected: `REDIS_URL=redis://:redis_password_123@redis:6379/0`

4. **Restart containers to apply code changes:**
```bash
make restart
# or
docker-compose restart web
```

### API Testing in Production

#### 1. Health Check

```bash
# Check bulk API availability (localhost)
curl -X GET http://localhost:8000/api/v1/payroll/bulk/status/ \
  -H "Authorization: Token $TOKEN"

# For production
curl -X GET https://your-domain.com/api/v1/payroll/bulk/status/ \
  -H "Authorization: Token $TOKEN"
```

**Expected Response:**
```json
{
  "service_available": true,
  "configuration": {
    "enable_fallback": true,
    "enable_caching": true
  },
  "recommendations": {
    "min_batch_size": 10,
    "optimal_batch_size": 100,
    "max_batch_size": 1000,
    "note": "For batches < 10 employees, sequential calculation may be faster"
  }
}
```

**Note:** Install `jq` for formatted output: `brew install jq`, then add `| jq .` to commands. Or use Python: `| python -m json.tool`

#### 2. Small Batch Test

```bash
# Test with small batch (5 employees) - localhost
curl -X POST http://localhost:8000/api/v1/payroll/bulk/calculate/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "year": 2025,
    "month": 10,
    "employee_ids": [1, 2, 3, 4, 5],
    "save_to_db": false
  }'

# For production
curl -X POST https://your-domain.com/api/v1/payroll/bulk/calculate/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "year": 2025,
    "month": 10,
    "employee_ids": [1, 2, 3, 4, 5],
    "save_to_db": false
  }'
```

**Verify:**
- Status code: 200
- Response time: < 2 seconds
- `summary.successful` = 5

#### 3. Medium Batch Test

```bash
# Test with medium batch (50 employees)
# Option 1: Without jq (simpler)
curl -X POST http://localhost:8000/api/v1/payroll/bulk/calculate/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "year": 2025,
    "month": 10,
    "employee_ids": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "use_cache": true,
    "save_to_db": false
  }'

# Option 2: With jq (requires `brew install jq`)
EMPLOYEE_IDS=$(curl -X GET http://localhost:8000/api/users/employees/ \
  -H "Authorization: Token $TOKEN" \
  | jq -r '[.results[0:50] | .[].id] | join(",")')

curl -X POST http://localhost:8000/api/v1/payroll/bulk/calculate/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"year\": 2025,
    \"month\": 10,
    \"employee_ids\": [$EMPLOYEE_IDS],
    \"use_cache\": true,
    \"save_to_db\": false
  }" | jq '.summary'
```

#### 4. Monitoring During Tests

**For bare metal / local development:**

```bash
# In separate terminal monitor logs
tail -f logs/django.log | grep -i "bulk\|payroll"

# Monitor Redis
redis-cli monitor | grep "payroll"

# Monitor PostgreSQL
psql -U myhours_user -h localhost -d myhours_db -c "
  SELECT query, state, wait_event_type, query_start
  FROM pg_stat_activity
  WHERE query LIKE '%payroll%'
  ORDER BY query_start DESC
  LIMIT 5;
"
```

**For Docker environment:**

```bash
# Monitor application logs (real-time)
docker logs -f myhours_web

# Filter for bulk/payroll activity
docker logs -f myhours_web 2>&1 | grep -i "bulk\|payroll"

# Monitor Redis activity
docker exec myhours_redis redis-cli -a redis_password_123 monitor

# Filter Redis for payroll keys
docker exec myhours_redis redis-cli -a redis_password_123 monitor | grep "monthly_summary"

# Monitor PostgreSQL
docker exec myhours_postgres psql -U myhours_user -d myhours_db -c "
  SELECT query, state, wait_event_type, query_start
  FROM pg_stat_activity
  WHERE query LIKE '%payroll%'
  ORDER BY query_start DESC
  LIMIT 5;
"

# Check container resource usage
docker stats myhours_web myhours_redis myhours_postgres
```

---

## Monitoring & Metrics

### Key Metrics to Track

#### 1. Performance Metrics

**Throughput:**
- **Definition**: Employees processed per second
- **Target**: > 15 employees/sec (sequential), > 30 employees/sec (parallel)
- **Measurement**: `employee_count / duration_seconds`

**Latency:**
- **Definition**: Processing time per employee
- **Target**: < 100ms per employee (sequential)
- **Measurement**: `duration_seconds / employee_count`

**Cache Hit Rate:**
- **Definition**: Percentage of results from cache
- **Target**: > 80% for repeated requests
- **Measurement**: `cached_count / total_count * 100`

#### 2. Resource Metrics

**Database Queries:**
- **Target**: < 10 queries regardless of batch size
- **Check**: `result.db_queries_count`

**Memory Usage:**
- **Target**: < 100MB for 100 employees
- **Check**: Process memory monitoring

**Redis Usage:**
- **Target**: < 10MB per 100 employees
- **Check**: `redis-cli info memory`

#### 3. Reliability Metrics

**Success Rate:**
- **Definition**: Percentage of successful calculations
- **Target**: > 99%
- **Measurement**: `successful_count / total_count * 100`

**Error Rate:**
- **Definition**: Percentage of failed calculations
- **Target**: < 1%
- **Measurement**: `failed_count / total_count * 100`

### Logging

All bulk operations are logged with detailed information:

```python
# Enable detailed logging
import logging
logging.getLogger('payroll.services.bulk').setLevel(logging.DEBUG)
```

**Key Events:**
- `bulk_service_init` - service initialization
- `bulk_calculation_start` - calculation start
- `data_loaded` - data loaded
- `cache_loaded` - results from cache
- `bulk_calculation_complete` - calculation complete
- `bulk_calculation_error` - calculation error

**Example Log:**
```json
{
  "timestamp": "2025-10-11T10:30:45.123Z",
  "level": "INFO",
  "action": "bulk_calculation_complete",
  "employee_count": 100,
  "successful": 98,
  "failed": 2,
  "duration_seconds": 4.56,
  "cache_hit_rate": 0.0,
  "throughput": 21.9
}
```

### Grafana Dashboard (Recommended)

If using Grafana, create a dashboard with panels:

**Panel 1: Throughput Over Time**
```
Query: rate(bulk_payroll_calculations_total[5m])
```

**Panel 2: Success Rate**
```
Query: (bulk_payroll_successful / bulk_payroll_total) * 100
```

**Panel 3: Cache Hit Rate**
```
Query: (bulk_payroll_cache_hits / bulk_payroll_requests) * 100
```

**Panel 4: Duration Percentiles**
```
Query: histogram_quantile(0.95, bulk_payroll_duration_bucket)
```

---

## Troubleshooting

### Problem: Slow Performance

**Symptoms:**
- Throughput < 10 employees/sec
- Duration > 10 seconds for 50 employees

**Diagnostics:**

1. **Check SQL query count:**
```python
from django.test.utils import override_settings
from django.db import connection
from django.test.utils import CaptureQueriesContext

with CaptureQueriesContext(connection) as ctx:
    service.calculate_bulk(employee_ids, 2025, 10)
    print(f"Queries: {len(ctx.captured_queries)}")
```

2. **Check slow queries:**
```sql
-- PostgreSQL
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
WHERE query LIKE '%payroll%'
ORDER BY mean_exec_time DESC
LIMIT 10;
```

3. **Check indexes:**
```sql
-- Missing indexes
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE tablename IN ('worktime_worklog', 'payroll_salary', 'users_employee')
ORDER BY tablename, indexname;
```

**Solutions:**
- Add select_related/prefetch_related in data_loader.py
- Create indexes on frequently used fields
- Increase batch_size for bulk operations

### Problem: High Memory Usage

**Symptoms:**
- OutOfMemory errors
- Peak memory > 500MB for 100 employees

**Diagnostics:**
```python
import tracemalloc

tracemalloc.start()
service.calculate_bulk(employee_ids, 2025, 10)
current, peak = tracemalloc.get_traced_memory()
print(f"Peak: {peak / 1024 / 1024:.2f} MB")
tracemalloc.stop()
```

**Solutions:**
- Decrease batch_size
- Use iterator() for large QuerySets
- Clear cache between batches

### Problem: Cache Not Working

**Symptoms:**
- Cache hit rate = 0%
- Warm cache not faster than cold cache

**Diagnostics:**

**For bare metal / local development:**
```bash
# Check Redis availability
redis-cli ping

# Check keys
redis-cli keys "monthly_summary:*"

# Check TTL
redis-cli ttl "monthly_summary:1:2025:10"

# Check Redis info
redis-cli info | grep -E "connected_clients|used_memory_human"
```

**For Docker environment:**
```bash
# Check Redis availability in container
docker exec myhours_redis redis-cli -a redis_password_123 ping

# Check keys in container Redis
docker exec myhours_redis redis-cli -a redis_password_123 keys "monthly_summary:*"

# Check TTL in container
docker exec myhours_redis redis-cli -a redis_password_123 ttl "monthly_summary:1:2025:10"

# Check application logs for Redis connection
docker logs myhours_web 2>&1 | grep -i "redis"

# Expected: "🔗 Connecting to Redis via URL: redis://:redis_password_123@..."
# NOT: "Error 111 connecting to localhost:6379"

# Check REDIS_URL environment variable
docker exec myhours_web env | grep REDIS_URL

# Expected: REDIS_URL=redis://:redis_password_123@redis:6379/0
```

**Solutions:**
- **Docker**: Check `REDIS_URL` environment variable in docker-compose.yml
- **Bare metal**: Check `REDIS_CONFIG` in Django settings
- Verify cache_manager uses `redis.from_url()` for Docker compatibility
- Increase `CACHE_TTL` if keys expire too quickly
- Restart containers after code changes: `make restart`
- Check cache_manager initialization logs

### Problem: Tests Hang Indefinitely

**See README_TESTING.md** - this is a known issue with ProcessPoolExecutor in Django tests.

**Quick Solution:**
```python
# Always use use_parallel=False in tests
service = BulkEnhancedPayrollService(use_parallel=False)
```

---

## Checklist: Production Readiness

Before production deployment check:

- [ ] All unit tests pass (596/596)
- [ ] Performance benchmarks show expected results
- [ ] Load testing with real batch sizes successful
- [ ] Cache works correctly (hit rate > 80%)
- [ ] Database queries optimized (< 10 queries)
- [ ] Memory usage acceptable (< 100MB per 100 employees)
- [ ] Logging configured and working
- [ ] Monitoring/metrics collected
- [ ] Error handling tested
- [ ] Rollback plan prepared
- [ ] Documentation updated

---

## Useful Commands (Quick Reference)

### Bare Metal / Local Development

```bash
# === TESTING ===

# All bulk tests
./venv/bin/pytest payroll/tests/bulk/ -v

# Performance benchmarks
./venv/bin/pytest payroll/tests/bulk/test_performance_benchmarks.py -v -s

# Load test (50 employees, 3 iterations)
python scripts/testing/load_test_bulk_payroll.py --employees 50 --iterations 3

# Stress test
python scripts/testing/load_test_bulk_payroll.py --stress-test --max-employees 200

# === PRODUCTION ===

# Management command
python manage.py bulk_calculate_payroll --year 2025 --month 10

# API status
curl -X GET http://localhost:8000/api/v1/payroll/bulk/status/ \
  -H "Authorization: Token $TOKEN"

# === DEBUGGING ===

# SQL query log
export DEBUG_SQL=1
python manage.py bulk_calculate_payroll --year 2025 --month 10 --dry-run

# Redis monitoring
redis-cli monitor | grep payroll

# PostgreSQL monitoring
psql -U myhours_user -h localhost -d myhours_db \
  -c "SELECT * FROM pg_stat_activity WHERE query LIKE '%payroll%'"
```

### Docker Environment

```bash
# === TESTING ===

# Run calculation in container
docker exec myhours_web python manage.py bulk_calculate_payroll \
  --year 2025 --month 10 --dry-run

# Test cache (cold)
docker exec myhours_web python manage.py bulk_calculate_payroll \
  --year 2025 --month 10 --invalidate-cache --dry-run

# Test cache (warm)
docker exec myhours_web python manage.py bulk_calculate_payroll \
  --year 2025 --month 10 --dry-run

# === CACHE VERIFICATION ===

# Check Redis keys
docker exec myhours_redis redis-cli -a redis_password_123 keys "monthly_summary:*"

# Verify Redis connection
docker exec myhours_redis redis-cli -a redis_password_123 ping

# Check cache in logs
docker logs myhours_web 2>&1 | grep "Bulk cache"

# === MONITORING ===

# Monitor application logs (real-time)
docker logs -f myhours_web

# Monitor Redis activity
docker exec myhours_redis redis-cli -a redis_password_123 monitor

# Monitor PostgreSQL
docker exec myhours_postgres psql -U myhours_user -d myhours_db \
  -c "SELECT * FROM pg_stat_activity WHERE query LIKE '%payroll%'"

# Container resource usage
docker stats myhours_web myhours_redis myhours_postgres

# === TROUBLESHOOTING ===

# Check Redis connection in logs
docker logs myhours_web 2>&1 | grep -i "redis\|cache"

# Check environment variables
docker exec myhours_web env | grep REDIS

# Restart containers
make restart
```

---

## Additional Resources

- **README_TESTING.md** - Explanation of multiprocessing issues in Django tests
- **payroll/services/bulk/README.md** - Bulk module architecture
- **Django Query Optimization** - https://docs.djangoproject.com/en/stable/topics/db/optimization/
- **Redis Best Practices** - https://redis.io/docs/manual/patterns/

---

**Questions?** Create an issue in the repository or contact the development team.
