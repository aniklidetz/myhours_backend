#!/usr/bin/env python3
"""
Test Refactoring Program: Migration from Adapters to Direct PayrollService

This script implements a 4-wave migration strategy to replace legacy adapter usage 
with direct PayrollService calls in test files.

Usage:
    python scripts/refactor_tests.py --wave A  # Helper factory creation (DONE manually)
    python scripts/refactor_tests.py --wave B  # Mass import replacement
    python scripts/refactor_tests.py --wave C  # Fix labor law constants (8.0→8.6)
    python scripts/refactor_tests.py --wave D  # Remove adapter dependencies
    python scripts/refactor_tests.py --all     # Run all waves
    python scripts/refactor_tests.py --dry-run # Preview changes only
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Set
import argparse


class TestRefactorer:
    """Handles systematic refactoring of test files from adapters to PayrollService."""
    
    def __init__(self, repo_root: Path, dry_run: bool = False):
        self.repo_root = repo_root
        self.dry_run = dry_run
        self.changes_made = []
        
        # Files that use adapters (excluding legacy)
        self.target_test_files = [
            'payroll/tests/test_api_integrations.py',
            'payroll/tests/test_enhanced_payroll_service_core.py', 
            'payroll/tests/test_holiday_calculations.py',
            'payroll/tests/test_monthly_employee_calculations.py',
            'payroll/tests/test_monthly_overtime_fixed_logic.py',
            'payroll/tests/test_overtime_calculations.py',
            'payroll/tests/test_payroll_compensation.py',
            'payroll/tests/test_payroll_services_basic.py',
            'payroll/tests/test_sabbath_calculations.py',
            'payroll/tests/test_salary_active_constraint.py',
            'payroll/tests/test_shift_splitting.py',
            'worktime/tests/test_night_shift_calculations.py',
        ]
    
    def wave_b_replace_imports_and_usage(self):
        """
        Wave B: Replace adapter imports and usage patterns.
        
        Transforms:
        FROM: 
            # Legacy adapter import (removed after migration)
            service = EnhancedPayrollCalculationService(employee, year, month)
            result = service.calculate_monthly_salary_enhanced()
            
        TO:
            from payroll.services.enums import CalculationStrategy
            from payroll.tests.conftest import make_context
            
            context = make_context(employee, year, month)
            result = payroll_service.calculate(context, CalculationStrategy.ENHANCED)
        """
        print(" Wave B: Replacing adapter imports and usage patterns...")
        
        for test_file in self.target_test_files:
            file_path = self.repo_root / test_file
            if not file_path.exists():
                print(f"    Skipping {test_file} (not found)")
                continue
                
            print(f"   Processing {test_file}")
            content = file_path.read_text()
            original_content = content
            
            # Replace imports
            content = re.sub(
                r'from payroll\.services\.adapters import.*EnhancedPayrollCalculationService.*\n',
                '''from payroll.services.enums import CalculationStrategy
from payroll.tests.conftest import make_context

''',
                content
            )
            
            # Add payroll_service fixture usage if not present
            if 'def test_' in content and 'payroll_service' not in content:
                # Find first test method and add fixture parameter
                content = re.sub(
                    r'def (test_\w+)\(self\)',
                    r'def \1(self, payroll_service)',
                    content,
                    count=1
                )
                
            # Replace service instantiation and usage
            content = re.sub(
                r'service = EnhancedPayrollCalculationService\(\s*([^,]+),\s*([^,]+),\s*([^)]+)\)',
                r'context = make_context(\1, \2, \3)',
                content
            )
            
            # Replace method calls
            content = re.sub(
                r'result = service\.calculate_monthly_salary_enhanced\(\)',
                r'result = payroll_service.calculate(context, CalculationStrategy.ENHANCED)',
                content
            )
            
            # Update result field access patterns
            content = re.sub(
                r'result\[[\'"](total_gross_pay)[\'\"]\]',
                r'result["total_salary"]',
                content
            )
            
            if content != original_content:
                if not self.dry_run:
                    file_path.write_text(content)
                self.changes_made.append(f"Updated {test_file}: Replaced adapter patterns")
                print(f"     Updated adapter usage patterns")
            else:
                print(f"      No changes needed")
    
    def wave_c_fix_labor_constants(self):
        """
        Wave C: Fix Israeli labor law constants (8.0 → 8.6 hours).
        
        Updates hardcoded values to use correct Israeli daily norm.
        """
        print(" Wave C: Fixing Israeli labor law constants...")
        
        patterns_to_fix = [
            (r'Decimal\([\'"]8\.0[\'"]\)', 'Decimal("8.6")'),
            (r'Decimal\([\'"]10\.0[\'"]\)', 'Decimal("10.6")'),  # 8.6 + 2 hours overtime
            (r'hours\s*<=\s*8\.0', 'hours <= Decimal("8.6")'),
            (r'hours\s*<=\s*8', 'hours <= Decimal("8.6")'),
            (r'regular_hours.*8\.', 'regular_hours == Decimal("8.6")'),
        ]
        
        for test_file in self.target_test_files:
            file_path = self.repo_root / test_file
            if not file_path.exists():
                continue
                
            print(f"   Processing {test_file}")
            content = file_path.read_text()
            original_content = content
            
            for pattern, replacement in patterns_to_fix:
                content = re.sub(pattern, replacement, content)
            
            # Add import for labor constants
            if 'israeli_labor_constants' not in content and ('8.6' in content or '8.0' in content):
                if 'from payroll.tests.conftest import' in content:
                    content = re.sub(
                        r'from payroll\.tests\.conftest import (.*)',
                        r'from payroll.tests.conftest import \1, ISRAELI_DAILY_NORM_HOURS',
                        content
                    )
                else:
                    # Add new import after existing imports
                    import_location = content.find('\nfrom payroll.')
                    if import_location != -1:
                        content = content[:import_location] + '\nfrom payroll.tests.conftest import ISRAELI_DAILY_NORM_HOURS' + content[import_location:]
            
            if content != original_content:
                if not self.dry_run:
                    file_path.write_text(content)
                self.changes_made.append(f"Updated {test_file}: Fixed labor law constants")
                print(f"     Fixed Israeli labor law constants")
    
    def wave_d_remove_adapter_dependencies(self):
        """
        Wave D: Remove remaining adapter dependencies and clean up.
        
        Ensures no non-legacy tests depend on adapters.
        """
        print(" Wave D: Removing adapter dependencies...")
        
        for test_file in self.target_test_files:
            file_path = self.repo_root / test_file
            if not file_path.exists():
                continue
                
            print(f"   Processing {test_file}")
            content = file_path.read_text()
            original_content = content
            
            # Remove any remaining adapter imports
            content = re.sub(
                r'from payroll\.services\.adapters import.*\n',
                '',
                content
            )
            
            # Remove unused imports
            lines = content.split('\n')
            cleaned_lines = []
            
            for line in lines:
                # Skip empty import lines or adapter references
                if (line.strip() and not 
                    (line.strip().startswith('from payroll.services.adapters') or
                     'EnhancedPayrollCalculationService' in line and 'import' in line)):
                    cleaned_lines.append(line)
            
            content = '\n'.join(cleaned_lines)
            
            if content != original_content:
                if not self.dry_run:
                    file_path.write_text(content)
                self.changes_made.append(f"Updated {test_file}: Removed adapter dependencies")
                print(f"     Cleaned up adapter dependencies")
    
    def update_static_checker(self):
        """Update static checker to forbid adapters in non-legacy tests."""
        print(" Updating static legacy import checker...")
        
        checker_path = self.repo_root / 'scripts/check_legacy_imports.py'
        if not checker_path.exists():
            print("    Static checker not found")
            return
            
        content = checker_path.read_text()
        
        # Add stricter patterns for adapter usage
        if 'adapters' not in content:
            # Find LEGACY_PATTERNS section and add adapter pattern
            pattern_match = re.search(r'LEGACY_PATTERNS = \[(.*?)\]', content, re.DOTALL)
            if pattern_match:
                existing_patterns = pattern_match.group(1)
                new_patterns = f'''{existing_patterns.strip()},
    re.compile(r'from\\s+payroll\\.services\\.adapters\\s+import'),'''
                
                content = content.replace(pattern_match.group(0), f'LEGACY_PATTERNS = [{new_patterns}\n]')
                
                # Update allowed patterns
                if 'tests/legacy/' not in content:
                    content = re.sub(
                        r"(ALLOWED_PATTERNS = \[.*?)(])",
                        r"\1    'tests/legacy/',\n\2",
                        content,
                        flags=re.DOTALL
                    )
                
                if not self.dry_run:
                    checker_path.write_text(content)
                self.changes_made.append("Updated static checker to catch adapter usage")
                print("     Updated static import checker")
    
    def generate_summary(self):
        """Generate refactoring summary and recommendations."""
        print("\n" + "="*60)
        print(" REFACTORING SUMMARY")
        print("="*60)
        
        if self.dry_run:
            print(" DRY RUN MODE - No changes were made")
        else:
            print(f" Made {len(self.changes_made)} changes:")
            for change in self.changes_made:
                print(f"   • {change}")
        
        print("\n NEXT STEPS:")
        print("1. Run tests to verify refactoring:")
        print("   pytest payroll/tests/ -v")
        print("2. Run static checker:")
        print("   python scripts/check_legacy_imports.py")
        print("3. Check for deprecation warnings:")
        print("   pytest payroll/tests/ -v --tb=short | grep -i deprecat")
        print("4. Update any failing tests to use new PayrollService contract")
        
        print("\n MIGRATION COMPLETE CRITERIA:")
        print(" All tests pass without deprecation warnings")
        print(" Static checker shows 0 adapter imports in non-legacy code")  
        print(" Only tests/legacy/ modules use adapters")
        print(" All tests use 8.6-hour Israeli labor norm")


def main():
    parser = argparse.ArgumentParser(description="Refactor tests from adapters to PayrollService")
    parser.add_argument("--wave", choices=['A', 'B', 'C', 'D'], help="Run specific wave")
    parser.add_argument("--all", action="store_true", help="Run all waves")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes only")
    
    args = parser.parse_args()
    
    # Find repository root
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    
    refactorer = TestRefactorer(repo_root, dry_run=args.dry_run)
    
    print(" TEST REFACTORING PROGRAM")
    print("=" * 50)
    print(f"Repository: {repo_root}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE CHANGES'}")
    
    if args.wave == 'A':
        print("Wave A: Helper factory already created in conftest.py")
    elif args.wave == 'B':
        refactorer.wave_b_replace_imports_and_usage()
    elif args.wave == 'C':
        refactorer.wave_c_fix_labor_constants()
    elif args.wave == 'D':
        refactorer.wave_d_remove_adapter_dependencies()
        refactorer.update_static_checker()
    elif args.all:
        print("Running all waves...")
        refactorer.wave_b_replace_imports_and_usage()
        refactorer.wave_c_fix_labor_constants()
        refactorer.wave_d_remove_adapter_dependencies()
        refactorer.update_static_checker()
    else:
        print("Please specify --wave [A|B|C|D] or --all")
        return 1
    
    refactorer.generate_summary()
    return 0


if __name__ == '__main__':
    sys.exit(main())