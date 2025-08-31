#!/bin/bash

# Local Testing Script for Critical Fixes
# Run this to validate all fixes locally

set -e  # Exit on any error

echo "🔍 MyHours Backend - Local Testing Suite"
echo "========================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test configuration
export DJANGO_SETTINGS_MODULE=myhours.settings_ci
export DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_test"
export SECRET_KEY="test-secret-key"

echo -e "${BLUE}📋 Test Environment:${NC}"
echo "  Django Settings: $DJANGO_SETTINGS_MODULE"
echo "  Database: PostgreSQL (myhours_test)"
echo "  Python: $(python --version 2>&1)"
echo ""

# Function to run test with error handling
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    echo -e "${BLUE}🧪 Running: $test_name${NC}"
    echo "Command: $test_command"
    echo ""
    
    if eval "$test_command"; then
        echo -e "${GREEN}✅ PASSED: $test_name${NC}"
        return 0
    else
        echo -e "${RED}❌ FAILED: $test_name${NC}"
        return 1
    fi
}

# Ensure virtual environment is activated
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo -e "${YELLOW}⚠️  Virtual environment not detected. Attempting to activate...${NC}"
    if [ -f "./venv/bin/activate" ]; then
        source ./venv/bin/activate
        echo -e "${GREEN}✅ Virtual environment activated${NC}"
    else
        echo -e "${RED}❌ Virtual environment not found. Please activate manually.${NC}"
        exit 1
    fi
fi

echo -e "${BLUE}🎯 Phase 1: Critical Vulnerability Tests${NC}"
echo "=========================================="

# Test 1: Critical fixes validation
run_test "Critical Fixes Validation" "python scripts/testing/test_critical_fixes.py"

echo ""
echo -e "${BLUE}🎯 Phase 2: Regression Tests${NC}"
echo "============================="

# Test 2: Regression tests
run_test "Salary Regression Tests" "./venv/bin/pytest --tb=short -q --no-cov payroll/tests/test_regression_fixes.py -v"

# Test 3: User model tests
run_test "User Model Tests" "./venv/bin/pytest --tb=short -q --no-cov users/tests/test_models_targeted.py::EmployeeModelTest::test_send_notification_method -v"

# Test 4: Exception handling
run_test "Exception Handling Tests" "./venv/bin/pytest --tb=short -q --no-cov core/tests/test_exceptions.py -v"

echo ""
echo -e "${BLUE}🎯 Phase 3: API Endpoint Tests${NC}"
echo "==============================="

# Test 5: Enhanced earnings endpoint
run_test "Enhanced Earnings API" "./venv/bin/pytest --tb=short -q --no-cov payroll/tests/test_regression_fixes.py::EnhancedEarningsRegressionTest -v"

# Test 6: Payroll API basic functionality
run_test "Payroll Views Basic" "./venv/bin/pytest --tb=short -q --no-cov payroll/tests/test_payroll_views_basic.py::PayrollAnalyticsBasicTest::test_analytics_admin_access -v"

echo ""
echo -e "${BLUE}🎯 Phase 4: Database and Performance Tests${NC}"
echo "==========================================="

# Test 7: Database constraints
run_test "Salary Database Constraints" "./venv/bin/pytest --tb=short -q --no-cov payroll/tests/test_salary_database_constraints.py::SalaryDatabaseConstraintsTest::test_positive_hourly_rate_constraint -v"

# Test 8: Query performance
run_test "WorkLog Performance Tests" "./venv/bin/pytest --tb=short -q --no-cov worktime/tests/test_worklog_performance.py::WorkLogPerformanceTest::test_overlapping_validation_performance -v"

echo ""
echo -e "${BLUE}🎯 Phase 5: Code Quality Checks${NC}"
echo "================================"

# Test 9: Code style (basic check - warnings only)
echo -e "${BLUE}🧪 Running: Python Code Style Check${NC}"
if ./venv/bin/flake8 --version > /dev/null 2>&1; then
    # Run flake8 but don't fail the script on warnings
    ./venv/bin/flake8 payroll/views.py users/models.py core/tasks.py --select=F401,F841 --show-source || true
    echo -e "${GREEN}✅ PASSED: Code Style Check (warnings are informational only)${NC}"
else
    echo -e "${YELLOW}⚠️  flake8 not available, skipping code style check${NC}"
fi

# Test 10: Import checks
echo -e "${BLUE}🧪 Running: Import Validation${NC}"
python -c "
import django
django.setup()
try:
    from payroll.models import Salary
    from users.models import Employee  
    from core.tasks import send_critical_alert, cleanup_old_logs
    print('✅ All critical imports successful')
except ImportError as e:
    print(f'❌ Import error: {e}')
    exit(1)
"

echo ""
echo -e "${BLUE}🎯 Final Summary${NC}"
echo "================="

# Database check
echo -e "${BLUE}🧪 Running: Database Connection Test${NC}"
python -c "
import django
django.setup()
from django.db import connection
try:
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
    print('✅ Database connection successful')
except Exception as e:
    print(f'❌ Database connection failed: {e}')
    exit(1)
"

echo ""
echo -e "${GREEN}🎉 Local testing completed!${NC}"
echo -e "${YELLOW}💡 Next steps:${NC}"
echo "  1. If all tests pass, run Docker tests: ./run_docker_tests.sh"
echo "  2. If tests fail, check the specific error messages above"
echo "  3. For production deployment, run full test suite"
echo ""