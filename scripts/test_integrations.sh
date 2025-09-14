#!/bin/bash
# Script to run all integration tests with correct database configuration

export DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_db"

echo " Running integration tests with local database..."
echo "Database: $DATABASE_URL"
echo

# Check if Docker containers are running
if ! docker ps | grep -q myhours_postgres; then
    echo " PostgreSQL container not running. Please start Docker containers first:"
    echo "   docker-compose up -d"
    exit 1
fi

# Run the specified test or all integration tests if no argument provided
if [ $# -eq 0 ]; then
    echo "Running all integration tests (excluding slow tests)..."
    echo "To include slow tests, use: python -m pytest integrations/tests/ -v --no-cov"
    python -m pytest integrations/tests/ -v --no-cov -m "not slow"
else
    echo "Running specific test: $1"
    python -m pytest "integrations/tests/$1" -v --no-cov
fi