# Migration and Refactoring Scripts Archive

## Overview

This document tracks one-time migration and refactoring scripts that have been executed and archived. These scripts were used during development to automate code transformations and architecture improvements.

## Archive Location

Archived scripts are located in: `scripts/archive/migrations_2025-10/`

## Migration History

### October 2025 Migration Scripts

All scripts in this batch were successfully executed and archived on October 2025.

#### 1. Service Imports Codemod
**File**: `service_imports_codemod.py`
**Purpose**: Automated refactoring of service import statements across the codebase
**Status**: Completed
**Impact**: Updated import paths to follow new service architecture

#### 2. Test Framework Migration
**Files**:
- `refactor_tests.py`
- `refactor_tests_wave_c.py`
- `unittest_migration_codemod.py`
- `fix_wave_c_syntax.py`
- `fix_test_imports.py`

**Purpose**: Migration from Django's unittest to pytest framework
**Status**: Completed
**Impact**:
- Converted 1531 tests to pytest format
- Updated test assertions and fixtures
- Fixed syntax issues in wave C tests
- Corrected import statements

#### 3. Payroll Architecture Migration
**Files**:
- `migrate_to_new_payroll.py`
- `monthly_calculation_codemod.py`
- `overtime_thresholds_codemod.py`
- `field_migration_codemod.py`
- `fix_salary_field_names.py`

**Purpose**: Major refactoring of payroll calculation system
**Status**: Completed
**Impact**:
- Introduced Strategy Pattern for payroll calculations
- Migrated monthly calculation logic to new service architecture
- Updated overtime threshold calculations
- Renamed and migrated salary model fields
- Fixed field name inconsistencies

## Technical Notes

### Why These Scripts Are Archived

1. **One-Time Execution**: All scripts were designed for single execution during specific refactoring phases
2. **Historical Value**: Preserved for reference and audit purposes
3. **No Future Use**: The transformations they performed are permanent changes to the codebase

### Restoration

If you need to reference or restore any archived script:

```bash
# View archived scripts
ls scripts/archive/migrations_2025-10/

# Copy back if needed (not recommended)
cp scripts/archive/migrations_2025-10/[script_name].py scripts/
```

## Best Practices for Future Migrations

When creating new migration scripts:

1. **Document Purpose**: Include clear docstrings explaining what the script does
2. **Add Dry-Run Mode**: Always include a `--dry-run` flag for testing
3. **Backup First**: Ensure git commits or backups before running
4. **Test Coverage**: Verify tests pass before and after migration
5. **Archive After Use**: Move to archive/ with updated documentation

## October 2025 Scripts Reorganization

As part of the October 2025 cleanup, the following changes were made to improve scripts organization:

### Moved Scripts
- **`check_legacy_imports.py`** - Moved to `testing/` (code quality check)
- **`start_redis_ha.sh`** - Moved to `deployment/` (infrastructure setup)
- **`test_shabbat_standalone.py`** - Moved to `testing/` (test utility)

### Removed Scripts
- **`test_integrations.sh`** - Redundant with `testing/run-tests.sh`
- **`test_shabbat_with_db.sh`** - Redundant with direct pytest usage

These scripts were wrappers around pytest commands that are better executed directly or via the main test runner scripts.

### Kept in Root
- **`pre-push.sh`** - Remains in `scripts/` root as it's actively symlinked from `.git/hooks/pre-push`

## Related Documentation

- Test migration details: See test suite documentation
- Payroll architecture: See `payroll/services/README.md`
- Service patterns: See architecture documentation
- Redis HA setup: See `docs/REDIS_HIGH_AVAILABILITY.md`
