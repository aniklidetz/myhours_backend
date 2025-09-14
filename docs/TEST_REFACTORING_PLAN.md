# Test Refactoring Plan: From Adapters to PayrollService

## Overview

This document outlines the systematic migration of 31 test files from legacy adapter usage to direct PayrollService integration. The goal is to eliminate adapter dependencies while maintaining test functionality and improving code quality.

## Current State

**Adapter Usage Analysis:**
- ✅ 2 files in `payroll/tests/legacy/` - correctly isolated
- ⚠️ 31 test files using adapters through `payroll.services.adapters`
- ⚠️ Tests using adapters get deprecation warnings
- ⚠️ Hardcoded 8.0-hour constants (should be 8.6 for Israeli law)

## 4-Wave Migration Strategy

### Wave A: Foundation Setup ✅ COMPLETED

**Objective:** Create test infrastructure for new PayrollService usage

**Actions:**
- ✅ Created `payroll/tests/conftest.py` with helper functions
- ✅ Added `make_context()` factory function
- ✅ Added `payroll_service` pytest fixture
- ✅ Added Israeli labor law constants (8.6 hours)
- ✅ Added result validation helpers

**Files Created:**
- `payroll/tests/conftest.py`
- `scripts/refactor_tests.py`

### Wave B: Mass Import Replacement

**Objective:** Replace adapter imports and usage patterns across all test files

**Transformation Pattern:**
```python
# BEFORE (using adapters)
from payroll.services.adapters import EnhancedPayrollCalculationService

def test_something(self):
    service = EnhancedPayrollCalculationService(employee, 2025, 8)
    result = service.calculate_monthly_salary_enhanced()
    assert result['total_gross_pay'] == expected

# AFTER (direct PayrollService)
from payroll.services.enums import CalculationStrategy
from payroll.tests.conftest import make_context

def test_something(self, payroll_service):
    context = make_context(employee, 2025, 8)
    result = payroll_service.calculate(context, CalculationStrategy.ENHANCED)
    assert result['total_salary'] == expected
```

**Target Files (12 files):**
- `payroll/tests/test_api_integrations.py` - 10 adapter usages
- `payroll/tests/test_enhanced_payroll_service_core.py` - 8 adapter usages  
- `payroll/tests/test_holiday_calculations.py` - 6 adapter usages
- `payroll/tests/test_monthly_employee_calculations.py` - 4 adapter usages
- `payroll/tests/test_monthly_overtime_fixed_logic.py` - 3 adapter usages
- `payroll/tests/test_overtime_calculations.py` - 7 adapter usages
- `payroll/tests/test_payroll_compensation.py` - 5 adapter usages
- `payroll/tests/test_payroll_services_basic.py` - 9 adapter usages
- `payroll/tests/test_sabbath_calculations.py` - 8 adapter usages
- `payroll/tests/test_salary_active_constraint.py` - 2 adapter usages
- `payroll/tests/test_shift_splitting.py` - 4 adapter usages
- `worktime/tests/test_night_shift_calculations.py` - 1 adapter usage

**Field Mapping Changes:**
- `total_gross_pay` → `total_salary`
- `regular_pay` → `breakdown.regular_pay` 
- `overtime_pay` → `breakdown.overtime_pay`
- Add `breakdown`, `is_sabbath`, `calculation_method` validations

**Command:**
```bash
python scripts/refactor_tests.py --wave B
```

### Wave C: Israeli Labor Law Compliance

**Objective:** Fix hardcoded 8.0-hour values to use correct 8.6-hour Israeli daily norm

**Changes Required:**
- Replace `Decimal("8.0")` → `Decimal("8.6")`
- Replace `Decimal("10.0")` → `Decimal("10.6")` (8.6 + 2 overtime)
- Update test assertions for regular hours
- Import `ISRAELI_DAILY_NORM_HOURS` constant

**High-Priority Files:**
- `test_overtime_calculations.py` - Multiple 8.0 hour references
- `test_enhanced_payroll_service_core.py` - Core calculation logic
- `test_sabbath_calculations.py` - Sabbath overtime thresholds

**Command:**
```bash
python scripts/refactor_tests.py --wave C
```

### Wave D: Cleanup and Isolation

**Objective:** Remove all adapter dependencies from non-legacy tests

**Actions:**
1. Remove remaining `from payroll.services.adapters import` statements
2. Update static checker to forbid adapters outside `tests/legacy/`
3. Verify no deprecation warnings in test output
4. Clean up unused import statements

**Static Checker Update:**
```python
LEGACY_PATTERNS = [
    re.compile(r'from\s+payroll\.services\s+import\s+.*PayrollCalculationService'),
    re.compile(r'from\s+payroll\.optimized_service\s+import'),
    re.compile(r'from\s+payroll\.services\.adapters\s+import'),  # NEW
]

ALLOWED_PATTERNS = [
    'tests/legacy/',
    'payroll/services.py',
    'payroll/services/__init__.py',
    'check_legacy_imports.py',
]
```

**Command:**
```bash
python scripts/refactor_tests.py --wave D
```

## Execution Plan

### Phase 1: Preparation
```bash
# 1. Create branch for refactoring
git checkout -b refactor/tests-to-payroll-service

# 2. Run baseline tests
pytest payroll/tests/ -v --tb=short

# 3. Check current adapter usage
grep -r "EnhancedPayrollCalculationService" payroll/tests/ | grep -v legacy
```

### Phase 2: Execute Waves
```bash
# Wave B: Mass replacement
python scripts/refactor_tests.py --wave B --dry-run  # Preview
python scripts/refactor_tests.py --wave B            # Execute

# Wave C: Fix labor constants  
python scripts/refactor_tests.py --wave C --dry-run
python scripts/refactor_tests.py --wave C

# Wave D: Clean up
python scripts/refactor_tests.py --wave D --dry-run
python scripts/refactor_tests.py --wave D
```

### Phase 3: Validation
```bash
# 1. All waves at once (alternative)
python scripts/refactor_tests.py --all

# 2. Run tests after each wave
pytest payroll/tests/ -v

# 3. Check for deprecation warnings
pytest payroll/tests/ -v 2>&1 | grep -i deprecat

# 4. Verify static checker
python scripts/check_legacy_imports.py

# 5. Test legacy isolation
pytest -m "legacy" -v      # Should work
pytest -m "not legacy" -v  # Should have no adapter deps
```

## Risk Mitigation

### Low Risk
- Import replacements - automated with clear patterns
- Field name mapping - well-defined transformations
- Fixture integration - standard pytest patterns

### Medium Risk  
- Complex test logic changes - may require manual review
- Israeli labor law constants - need validation with business logic
- Mock object updates - integration test mocks may need adjustment

### High Risk
- Calculation result format changes - could break assertions
- External API integration mocks - timing/caching behavior differences
- Performance test expectations - new service may have different metrics

### Rollback Plan
```bash
# If issues arise during refactoring:
git stash                    # Save partial work
git checkout main           # Return to stable state
git branch -D refactor/tests-to-payroll-service  # Clean up

# For partial rollback:
git reset HEAD~1            # Undo last wave
python scripts/refactor_tests.py --wave [previous] --dry-run
```

## Success Criteria

### ✅ Technical Success
- [ ] All 31 test files migrated from adapters to PayrollService
- [ ] Zero deprecation warnings in test output
- [ ] Static checker shows no adapter imports in non-legacy code
- [ ] All tests pass with new service architecture
- [ ] 8.6-hour Israeli labor norm used consistently

### ✅ Quality Success  
- [ ] Test execution time unchanged or improved
- [ ] Code coverage maintained or increased
- [ ] No regression in payroll calculation accuracy
- [ ] Clear separation between legacy and modern test code

### ✅ Maintenance Success
- [ ] Developers can write new tests using direct PayrollService
- [ ] Legacy adapter code isolated to `tests/legacy/` only
- [ ] CI prevents new adapter dependencies in non-legacy code
- [ ] Documentation updated with new test patterns

## Timeline

**Estimated Duration:** 2-3 hours

- **Wave A:** ✅ COMPLETED (30 minutes)
- **Wave B:** 45 minutes (mass replacement)  
- **Wave C:** 30 minutes (labor law fixes)
- **Wave D:** 30 minutes (cleanup)
- **Validation:** 30 minutes (testing and verification)

## Post-Migration Actions

1. **Update README:** Add section on writing payroll tests
2. **Team Training:** Share new test patterns with developers
3. **Adapter Removal:** Schedule deletion of `payroll/services/adapters.py` 
4. **Performance Review:** Compare test execution times before/after
5. **Documentation:** Update API documentation with new service contract

---

**Next Command to Run:**
```bash
python scripts/refactor_tests.py --wave B --dry-run
```