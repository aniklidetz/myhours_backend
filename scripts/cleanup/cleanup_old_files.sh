#!/bin/bash

# Script to clean up old files and temporary data

echo "🧹 Starting comprehensive cleanup..."

# Run log rotation first
echo "📋 Step 1: Log rotation and cleanup..."
./scripts/cleanup/setup_log_rotation.sh

echo ""
echo "📋 Step 2: General file cleanup..."

# Clean old backup directories (keep last 3)
echo "Cleaning old backup directories..."
# shellcheck disable=SC2012
ls -dt backups/20*/ 2>/dev/null | tail -n +4 | xargs rm -rf 2>/dev/null || true

# Clean old coverage reports (keep last 10)
echo "Cleaning old coverage reports..."
# shellcheck disable=SC2012
ls -dt archive/coverage_reports/htmlcov_*/ 2>/dev/null | tail -n +11 | xargs rm -rf 2>/dev/null || true

# Clean old log archives (keep last 20)
echo "Cleaning old archived logs..."
# shellcheck disable=SC2012
ls -dt logs/archive/*.gz 2>/dev/null | tail -n +21 | xargs rm -f 2>/dev/null || true

# Clean Python cache
echo "Cleaning Python cache files..."
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -type f -delete 2>/dev/null || true

# Clean temporary files
echo "Cleaning temporary files..."
rm -f .coverage* 2>/dev/null || true
rm -rf .pytest_cache/ 2>/dev/null || true
rm -f -- ./*.tmp 2>/dev/null || true

# Clean Django temporary files
echo "Cleaning Django temporary files..."
rm -rf staticfiles/ 2>/dev/null || true

echo ""
echo "📊 Final size summary:"
echo "   Logs: $(du -sh logs/ | cut -f1)"
echo "   Backups: $(du -sh backups/ | cut -f1)"
echo "   Archive: $(du -sh archive/ | cut -f1)"

echo ""
echo "✅ Comprehensive cleanup completed!"