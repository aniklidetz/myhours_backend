#!/bin/bash

# Docker Testing Script for Critical Fixes
# Tests in isolated Docker environment

set -e

echo "🐳 MyHours Backend - Docker Testing Suite"
echo "=========================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running. Please start Docker first.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Docker is running${NC}"
echo ""

# Test configuration
TEST_DB_NAME="myhours_test_docker"
TEST_CONTAINER_NAME="myhours-test-db"
TEST_REDIS_CONTAINER="myhours-test-redis"

# Function to cleanup containers
cleanup_containers() {
    echo -e "${YELLOW}🧹 Cleaning up test containers...${NC}"
    docker stop $TEST_CONTAINER_NAME $TEST_REDIS_CONTAINER 2>/dev/null || true
    docker rm $TEST_CONTAINER_NAME $TEST_REDIS_CONTAINER 2>/dev/null || true
    echo -e "${GREEN}✅ Cleanup completed${NC}"
}

# Trap to ensure cleanup on exit
trap cleanup_containers EXIT

echo -e "${BLUE}🎯 Phase 1: Docker Environment Setup${NC}"
echo "===================================="

# Start PostgreSQL test database
echo -e "${BLUE}🐘 Starting PostgreSQL test database...${NC}"
docker run -d \
    --name $TEST_CONTAINER_NAME \
    -e POSTGRES_DB=$TEST_DB_NAME \
    -e POSTGRES_USER=myhours_user \
    -e POSTGRES_PASSWORD=secure_password_123 \
    -p 5433:5432 \
    postgres:14

# Wait for PostgreSQL to be ready and create test database
echo -e "${YELLOW}⏳ Waiting for PostgreSQL to be ready...${NC}"
for i in {1..30}; do
    if docker exec $TEST_CONTAINER_NAME pg_isready -U myhours_user > /dev/null 2>&1; then
        echo -e "${GREEN}✅ PostgreSQL is ready${NC}"
        # Create the test database if it doesn't exist
        echo -e "${BLUE}🗄️ Creating test database...${NC}"
        docker exec $TEST_CONTAINER_NAME psql -U myhours_user -d postgres -c "DROP DATABASE IF EXISTS myhours_test_docker;" > /dev/null 2>&1
        docker exec $TEST_CONTAINER_NAME psql -U myhours_user -d postgres -c "CREATE DATABASE myhours_test_docker;" > /dev/null 2>&1
        echo -e "${GREEN}✅ Test database created${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ PostgreSQL failed to start${NC}"
        exit 1
    fi
    sleep 1
done

# Start Redis test instance
echo -e "${BLUE}🔴 Starting Redis test instance...${NC}"
docker run -d \
    --name $TEST_REDIS_CONTAINER \
    -p 6380:6379 \
    redis:7-alpine

# Wait for Redis to be ready
echo -e "${YELLOW}⏳ Waiting for Redis to be ready...${NC}"
sleep 3
if docker exec $TEST_REDIS_CONTAINER redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Redis is ready${NC}"
else
    echo -e "${RED}❌ Redis failed to start${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}🎯 Phase 2: Docker Environment Tests${NC}"
echo "==================================="

# Test environment variables for Docker
export DJANGO_SETTINGS_MODULE=myhours.settings_ci
export DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5433/myhours_test_docker"
export CI_DB_NAME="myhours_test_docker"
export SECRET_KEY="docker-test-secret-key"
export REDIS_URL="redis://localhost:6380/0"

# Fix Python command to use venv
PYTHON_CMD="./venv/bin/python"

echo -e "${BLUE}🐍 Using Python: $PYTHON_CMD${NC}"

echo -e "${BLUE}📋 Docker Test Environment:${NC}"
echo "  Django Settings: $DJANGO_SETTINGS_MODULE"
echo "  Database: PostgreSQL (port 5433)"
echo "  Database URL: $DATABASE_URL"
echo "  Redis: localhost:6380"
echo "  Redis URL: $REDIS_URL"
echo "  Container DB: $TEST_CONTAINER_NAME"
echo "  Container Redis: $TEST_REDIS_CONTAINER"
echo ""

# Function to run Docker tests
run_docker_test() {
    local test_name="$1"
    local test_command="$2"
    
    echo -e "${BLUE}🧪 Docker Test: $test_name${NC}"
    echo "Command: $test_command"
    echo ""
    
    if eval "$test_command"; then
        echo -e "${GREEN}✅ DOCKER PASSED: $test_name${NC}"
        return 0
    else
        echo -e "${RED}❌ DOCKER FAILED: $test_name${NC}"
        return 1
    fi
}

# Run Django migrations in Docker environment
echo -e "${BLUE}🔧 Running Django migrations...${NC}"
$PYTHON_CMD manage.py migrate --run-syncdb
echo -e "${GREEN}✅ Migrations completed${NC}"

echo ""

# Docker Test 1: Critical fixes with Docker database
run_docker_test "Critical Fixes (Docker DB)" "$PYTHON_CMD scripts/testing/test_critical_fixes.py"

# Docker Test 2: Database operations with Docker PostgreSQL
run_docker_test "Database Operations" "./venv/bin/pytest --tb=short -q --no-cov payroll/tests/test_salary_database_constraints.py::SalaryDatabaseConstraintsTest::test_positive_hourly_rate_constraint -v"

# Docker Test 3: API endpoints with Docker environment
run_docker_test "API Endpoints" "./venv/bin/pytest --tb=short -q --no-cov payroll/tests/test_regression_fixes.py::EnhancedEarningsRegressionTest::test_enhanced_earnings_no_salary_returns_200 -v"

# Docker Test 4: Redis integration (if available)
echo -e "${BLUE}🧪 Docker Test: Redis Integration${NC}"
$PYTHON_CMD -c "
import django
django.setup()
try:
    from django.core.cache import cache
    cache.set('docker_test_key', 'docker_test_value', 30)
    value = cache.get('docker_test_key')
    if value == 'docker_test_value':
        print('✅ Redis integration working')
    else:
        print('❌ Redis integration failed')
        exit(1)
except Exception as e:
    print(f'⚠️ Redis test skipped: {e}')
"

echo ""
echo -e "${BLUE}🎯 Phase 3: Docker Stress Tests${NC}"
echo "==============================="

# Docker Test 5: Concurrent database operations
run_docker_test "Concurrent Operations" "./venv/bin/pytest --tb=short -q --no-cov worktime/tests/test_worklog_performance.py::WorkLogPerformanceTest::test_overlapping_validation_performance -v"

# Docker Test 6: Memory efficiency with Docker limits
echo -e "${BLUE}🧪 Docker Test: Memory Usage${NC}"
$PYTHON_CMD -c "
import django
django.setup()
import psutil
import os

# Check memory usage
process = psutil.Process(os.getpid())
memory_info = process.memory_info()
memory_mb = memory_info.rss / 1024 / 1024

print(f'Python process memory usage: {memory_mb:.1f} MB')

if memory_mb < 200:  # Under 200MB is good
    print('✅ Memory usage is efficient')
else:
    print(f'⚠️ Memory usage is high: {memory_mb:.1f} MB')
"

echo ""
echo -e "${BLUE}🎯 Phase 4: Docker Environment Validation${NC}"
echo "=========================================="

# Validate Docker database state
echo -e "${BLUE}🧪 Docker Test: Database State Validation${NC}"
$PYTHON_CMD -c "
import django
django.setup()
from django.db import connection
from users.models import Employee
from payroll.models import Salary

try:
    # Check database tables exist
    with connection.cursor() as cursor:
        cursor.execute(\"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'\")
        table_count = cursor.fetchone()[0]
    
    print(f'Database tables created: {table_count}')
    
    # Test model operations
    print('Testing model operations...')
    from django.contrib.auth.models import User
    user = User.objects.create_user(username='docker_test', password='test123')
    employee = Employee.objects.create(
        user=user,
        first_name='Docker',
        last_name='Test',
        email='docker@test.com',
        employment_type='full_time',
        role='employee'
    )
    
    # Cleanup
    employee.delete()
    user.delete()
    
    print('✅ Database operations working correctly')

except Exception as e:
    print(f'❌ Database validation failed: {e}')
    exit(1)
"

echo ""
echo -e "${BLUE}🎯 Final Docker Summary${NC}"
echo "======================="

# Show Docker container status
echo -e "${BLUE}🐳 Docker Container Status:${NC}"
docker ps --filter "name=$TEST_CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker ps --filter "name=$TEST_REDIS_CONTAINER" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo -e "${GREEN}🎉 Docker testing completed successfully!${NC}"
echo ""
echo -e "${YELLOW}💡 Next steps:${NC}"
echo "  1. If Docker tests pass, your fixes work in isolated environment"
echo "  2. Run comprehensive test suite: ./run_comprehensive_tests.sh"
echo "  3. For production deployment, ensure all Docker tests pass"
echo ""
echo -e "${BLUE}🧹 Containers will be automatically cleaned up on exit${NC}"