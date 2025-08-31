#!/bin/bash
# Main test runner script - consolidated from multiple test scripts

set -e

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🧪 MyHours Test Runner${NC}"
echo "=================================="

# Function to run tests with proper settings
run_tests() {
    local test_type=$1
    local settings_module=$2
    local extra_args=$3
    
    echo -e "${YELLOW}Running $test_type tests...${NC}"
    
    if command -v pytest &> /dev/null && [ "$test_type" != "docker" ]; then
        DJANGO_SETTINGS_MODULE=$settings_module pytest $extra_args
    else
        if [ "$test_type" = "docker" ]; then
            docker compose exec web python manage.py test --settings=$settings_module $extra_args
        else
            python3 manage.py test --settings=$settings_module $extra_args
        fi
    fi
}

# Parse command line arguments
TEST_TYPE="local"
VERBOSE=""
COVERAGE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --docker)
            TEST_TYPE="docker"
            shift
            ;;
        --ci)
            TEST_TYPE="ci"
            shift
            ;;
        --local)
            TEST_TYPE="local"
            shift
            ;;
        --verbose|-v)
            VERBOSE="--verbosity=2"
            shift
            ;;
        --coverage)
            COVERAGE="--cov"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --local     Run local tests (default)"
            echo "  --docker    Run tests in Docker container"
            echo "  --ci        Run CI-style tests"
            echo "  --verbose   Verbose output"
            echo "  --coverage  Run with coverage"
            echo "  --help      Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Run tests based on type
case $TEST_TYPE in
    "local")
        echo -e "${GREEN}Running local tests...${NC}"
        run_tests "local" "myhours.test_settings" "$VERBOSE $COVERAGE"
        ;;
    "docker")
        echo -e "${GREEN}Running Docker tests...${NC}"
        run_tests "docker" "myhours.settings_ci" "$VERBOSE --keepdb --failfast"
        ;;
    "ci")
        echo -e "${GREEN}Running CI tests...${NC}"
        run_tests "ci" "myhours.settings_ci" "$VERBOSE --parallel 4 --failfast"
        ;;
esac

echo -e "${GREEN}✅ Tests completed successfully!${NC}"
