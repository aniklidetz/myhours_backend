# MyHours Backend Testing Guide

## Quick Start

### **IMPORTANT: Docker Environment**

When running with databases in Docker containers, always use the `--docker` flag:

```bash
./run-tests.sh --docker
```

This ensures proper database connectivity and container configuration.

### **Recommended Testing Order:**

1. **Docker Environment Tests** (when databases run in containers)
   ```bash
   ./run-tests.sh --docker
   ```

2. **Local Environment Tests** (when databases run locally)
   ```bash
   ./run-tests.sh --local
   ```

3. **Critical Tests First** (if available)
   ```bash
   python scripts/testing/test_critical_fixes.py
   ```

4. **Local Environment Tests**
   ```bash
   ./scripts/testing/run_local_tests.sh
   ```

5. **Docker Isolated Tests**
   ```bash
   ./scripts/testing/run_docker_tests.sh
   ```

6. **Full Test Suite**
   ```bash
   ./scripts/testing/run_comprehensive_tests.sh
   ```

---

## Test Categories

### **Main Test Runner**
**File:** `run-tests.sh`  
**Purpose:** Primary test execution with multiple options

**Options:**
- `--local` - Run local tests (default) - use when databases run locally
- `--docker` - Run tests in Docker container - REQUIRED when databases run in containers
- `--ci` - Run CI-style tests
- `--verbose` - Verbose output
- `--coverage` - Run with coverage

**Run:** `./run-tests.sh [options]`

### **Critical Vulnerability Tests**
**File:** `scripts/testing/test_critical_fixes.py`  
**Purpose:** Test the most vulnerable areas after technical fixes

**Tests:**
- `salary_info` DoesNotExist behavior
- Enhanced earnings endpoint missing salary handling  
- Celery task retry configuration
- Query optimization with prefetch
- Logging and PII filtering

**Run:** `python scripts/testing/test_critical_fixes.py`

### **Local Environment Tests**
**File:** `scripts/testing/run_local_tests.sh`  
**Purpose:** Comprehensive local testing with existing database

**Phases:**
1. Critical vulnerability validation
2. Regression tests 
3. API endpoint tests
4. Database and performance tests
5. Code quality checks

**Run:** `./scripts/testing/run_local_tests.sh`

### **Docker Isolated Tests**
**File:** `scripts/testing/run_docker_tests.sh`  
**Purpose:** Test in isolated Docker containers

**Features:**
- Fresh PostgreSQL database (port 5433)
- Redis instance (port 6380)
- Clean environment testing
- Automatic container cleanup

**Run:** `./scripts/testing/run_docker_tests.sh`

### **Comprehensive Test Suite**
**File:** `scripts/testing/run_comprehensive_tests.sh`  
**Purpose:** Full system validation across all environments

**Phases:**
1. Environment setup & validation
2. Critical tests (local)
3. Docker isolated tests
4. Full Django test suite  
5. Performance & integration tests

**Run:** `./scripts/testing/run_comprehensive_tests.sh`

---

## Setup Requirements

### **Prerequisites:**
```bash
# Ensure virtual environment is activated
source ./venv/bin/activate

# Required packages should be installed
pip install -r requirements.txt
```

### **Local Database Requirements:**
```bash
# Database should be accessible (when using --local)
export DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_test"
```

### **Docker Requirements:**
```bash
# Docker must be running (when using --docker)
docker info

# Check if database containers are running
docker ps | grep -E "(postgres|redis|mongo)"

# For isolated Docker tests, ports 5433, 6380 should be available
netstat -an | grep ":5433\|:6380"
```

---

## Expected Results

### **Success Indicators:**
- All critical tests pass
- API endpoints return expected responses
- Database operations complete without errors
- Query optimizations working
- Docker containers start and function correctly

### **Warning Signs:**
- Memory usage greater than 200MB during tests
- Database connection failures
- Docker container startup issues
- Test timeouts or hanging

### **Failure Indicators:**
- salary_info DoesNotExist not handled properly
- Enhanced earnings returns 500 instead of 200
- Celery tasks missing retry configuration
- Query optimization not working
- FieldError: Cannot resolve keyword 'salary_info' into field (management commands)

---

## Troubleshooting

### **Common Issues:**

#### **Database Connection Failed**
```bash
# Check PostgreSQL status
brew services list | grep postgresql

# Start PostgreSQL if needed
brew services start postgresql

# Verify connection
psql -h localhost -U myhours_user -d myhours_test -c "SELECT 1;"
```

#### **Docker Tests Fail**
```bash
# Check Docker is running
docker info

# Check if database containers are running
docker ps | grep -E "(postgres|redis|mongo)"

# If containers not running, start them
docker compose up -d

# Clean up any existing test containers
docker stop myhours-test-db myhours-test-redis 2>/dev/null || true
docker rm myhours-test-db myhours-test-redis 2>/dev/null || true

# Run Docker tests again
./run_docker_tests.sh
```

#### **Test Database Already Exists Error**
```bash
# If you get "database test_myhours_test already exists" error:

# Terminate active connections to test database
docker exec myhours_postgres psql -U myhours_user -d postgres -c "
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE datname = 'test_myhours_test' AND pid <> pg_backend_pid();"

# Drop the old test database
docker exec myhours_postgres psql -U myhours_user -d postgres -c "DROP DATABASE IF EXISTS test_myhours_test;"

# Run tests again
./run-tests.sh --docker
```

#### **Virtual Environment Issues**
```bash
# Deactivate and reactivate
deactivate
source ./venv/bin/activate

# Verify Python path
which python
python --version
```

#### **Import Errors**
```bash
# Verify Django setup
export DJANGO_SETTINGS_MODULE=myhours.settings_ci
python -c "import django; django.setup(); print('Django ready')"
```

---

## Performance Benchmarks

### **Expected Performance:**
- Critical tests: less than 10 seconds
- Local tests: less than 60 seconds  
- Docker tests: less than 120 seconds
- Comprehensive tests: less than 300 seconds

### **Memory Usage:**
- Python process: less than 200MB
- PostgreSQL container: less than 100MB
- Redis container: less than 50MB

---

## Log Files

**Test logs are saved to:**
- Local tests: `/tmp/local_tests.log`
- Docker tests: `/tmp/docker_tests.log`
- Critical tests: Console output

**To view logs:**
```bash
tail -f /tmp/local_tests.log
tail -f /tmp/docker_tests.log
```

---

## Production Readiness

### **All Tests Pass:**
- System is production-ready
- All critical fixes validated
- Performance benchmarks met

### **80%+ Tests Pass:** WARNING
- Minor issues detected
- Review failed tests
- Fix before production deployment

### **Less than 80% Tests Pass:**
- Significant issues detected
- Critical fixes required
- Do not deploy to production

---

## Success Checklist

- [ ] Critical vulnerability tests pass
- [ ] Local environment tests pass  
- [ ] Docker isolated tests pass
- [ ] Full Django test suite passes
- [ ] Performance benchmarks met
- [ ] No memory leaks detected
- [ ] API endpoints respond correctly
- [ ] Database operations complete successfully

**When all items checked: System is production-ready**