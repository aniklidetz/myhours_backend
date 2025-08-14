# Testing Setup and Configuration

## Problem Solved

The tests were failing due to a conflict between the local PostgreSQL installation (Homebrew) and the Docker PostgreSQL container. Both were trying to use port 5432, causing Django tests to connect to the wrong PostgreSQL instance.

## Root Cause

1. **Local PostgreSQL**: Homebrew PostgreSQL@14 was running on port 5432
2. **Docker PostgreSQL**: myhours_postgres container was also using port 5432
3. **Conflict**: External connections went to local PostgreSQL instead of Docker container
4. **Auth Issue**: Local PostgreSQL didn't have the required users (`myhours_user`) for Django tests

## Solution Applied

### 1. Stop Local PostgreSQL
```bash
brew services stop postgresql@14
```

### 2. Database Permissions Setup
Created initialization script at `docker-entrypoint-initdb.d/03-setup-test-permissions.sql`:
```sql
-- Ensure postgres user has proper permissions
ALTER USER postgres WITH PASSWORD 'postgres';
ALTER USER postgres CREATEDB;

-- Ensure myhours_user has all necessary permissions
ALTER USER myhours_user CREATEDB;
ALTER USER myhours_user CREATEROLE;

-- Create dedicated test user
CREATE USER django_test_user WITH 
    SUPERUSER 
    CREATEDB 
    CREATEROLE 
    PASSWORD 'django_test_password';
```

### 3. Test Databases Created
```bash
docker exec myhours_postgres psql -U myhours_user -d myhours_db -c "CREATE DATABASE myhours_test OWNER myhours_user;"
```

## Running Tests

### Environment Setup
```bash
# Ensure local PostgreSQL is stopped
brew services stop postgresql@14

# Ensure Docker containers are running
docker-compose up -d

# Check PostgreSQL is accessible
docker exec myhours_postgres psql -U myhours_user -d myhours_db -c "SELECT version();"
```

### Test Command
```bash
# Run single test
DJANGO_SETTINGS_MODULE=myhours.settings_ci \
DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_test" \
SECRET_KEY="test-secret-key" \
./venv/bin/pytest -q --no-cov core/tests/test_exceptions.py::CustomExceptionHandlerTest::test_context_with_anonymous_user -v

# Run all exception tests
DJANGO_SETTINGS_MODULE=myhours.settings_ci \
DATABASE_URL="postgresql://myhours_user:secure_password_123@localhost:5432/myhours_test" \
SECRET_KEY="test-secret-key" \
./venv/bin/pytest -q --no-cov core/tests/test_exceptions.py -v
```

### Test Environment Variables
- `DJANGO_SETTINGS_MODULE`: `myhours.settings_ci`
- `DATABASE_URL`: `postgresql://myhours_user:secure_password_123@localhost:5432/myhours_test`  
- `SECRET_KEY`: `test-secret-key`

## Verification Steps

1. **Check Docker containers are running:**
```bash
docker-compose ps
```

2. **Verify PostgreSQL connection:**
```bash
PGPASSWORD=secure_password_123 psql -h localhost -p 5432 -U myhours_user -d myhours_test -c "SELECT current_user;"
```

3. **Test database creation permissions:**
```bash
PGPASSWORD=secure_password_123 psql -h localhost -p 5432 -U myhours_user -d postgres -c "CREATE DATABASE test_temp; DROP DATABASE test_temp;"
```

## Files Modified

1. **`docker-entrypoint-initdb.d/03-setup-test-permissions.sql`** - PostgreSQL user permissions
2. **`docker-entrypoint-initdb.d/02-grant-test-permissions.sql`** - Additional test permissions  
3. **`myhours/test_settings.py`** - Alternative test settings (optional)
4. **`TESTING.md`** - This documentation

## Common Issues

### Issue: "permission denied to create database"
**Solution**: Ensure local PostgreSQL is stopped and Docker PostgreSQL is running

### Issue: "role does not exist"  
**Solution**: Make sure you're connecting to Docker PostgreSQL (localhost:5432) not local

### Issue: "database does not exist"
**Solution**: Create test databases using the commands above

### Issue: Tests still fail after setup
**Solution**: Check that all containers are healthy:
```bash
docker-compose ps
docker logs myhours_postgres
```

## Success Indicators

✅ Tests pass: `50 passed in 2.57s`
✅ No database creation errors
✅ PostgreSQL accessible from host
✅ Django can create test databases
✅ All exception tests working

## Future Development

For new developers:
1. Clone repository
2. Run `docker-compose up -d`  
3. Ensure local PostgreSQL is stopped: `brew services stop postgresql@14`
4. Run tests using the commands above

The Docker setup now properly supports Django test database creation without conflicts.