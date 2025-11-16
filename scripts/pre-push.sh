#!/usr/bin/env bash
set -Eeuo pipefail

# Pre-push hook for quality assurance
# 
# Usage:
#   git push                    -> full run with coverage (default)
#   FULL=0 git push            -> quick run without coverage 
#   SKIP_PRE_PUSH=1 git push   -> skip hook entirely
#   COV=60 git push            -> custom coverage threshold
#
# Environment variables:
#   FULL=1       -> full run with coverage and threshold (default)
#   COV=50       -> coverage threshold (should match CI)
#   SKIP_PRE_PUSH=1 -> completely skip hook (for WIP branches)

cd "$(git rev-parse --show-toplevel)"

# Load local test environment variables if available
if [[ -f ".env.test" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env.test
  set +a
fi

# Set default environment variables
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-myhours.settings_ci}"
export DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@127.0.0.1:5432/myhours_test}"

# Check if pre-push should be skipped
if [[ "${SKIP_PRE_PUSH:-0}" == "1" ]]; then
  echo "[pre-push] SKIP_PRE_PUSH=1 -> checks skipped."
  exit 0
fi

echo "[pre-push] Running pre-push quality checks..."

# Detect Python runner (prefer poetry if available)
RUN=""
if command -v poetry >/dev/null 2>&1 && [[ -f "pyproject.toml" ]]; then
  RUN="poetry run "
  echo "[pre-push] Using Poetry for Python execution"
elif [[ -f "venv/bin/python" ]]; then
  RUN="./venv/bin/"
  echo "[pre-push] Using local venv for Python execution"
else
  echo "[pre-push] Using system Python"
fi

# Check database connectivity and authentication
if command -v pg_isready >/dev/null 2>&1; then
  if ! pg_isready -d "$DATABASE_URL" >/dev/null 2>&1; then
    echo "[pre-push]  PostgreSQL server not available at $DATABASE_URL"
    echo "           Start your database or check DATABASE_URL in .env.test"
    exit 1
  fi
  
  # Test authentication by connecting to postgres database (which always exists)
  # We don't test the target database since pytest --create-db will create it
  postgres_url=$(echo "$DATABASE_URL" | sed 's|/[^/]*$|/postgres|')
  if ! echo "SELECT 1;" | psql "$postgres_url" >/dev/null 2>&1; then
    echo "[pre-push]  PostgreSQL authentication failed for $postgres_url"
    echo "           Check your database credentials in .env.test"
    echo "           Current DATABASE_URL: $DATABASE_URL"
    echo ""
    echo "           Common fixes:"
    echo "           - Use your macOS username: postgresql://$(whoami)@127.0.0.1:5432/myhours_test"
    echo "           - Or set up postgres user password: psql -c \"ALTER ROLE postgres WITH PASSWORD 'postgres';\""
    exit 1
  fi
  echo "[pre-push] Database connectivity and authentication verified"
else
  echo "[pre-push]  pg_isready not found - skipping database check"
fi

# Django system checks
if [[ -f "manage.py" ]]; then
  echo "[pre-push] Running Django system checks..."
  ${RUN}python manage.py check --settings="$DJANGO_SETTINGS_MODULE"
  
  echo "[pre-push] Checking for missing migrations..."
  ${RUN}python manage.py makemigrations --check --dry-run --settings="$DJANGO_SETTINGS_MODULE"
  
  echo "[pre-push] Django checks passed"
else
  echo "[pre-push]  No manage.py found - skipping Django checks"
fi

# Test execution
if [[ "${FULL:-1}" == "1" ]]; then
  # Full run with coverage
  coverage_threshold="${COV:-50}"
  echo "[pre-push] Running FULL test suite with coverage (threshold: ${coverage_threshold}%)"
  
  ${RUN}pytest \
    --cov=. \
    --cov-report=term-missing \
    --cov-fail-under="$coverage_threshold" \
    --create-db \
    --tb=short \
    -q
  
  echo "[pre-push] Full test suite passed with adequate coverage"
else
  # Quick run without coverage
  echo "[pre-push] ⚡ Running QUICK test suite (no coverage)"
  
  ${RUN}pytest \
    --tb=short \
    -q \
    --maxfail=3 \
    --durations=5
  
  echo "[pre-push] Quick test suite passed"
fi

# Success summary
echo ""
echo "[pre-push] All checks passed! Ready to push."
echo "[pre-push]"
echo "[pre-push] Tip: Use FULL=0 for faster local testing"
echo "[pre-push]      Use SKIP_PRE_PUSH=1 to skip checks entirely"