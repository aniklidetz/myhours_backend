#!/usr/bin/env python3
"""
Fix salary field name issues in test files.

Changes:
- monthly_hourly -> hourly_rate (in Salary model creation/updates)
"""

import os
import re
import sys
from pathlib import Path


def fix_salary_field_names(file_path: str):
    """Fix salary field name issues in a test file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"  ERROR: Could not read {file_path}: {e}")
        return False

    original_content = content
    modifications = []

    # Fix monthly_hourly -> hourly_rate in Salary model operations
    content = re.sub(r"monthly_hourly=", "hourly_rate=", content)
    if "monthly_hourly=" in original_content:
        modifications.append("Changed monthly_hourly to hourly_rate")

    # Fix in serializer data dictionaries
    content = re.sub(r'"monthly_hourly":', '"hourly_rate":', content)
    if '"monthly_hourly":' in original_content:
        modifications.append("Changed monthly_hourly key in serializer data")

    # Only write if there were changes
    if content != original_content:
        # Create backup
        backup_path = file_path + ".salary_field_fix_bak"
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(original_content)

        # Write fixed content
        with open(file_path, "w", encoding="utf-8") as f:
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

    # Find files with monthly_hourly references
    files_to_fix = []
    payroll_tests_path = Path(base_path) / "payroll" / "tests"

    for test_file in payroll_tests_path.glob("*.py"):
        if test_file.name.startswith("test_"):
            try:
                with open(test_file, "r") as f:
                    content = f.read()
                if "monthly_hourly" in content:
                    files_to_fix.append(str(test_file))
            except:
                continue

    files_to_fix.sort()

    print(f"Fixing Salary Field Names")
    print(f"Found {len(files_to_fix)} test files with field name issues\n")

    fixed_count = 0
    for file_path in files_to_fix:
        rel_path = os.path.relpath(file_path, base_path)
        print(f"Checking {rel_path}...")

        if fix_salary_field_names(file_path):
            fixed_count += 1

    print(f"\nSummary:")
    print(f"  Files checked: {len(files_to_fix)}")
    print(f"  Files fixed: {fixed_count}")

    return fixed_count


if __name__ == "__main__":
    sys.exit(main())
