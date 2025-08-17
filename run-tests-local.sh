#!/bin/bash

# Local test runner script for MyHours backend
# Configures proper database URL for local PostgreSQL

set -e

echo "🧪 Running MyHours Tests Locally"
echo "================================="

# Database configuration for local PostgreSQL
export DJANGO_SETTINGS_MODULE=myhours.settings_ci
export DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_test"
export SECRET_KEY="test-secret-key-for-local-development-with-sufficient-length"

echo "📊 Database Configuration:"
echo "  Host: localhost (local PostgreSQL)"
echo "  Database: myhours_test"
echo "  User: myhours_user"

echo ""
echo "🔐 Testing PII Protection System..."

# Test PII protection functionality
./venv/bin/pytest -q --no-cov core/tests/test_logging_filters.py tests/test_safe_logging_simple.py -v

echo ""
echo "🧪 Running Core Security Tests..."

# Test core security features that don't require heavy database setup
./venv/bin/pytest -q --no-cov \
  core/tests/test_exceptions.py \
  core/tests/test_filters.py \
  core/tests/test_serializers.py \
  --tb=line --maxfail=5

echo ""
echo "✅ Local test execution completed successfully!"
echo ""
echo "📝 Note: Some tests may fail due to database permissions or Docker-specific configuration."
echo "   The PII protection system is verified and working correctly."