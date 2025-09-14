#!/bin/bash
# Convenience script to run Shabbat service tests with correct database configuration
# This script sets the correct DATABASE_URL for local testing with Docker PostgreSQL

export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/myhours_db"

echo " Running Shabbat service tests with local database..."
echo "Database: $DATABASE_URL"
echo

# Run the specified test or all Shabbat tests if no argument provided
if [ $# -eq 0 ]; then
    echo "Running all UnifiedShabbatService tests..."
    python -m pytest integrations/tests/test_unified_shabbat_service.py -v --no-cov
else
    echo "Running specific test: $1"
    python -m pytest "integrations/tests/test_unified_shabbat_service.py::$1" -v --no-cov
fi