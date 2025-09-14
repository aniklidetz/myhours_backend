#!/usr/bin/env python3
"""
Fix test import issues after unittest migration.

Fixes:
1. Duplicate imports 
2. Missing PayrollTestMixin imports
3. Syntax errors in method calls
4. Import consolidation
"""

import os
import re
import sys
from pathlib import Path

def fix_test_file_imports(file_path: str):
    """Fix import issues in a test file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"  ERROR: Could not read {file_path}: {e}")
        return False

    original_content = content
    modifications = []

    # Fix duplicate imports - remove redundant lines
    if "from payroll.tests.helpers import MONTHLY_NORM_HOURS\nfrom payroll.tests.helpers import" in content:
        content = re.sub(
            r"from payroll\.tests\.helpers import MONTHLY_NORM_HOURS\nfrom payroll\.tests\.helpers import ([^\n]+)",
            r"from payroll.tests.helpers import MONTHLY_NORM_HOURS, \1",
            content
        )
        modifications.append("Consolidated duplicate helpers imports")

    # Fix missing PayrollTestMixin import
    if "PayrollTestMixin" in content and "from payroll.tests.helpers import" in content:
        if "PayrollTestMixin" not in content.split("from payroll.tests.helpers import")[1].split("\n")[0]:
            content = re.sub(
                r"from payroll\.tests\.helpers import ([^\n]+)",
                r"from payroll.tests.helpers import PayrollTestMixin, \1",
                content
            )
            modifications.append("Added PayrollTestMixin import")

    # Fix syntax errors in method calls like self.self.self.payroll_service
    content = re.sub(r"self\.self\.self\.payroll_service", "self.payroll_service", content)
    if "self.self.self.payroll_service" in original_content:
        modifications.append("Fixed triple self.self.self syntax error")

    # Fix double self.self.payroll_service
    content = re.sub(r"self\.self\.payroll_service", "self.payroll_service", content)  
    if "self.self.payroll_service" in original_content:
        modifications.append("Fixed double self.self syntax error")

    # Fix missing closing parentheses in make_context calls
    content = re.sub(
        r"make_context\(([^)]+), fast_mode=([^)]+)\n\s*\)",
        r"make_context(\1, fast_mode=\2)",
        content
    )
    if re.search(r"make_context\([^)]+, fast_mode=[^)]+\n\s*\)", original_content):
        modifications.append("Fixed missing closing parentheses in make_context")

    # Remove trailing spaces and fix missing newlines
    lines = content.split('\n')
    fixed_lines = []
    for line in lines:
        # Remove trailing spaces
        fixed_line = line.rstrip()
        fixed_lines.append(fixed_line)

    # Ensure file ends with newline
    content = '\n'.join(fixed_lines) + '\n'
    if not original_content.endswith('\n'):
        modifications.append("Added missing final newline")

    # Only write if there were changes
    if content != original_content:
        # Create backup
        backup_path = file_path + '.import_fix_bak'
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original_content)
        
        # Write fixed content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"  FIXED: {file_path}")
        for mod in modifications:
            print(f"    - {mod}")
        print(f"    Backup: {backup_path}")
        return True
    else:
        print(f"  OK: {file_path} (no changes needed)")
        return False

def main():
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    payroll_tests_path = Path(base_path) / "payroll" / "tests"
    
    test_files = []
    for test_file in payroll_tests_path.glob("test_*.py"):
        if "legacy" not in str(test_file) and test_file.name != "helpers.py":
            test_files.append(str(test_file))
    
    # Also check management command tests
    management_tests = Path(base_path) / "payroll" / "management" / "commands"
    for test_file in management_tests.glob("test_*.py"):
        test_files.append(str(test_file))
    
    test_files.sort()
    
    print(f"Fixing Test Import Issues")
    print(f"Found {len(test_files)} test files to check\n")
    
    fixed_count = 0
    for file_path in test_files:
        rel_path = os.path.relpath(file_path, base_path)
        print(f"Checking {rel_path}...")
        
        if fix_test_file_imports(file_path):
            fixed_count += 1
    
    print(f"\nSummary:")
    print(f"  Files checked: {len(test_files)}")
    print(f"  Files fixed: {fixed_count}")
    
    return fixed_count

if __name__ == '__main__':
    sys.exit(main())