# Scripts Directory

This directory contains utility scripts organized by purpose to maintain and manage the MyHours backend system.

## Directory Structure

```
scripts/
├── cleanup/           # Data cleanup and maintenance scripts
├── database/          # Database backup and setup scripts  
├── deployment/        # Production deployment files
├── testing/           # Test execution and coverage scripts
└── utilities/         # General utility tools
```

## Available Scripts

###  Shabbat Service Migration Scripts
- **`test_shabbat_migration.py`** - Full Django-based migration readiness test
- **`test_shabbat_standalone.py`** - Standalone logic tests (no Django/DB required)

###  Cleanup Scripts (`cleanup/`)
- **`cleanup_old_files.sh`** - Comprehensive cleanup: logs, backups, cache, and temporary files
- **`setup_log_rotation.sh`** - Log rotation with compression and archiving
- **`setup_crontab.sh`** - Automated cleanup scheduling via crontab
- **`cleanup_biometric_simple.sh`** - Cleans up biometric test data

### 🗃️ Database Scripts (`database/`)
- **`setup_database.py`** - Initial database setup and configuration
- **`backup_database.sh`** - Creates timestamped backups of PostgreSQL and MongoDB

###  Deployment Scripts (`deployment/`)
- **`Dockerfile.optimized`** - Optimized Docker configuration for production

###  Testing Scripts (`testing/`)
- **`run-tests.sh`** - Main test execution script
- **`coverage.sh`** - Generates test coverage reports

###  Utilities (`utilities/`)
- **`url_inspector.py`** - URL pattern inspection tool

## Usage Examples

```bash
# Run comprehensive tests with coverage
./scripts/testing/run-tests.sh

# Generate coverage report
./scripts/testing/coverage.sh

# Backup databases
./scripts/database/backup_database.sh

# Clean up old files and rotate logs
./scripts/cleanup/cleanup_old_files.sh

# Set up automated cleanup (crontab)
./scripts/cleanup/setup_crontab.sh

# Clean biometric test data
./scripts/cleanup/cleanup_biometric_simple.sh
```

## Configuration

Most scripts use environment variables for configuration:
- `DJANGO_SETTINGS_MODULE` - Django settings module
- `DATABASE_URL` - Database connection string
- `SECRET_KEY` - Django secret key

## Backup Strategy

Database backups are automatically timestamped and stored in `backups/` directory:
- PostgreSQL: Custom format dumps (`.dump`)
- MongoDB: Compressed tar archives (`.tar.gz`)
- Retention: Last 3 backups are kept automatically

## Maintenance

Run cleanup scripts regularly:
- **Daily**: `cleanup_old_files.sh` for temporary files
- **Weekly**: Database backups
- **Monthly**: Archive old coverage reports

## Notes

- All scripts are designed to run from the project root directory
- Backup scripts require appropriate database permissions
- Coverage reports are automatically archived to prevent disk space issues