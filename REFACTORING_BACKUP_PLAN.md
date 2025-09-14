# Integration Refactoring - Backup & Rollback Plan

## Pre-Deletion Validation Status: ✅ COMPLETED

### Critical Files Updated & Validated:
- `integrations/views.py` - Updated to use UnifiedShabbatService
- `payroll/services/external.py` - Updated to use UnifiedShabbatService
- `integrations/services/hebcal_service.py` - Updated to use UnifiedShabbatService
- `payroll/services.py` - Removed old import (uses ShiftSplitter)
- `worktime/management/commands/add_sabbath_shifts.py` - Updated to UnifiedShabbatService
- `payroll/models.py` - Updated with lazy import (previously fixed)

### Test Results:
- Integration tests: 95/96 passing (1 deselected slow test)
- Critical integrations: 5/5 passing
- All production paths validated
- No circular dependencies detected

## Files Ready for Safe Removal:

### 1. Primary Deprecated Services:
- `integrations/services/sunrise_sunset_service.py`
- `integrations/services/enhanced_sunrise_sunset_service.py`

### 2. Test-Only References (can be removed with tests):
- `integrations/tests/test_external_apis.py` (lines testing old services)
- `payroll/tests/test_*` (various test files with old service references)
- `scripts/test_shabbat_migration.py` (migration test script)

### 3. Obsolete Management Commands:
- `payroll/management/commands/test_shabbat_integration.py` (tests old service)

## Backup Strategy:

### Git Branch Backup:
```bash
# Create backup branch before deletion
git checkout -b backup/old-shabbat-services-$(date +%Y%m%d)
git add .
git commit -m "backup: preserve old shabbat services before deletion"
git checkout main
```

### File-Level Backup:
```bash
# Create backup directory
mkdir -p backups/old-services-$(date +%Y%m%d)

# Backup old services
cp integrations/services/sunrise_sunset_service.py backups/old-services-*/
cp integrations/services/enhanced_sunrise_sunset_service.py backups/old-services-*/
cp payroll/management/commands/test_shabbat_integration.py backups/old-services-*/
```

## Rollback Strategy:

### If Issues Discovered After Deletion:
1. **Immediate Rollback** (if critical production issue):
   ```bash
   git checkout backup/old-shabbat-services-$(date +%Y%m%d)
   # OR restore from backups/ directory
   ```

2. **Selective Restoration** (if specific functionality needed):
   ```bash
   # Restore specific service if needed
   git checkout backup-branch -- integrations/services/sunrise_sunset_service.py

   # Update imports in affected files
   # Run tests to validate restoration
   ```

3. **Migration Path Back** (if gradual rollback needed):
   - Restore old service files
   - Update imports in critical production files only
   - Keep UnifiedShabbatService as primary, old as fallback
   - Gradual transition back if required

## Safe Deletion Order:

### Phase 1: Remove Test Dependencies
1. Clean up test files that import old services
2. Remove migration test scripts
3. Update test documentation

### Phase 2: Remove Management Commands
1. Remove obsolete management commands
2. Update command documentation

### Phase 3: Remove Core Services
1. Remove `enhanced_sunrise_sunset_service.py`
2. Remove `sunrise_sunset_service.py`
3. Clean up any remaining import references

### Phase 4: Final Cleanup
1. Remove deprecation warnings (no longer needed)
2. Update documentation to reflect new architecture
3. Clean up backup files and test scripts

## Validation Checkpoints:

### After Each Phase:
- [ ] Run integration tests: `./scripts/test_integrations.sh`
- [ ] Test critical production paths
- [ ] Check Django deployment checks: `python manage.py check --deploy`
- [ ] Verify UnifiedShabbatService functionality

### Before Production Deploy:
- [ ] Full test suite passing
- [ ] Load test critical API endpoints
- [ ] Verify Shabbat calculation accuracy
- [ ] Check monitoring/logging for errors

## Risk Mitigation:

### Low Risk Files (Safe to Remove):
- Test files importing old services
- Migration scripts
- Obsolete management commands

### Medium Risk Files (Test Carefully):
- Old service files themselves
- Documentation references

### Zero Risk (Already Migrated):
- All production code paths now use UnifiedShabbatService
- All critical integrations validated
- Backward compatibility maintained through deprecation warnings

## Success Criteria:
- [ ] All deprecated services removed
- [ ] No import errors in any module
- [ ] Integration tests passing
- [ ] Production API endpoints functional
- [ ] Shabbat calculations accurate and precise

## Emergency Contact:
If issues arise during deletion process, rollback using backup branch and investigate specific failure points before re-attempting removal.