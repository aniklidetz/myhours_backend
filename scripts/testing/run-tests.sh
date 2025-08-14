#!/bin/bash
# Test runner script for MyHours Django application
# Handles PostgreSQL setup and runs tests with proper environment

set -e  # Exit on any error

echo "🧪 MyHours Test Runner"
echo "===================="

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Check if containers are running
if ! docker-compose ps | grep -q "Up"; then
    echo "📦 Starting Docker containers..."
    docker-compose up -d
    echo "⏳ Waiting for containers to be healthy..."
    sleep 10
fi

# Check PostgreSQL health
echo "🔍 Checking PostgreSQL connection..."
if ! docker exec myhours_postgres pg_isready -U myhours_user -d myhours_db >/dev/null 2>&1; then
    echo "❌ PostgreSQL is not ready. Check container status:"
    docker-compose ps
    exit 1
fi

# Check if local PostgreSQL is running and warn user
if lsof -i :5432 | grep -q "postgres" | grep -v "docker"; then
    echo "⚠️  WARNING: Local PostgreSQL may be running on port 5432"
    echo "   This can cause test failures. Consider stopping it with:"
    echo "   brew services stop postgresql@14"
    echo ""
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Set up test environment
export DJANGO_SETTINGS_MODULE=myhours.settings_ci
export DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_test"
export SECRET_KEY="test-secret-key-for-script"

# Create test database if it doesn't exist
echo "🗄️  Ensuring test database exists..."
docker exec myhours_postgres psql -U myhours_user -d myhours_db -c "CREATE DATABASE myhours_test OWNER myhours_user;" 2>/dev/null || echo "Database myhours_test already exists"

# Verify connection
echo "✅ Testing database connection..."
if ! PGPASSWORD=secure_password_123 psql -h localhost -p 5432 -U myhours_user -d myhours_test -c "SELECT 1;" >/dev/null 2>&1; then
    echo "❌ Cannot connect to test database. Check configuration."
    exit 1
fi

echo "✅ Database connection successful!"
echo ""

# Run tests based on arguments
if [ $# -eq 0 ]; then
    echo "🚀 Running ALL tests..."
    ./venv/bin/pytest -q --no-cov -v
else
    echo "🚀 Running specific test: $*"
    ./venv/bin/pytest -q --no-cov "$@" -v
fi

echo ""
echo "🎉 Test run completed!"