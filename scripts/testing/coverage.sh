#!/bin/bash

# Coverage report generation script

echo "🧪 Running test coverage analysis..."

# Set Django settings
export DJANGO_SETTINGS_MODULE=myhours.settings_ci
export DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_test"
export SECRET_KEY="test-secret-key"

# Run coverage
./venv/bin/pytest --cov=. --cov-report=html --cov-report=xml --cov-report=term-missing --cov-fail-under=60

# Move coverage reports to archive
if [ -d "htmlcov" ]; then
    mv htmlcov/ "archive/coverage_reports/htmlcov_$(date +%Y%m%d_%H%M%S)/"
fi

if [ -f "coverage.xml" ]; then
    mv coverage.xml "archive/coverage_reports/coverage_$(date +%Y%m%d_%H%M%S).xml"
fi

echo "✅ Coverage reports generated and archived"