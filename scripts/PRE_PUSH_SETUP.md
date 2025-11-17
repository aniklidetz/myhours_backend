# Pre-Push Hook Setup Guide

## Overview

The pre-push hook (`scripts/pre-push.sh`) runs automated quality checks before allowing code to be pushed to the remote repository. This ensures code quality and prevents broken code from being pushed.

## Initial Setup

### 1. Configure Database Connection

The pre-push hook requires a working PostgreSQL database. Update the `.env.test` file with your database credentials.

**For Docker PostgreSQL (recommended):**

```bash
# .env.test
DJANGO_SETTINGS_MODULE=myhours.settings_ci
DATABASE_URL=postgresql://myhours_user:secure_password_123@127.0.0.1:5432/myhours_test
```

**Verify your PostgreSQL is running:**

```bash
docker ps | grep postgres
```

**Test database connection:**

```bash
PGPASSWORD=secure_password_123 psql -h 127.0.0.1 -U myhours_user -d postgres -c "SELECT 1;"
```

### 2. Verify Hook Installation

Check if the pre-push hook is properly installed:

```bash
ls -la .git/hooks/pre-push
# Should show: .git/hooks/pre-push -> ../../scripts/pre-push.sh
```

If not installed, create the symlink:

```bash
ln -sf ../../scripts/pre-push.sh .git/hooks/pre-push
```

## Usage

### Normal Push (Full Checks)

By default, every `git push` will run the full test suite with coverage:

```bash
git push
# Runs: Django checks + Full test suite + Coverage validation
```

This can take 3-5 minutes depending on your machine.

### Quick Push (Skip Coverage)

For faster local testing, skip coverage checks:

```bash
FULL=0 git push
# Runs: Django checks + Quick test suite (no coverage)
```

This typically takes 1-2 minutes.

### Skip Hook Entirely

For work-in-progress branches, you can skip the hook completely:

```bash
SKIP_PRE_PUSH=1 git push
# Skips all checks
```

**Warning:** Only use this for temporary WIP branches. Never skip checks for production branches.

### Custom Coverage Threshold

Override the default coverage threshold (50%):

```bash
COV=60 git push
# Requires 60% test coverage
```

## What Gets Checked

The pre-push hook performs the following checks in order:

1. **Database Connectivity**
   - Verifies PostgreSQL is running and accessible
   - Tests authentication with provided credentials

2. **Django System Checks**
   - Runs `python manage.py check`
   - Validates models, settings, and configuration

3. **Migration Check**
   - Runs `python manage.py makemigrations --check`
   - Ensures no uncommitted migrations

4. **Test Suite** (depends on FULL setting)
   - **FULL=1 (default):** Runs all tests with coverage validation
   - **FULL=0:** Runs tests without coverage, stops after 3 failures

## Troubleshooting

### "PostgreSQL authentication failed"

**Problem:** Cannot connect to PostgreSQL database.

**Solutions:**

1. Check if Docker containers are running:
   ```bash
   docker ps | grep postgres
   ```

2. Verify `.env.test` has correct credentials:
   ```bash
   cat .env.test
   # Should show: DATABASE_URL=postgresql://myhours_user:secure_password_123@...
   ```

3. Test connection manually:
   ```bash
   PGPASSWORD=secure_password_123 psql -h 127.0.0.1 -U myhours_user -d postgres -c "SELECT 1;"
   ```

### "Database myhours_test does not exist"

This is **normal**. The test runner will create the database automatically using `--create-db` flag.

### Tests Taking Too Long

**Option 1:** Use quick mode
```bash
FULL=0 git push
```

**Option 2:** Run specific test modules locally before pushing
```bash
pytest payroll/tests/test_specific_module.py
```

**Option 3:** Temporarily skip for WIP branches
```bash
SKIP_PRE_PUSH=1 git push
```

### "No such file or directory: .env.test"

Create the `.env.test` file:

```bash
cat > .env.test << 'EOF'
DJANGO_SETTINGS_MODULE=myhours.settings_ci
DATABASE_URL=postgresql://myhours_user:secure_password_123@127.0.0.1:5432/myhours_test
EOF
```

## Best Practices

1. **Run Quick Checks Frequently**
   ```bash
   FULL=0 git push  # During development
   ```

2. **Run Full Checks Before PR**
   ```bash
   git push  # Full checks with coverage
   ```

3. **Never Skip Checks for Main Branches**
   - Always run full checks when merging to `main` or `develop`
   - Use `SKIP_PRE_PUSH=1` only for temporary WIP branches

4. **Keep Tests Fast**
   - Write focused unit tests
   - Use `@pytest.mark.slow` for long-running tests
   - Mock external services

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `FULL` | `1` | Run full tests with coverage (1) or quick tests (0) |
| `COV` | `50` | Coverage threshold percentage |
| `SKIP_PRE_PUSH` | `0` | Skip all pre-push checks (1) or run normally (0) |
| `DATABASE_URL` | from `.env.test` | PostgreSQL connection string |
| `DJANGO_SETTINGS_MODULE` | from `.env.test` | Django settings module for tests |

## CI/CD Integration

The pre-push hook uses the same test configuration as CI:

- **Local:** Uses `.env.test` for database credentials
- **CI:** Uses GitHub Actions secrets and environment variables

This ensures consistency between local and CI test environments.
