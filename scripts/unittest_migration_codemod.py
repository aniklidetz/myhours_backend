#!/usr/bin/env python3
"""
Unittest migration codemod script.

Migrates payroll tests from pytest fixture dependencies to unittest.TestCase patterns:
1. Updates imports from conftest.py to helpers.py
2. Removes pytest fixture usage patterns
3. Adds PayrollTestMixin where beneficial
4. Maintains all existing functionality through re-exports

This script ensures tests no longer depend on pytest fixtures while preserving
all current imports and functionality.
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import List, Tuple, Dict

# Import migration patterns
UNITTEST_MIGRATION_PATTERNS = {
    # Update imports from conftest to helpers
    'import_migrations': [
        # Single line imports
        (r"from payroll\.tests\.conftest import (.+)",
         r"from payroll.tests.helpers import \1"),
        
        # Multi-line imports (basic pattern)
        (r"from payroll\.tests\.conftest import \(",
         "from payroll.tests.helpers import ("),
    ],
    
    # Remove pytest fixture function parameters
    'remove_fixture_params': [
        # Remove payroll_service fixture parameter
        (r"def test_\w+\(self, payroll_service\):",
         r"def test_\w+(self):"),
        (r"def test_\w+\(self, payroll_service, ([^)]+)\):",
         r"def test_\w+(self, \1):"),
        
        # Remove israeli_labor_constants fixture parameter  
        (r"def test_\w+\(self, israeli_labor_constants\):",
         r"def test_\w+(self):"),
        (r"def test_\w+\(self, israeli_labor_constants, ([^)]+)\):",
         r"def test_\w+(self, \1):"),
        
        # Remove both fixtures
        (r"def test_\w+\(self, payroll_service, israeli_labor_constants\):",
         r"def test_\w+(self):"),
        (r"def test_\w+\(self, israeli_labor_constants, payroll_service\):",
         r"def test_\w+(self):"),
    ],
    
    # Add PayrollTestMixin to test classes that would benefit
    'add_mixin': [
        # Classes that use payroll_service or constants heavily
        (r"class (\w+Test.*)\(TestCase\):",
         r"class \1(PayrollTestMixin, TestCase):"),
        (r"class (\w+Test.*)\(APITestCase\):",
         r"class \1(PayrollTestMixin, APITestCase):"),
    ],
    
    # Update fixture usage to setUp() initialization
    'fixture_to_setup': [
        # Replace direct fixture usage with self.payroll_service
        (r"payroll_service\.calculate\(",
         "self.payroll_service.calculate("),
        (r"payroll_service\.",
         "self.payroll_service."),
        
        # Replace constants fixture usage
        (r"israeli_labor_constants\[(['\"])([^'\"]+)\1\]",
         r"self.constants['\2']"),
    ],
    
    # Ensure helpers import is added when mixin is used
    'ensure_helpers_import': [
        (r"from payroll\.tests\.helpers import",
         "from payroll.tests.helpers import PayrollTestMixin, "),
    ],
}

def find_test_files(base_path: str) -> List[str]:
    """Find all test files in payroll module, excluding legacy files."""
    test_files = []
    payroll_path = Path(base_path) / "payroll"
    
    for test_file in payroll_path.rglob("test_*.py"):
        # Skip legacy test files and helpers.py itself
        if ("legacy" in str(test_file) or 
            "archive" in str(test_file) or
            test_file.name == "helpers.py"):
            continue
        test_files.append(str(test_file))
    
    return sorted(test_files)

def analyze_test_file(content: str) -> Dict[str, bool]:
    """Analyze test file to determine what migrations are needed."""
    analysis = {
        'has_conftest_imports': bool(re.search(r"from payroll\.tests\.conftest import", content)),
        'has_fixture_params': bool(re.search(r"def test_\w+\([^)]*(?:payroll_service|israeli_labor_constants)", content)),
        'has_fixture_usage': bool(re.search(r"(?:payroll_service|israeli_labor_constants)\.", content)),
        'needs_mixin': bool(re.search(r"payroll_service\.|israeli_labor_constants\[", content)),
        'is_testcase': bool(re.search(r"class \w+.*\(.*TestCase\):", content)),
    }
    return analysis

def apply_unittest_migrations(content: str, analysis: Dict[str, bool]) -> Tuple[str, int]:
    """Apply unittest migration patterns to content based on analysis."""
    modified_content = content
    replacements_made = 0
    
    # Always update imports if they exist
    if analysis['has_conftest_imports']:
        for category in ['import_migrations']:
            patterns = UNITTEST_MIGRATION_PATTERNS[category]
            for old_pattern, new_pattern in patterns:
                matches = re.findall(old_pattern, modified_content)
                if matches:
                    modified_content = re.sub(old_pattern, new_pattern, modified_content)
                    replacements_made += len(matches)
                    print(f"    {category}: {len(matches)} replacements")
    
    # Remove fixture parameters if they exist  
    if analysis['has_fixture_params']:
        for category in ['remove_fixture_params']:
            patterns = UNITTEST_MIGRATION_PATTERNS[category]
            for old_pattern, new_pattern in patterns:
                matches = re.findall(old_pattern, modified_content)
                if matches:
                    modified_content = re.sub(old_pattern, new_pattern, modified_content)
                    replacements_made += len(matches)
                    print(f"    {category}: {len(matches)} replacements")
    
    # Add mixin if needed and beneficial
    if analysis['needs_mixin'] and analysis['is_testcase']:
        for category in ['add_mixin']:
            patterns = UNITTEST_MIGRATION_PATTERNS[category]
            for old_pattern, new_pattern in patterns:
                # Only add mixin if not already present
                if "PayrollTestMixin" not in modified_content:
                    matches = re.findall(old_pattern, modified_content)
                    if matches:
                        modified_content = re.sub(old_pattern, new_pattern, modified_content)
                        replacements_made += len(matches)
                        print(f"    {category}: {len(matches)} replacements")
                        
                        # Ensure PayrollTestMixin is imported
                        if "from payroll.tests.helpers import" in modified_content:
                            if "PayrollTestMixin" not in modified_content:
                                modified_content = re.sub(
                                    r"from payroll\.tests\.helpers import ([^\\n]+)",
                                    r"from payroll.tests.helpers import PayrollTestMixin, \1",
                                    modified_content
                                )
                                replacements_made += 1
                                print(f"    Added PayrollTestMixin import")
    
    # Update fixture usage to setUp patterns
    if analysis['has_fixture_usage']:
        for category in ['fixture_to_setup']:
            patterns = UNITTEST_MIGRATION_PATTERNS[category]
            for old_pattern, new_pattern in patterns:
                matches = re.findall(old_pattern, modified_content)
                if matches:
                    modified_content = re.sub(old_pattern, new_pattern, modified_content)
                    replacements_made += len(matches)
                    print(f"    {category}: {len(matches)} replacements")
    
    return modified_content, replacements_made

def process_test_file(file_path: str, dry_run: bool = True) -> Tuple[bool, int]:
    """Process a single test file for unittest migration."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"  ERROR: Could not read {file_path}: {e}")
        return False, 0
    
    analysis = analyze_test_file(original_content)
    
    # Skip files that don't need migration
    if not any(analysis.values()):
        return False, 0
    
    modified_content, replacements_made = apply_unittest_migrations(original_content, analysis)
    
    if replacements_made == 0:
        return False, 0
    
    if not dry_run:
        # Create backup
        backup_path = file_path + '.unittest_migration_bak'
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original_content)
        
        # Write modified content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        
        print(f"  UPDATED: {file_path} (backup: {backup_path})")
    else:
        print(f"  DRY RUN: Would update {file_path}")
    
    return True, replacements_made

def main():
    parser = argparse.ArgumentParser(description='Migrate payroll tests from pytest to unittest patterns')
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='Show what would be changed without modifying files (default)')
    parser.add_argument('--apply', action='store_true',
                        help='Actually apply the changes to files')
    args = parser.parse_args()
    
    # Determine if we should apply changes
    apply_changes = args.apply
    
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_files = find_test_files(base_path)
    
    print(f"Unittest Migration for Payroll Tests")
    print(f"Mode: {'APPLY' if apply_changes else 'DRY RUN'}")
    print(f"Found {len(test_files)} test files to process\n")
    
    print("Migration tasks:")
    print("  1. Update imports: conftest.py -> helpers.py")
    print("  2. Remove pytest fixture parameters from test methods")
    print("  3. Add PayrollTestMixin where beneficial")
    print("  4. Update fixture usage to self.* patterns")
    print("  5. Maintain all existing functionality via re-exports\n")
    
    # Process files
    modified_files = []
    total_replacements = 0
    
    for file_path in test_files:
        rel_path = os.path.relpath(file_path, base_path)
        print(f"Processing {rel_path}...")
        
        was_modified, replacements = process_test_file(file_path, dry_run=not apply_changes)
        
        if was_modified:
            modified_files.append(rel_path)
            total_replacements += replacements
        else:
            print(f"  No migration needed")
        
        print()
    
    # Summary
    print(f"Summary:")
    print(f"  Files processed: {len(test_files)}")
    print(f"  Files modified: {len(modified_files)}")
    print(f"  Total replacements: {total_replacements}")
    
    if modified_files:
        print(f"\nModified files:")
        for file_path in modified_files:
            print(f"  - {file_path}")
    
    if not apply_changes and modified_files:
        print(f"\nTo apply changes, run: {sys.argv[0]} --apply")
    
    return 0 if not modified_files else len(modified_files)

if __name__ == '__main__':
    sys.exit(main())