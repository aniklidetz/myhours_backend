#!/usr/bin/env python3
"""
Field Migration Codemod Script
Automatically migrates old field names to new unified payment structure field names.

Usage:
    python scripts/field_migration_codemod.py [--dry-run|--apply]

This script will:
1. Find all Python files in payroll/tests/ (excluding tests/legacy/)
2. Apply field name migrations according to the mapping table
3. Create backup files (.bak) before making changes (in --apply mode)
4. Report all changes made
"""

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Tuple


# Mapping table for field name migration
FIELD_MIGRATION_MAP = {
    'total_gross_pay': 'total_salary',
    'total_pay': 'total_salary', 
    'regular_pay': 'base_regular_pay',
    'overtime_pay_1': 'bonus_overtime_pay_1',
    'overtime_pay_2': 'bonus_overtime_pay_2',
    'sabbath_overtime_pay_1': 'bonus_sabbath_overtime_pay_1',
    'sabbath_overtime_pay_2': 'bonus_sabbath_overtime_pay_2',
}


def find_test_files(base_dir: str) -> List[Path]:
    """Find all Python test files, excluding legacy tests."""
    base_path = Path(base_dir)
    test_files = []
    
    # Find all .py files in payroll/tests/
    payroll_tests = base_path / "payroll" / "tests"
    if payroll_tests.exists():
        for py_file in payroll_tests.rglob("*.py"):
            # Skip legacy tests
            if "legacy" not in py_file.parts:
                test_files.append(py_file)
    
    return test_files


def create_backup(file_path: Path) -> None:
    """Create a backup of the original file."""
    backup_path = file_path.with_suffix(file_path.suffix + '.bak')
    shutil.copy2(file_path, backup_path)
    print(f"  Created backup: {backup_path}")


def migrate_field_names(content: str, file_path: Path) -> Tuple[str, List[str]]:
    """Apply field name migration to file content."""
    changes = []
    modified_content = content
    
    for old_field, new_field in FIELD_MIGRATION_MAP.items():
        original_content = modified_content
        
        # Patterns to match the field in different contexts
        patterns = [
            # Dictionary access: result["field_name"] or result['field_name']
            (rf'\["{re.escape(old_field)}"\]', f'["{new_field}"]'),
            (rf"\['{re.escape(old_field)}'\]", f"['{new_field}']"),
            
            # Object attribute access: calc.field_name (word boundary)
            (rf'\.{re.escape(old_field)}\b', f'.{new_field}'),
            
            # Keyword arguments: field_name= (word boundary)
            (rf'\b{re.escape(old_field)}=', f'{new_field}='),
            
            # String literals: "field_name" and 'field_name'
            (rf'"{re.escape(old_field)}"', f'"{new_field}"'),
            (rf"'{re.escape(old_field)}'", f"'{new_field}'"),
            
            # f-string and format references: {field_name}
            (rf'\{{{re.escape(old_field)}\}}', f'{{{new_field}}}'),
        ]
        
        total_replacements = 0
        for pattern, replacement in patterns:
            new_content, count = re.subn(pattern, replacement, modified_content)
            if count > 0:
                total_replacements += count
                modified_content = new_content
        
        if total_replacements > 0:
            changes.append(f"  {old_field} → {new_field} ({total_replacements} occurrences)")
    
    return modified_content, changes


def process_file(file_path: Path, dry_run: bool = False) -> bool:
    """Process a single file for field migration."""
    print(f"\nProcessing: {file_path.relative_to(Path.cwd())}")
    
    try:
        # Read original content
        with open(file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        # Apply field migrations
        modified_content, changes = migrate_field_names(original_content, file_path)
        
        if changes:
            print(f"  Found {len(changes)} field migration(s):")
            for change in changes:
                print(f"    {change}")
            
            if not dry_run:
                # Create backup
                create_backup(file_path)
                
                # Write modified content
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(modified_content)
                
                print(f"   Applied migrations to {file_path}")
            else:
                print(f"   [DRY RUN] Would apply migrations to {file_path}")
            
            return True
        else:
            print(f"   No field migrations needed")
            return False
            
    except Exception as e:
        print(f"   Error processing {file_path}: {e}")
        return False


def main():
    """Main execution function."""
    print(" Field Migration Codemod Script")
    print("=" * 50)
    
    # Parse command line arguments
    dry_run = True  # Default to safe mode
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg == '--dry-run' or arg == 'dry':
            dry_run = True
            print(" DRY RUN MODE (from command line)")
        elif arg == '--apply' or arg == 'apply':
            dry_run = False
            print(" APPLY MODE (from command line)")
        else:
            print(f"Usage: {sys.argv[0]} [--dry-run|--apply]")
            return
    else:
        # Default to dry-run for safety
        dry_run = True
        print(" DRY RUN MODE (default - use --apply to modify files)")
    
    # Get base directory (assume script is in scripts/ subdirectory)
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent
    
    print(f"Base directory: {base_dir}")
    print(f"Field migration map: {len(FIELD_MIGRATION_MAP)} mappings")
    
    # Find test files
    test_files = find_test_files(base_dir)
    print(f"Found {len(test_files)} test files to process")
    
    if not test_files:
        print("No test files found. Exiting.")
        return
    
    # Show migration mappings
    print("\nField migration mappings:")
    for old_field, new_field in FIELD_MIGRATION_MAP.items():
        print(f"  {old_field} → {new_field}")
    
    if dry_run:
        print("\n DRY RUN MODE - No files will be modified")
    else:
        print("\n LIVE MODE - Files will be modified")
    
    # Process files
    processed_count = 0
    modified_count = 0
    
    for file_path in test_files:
        processed_count += 1
        if process_file(file_path, dry_run):
            modified_count += 1
    
    # Summary
    print("\n" + "=" * 50)
    print(f" SUMMARY:")
    print(f"  Files processed: {processed_count}")
    print(f"  Files modified: {modified_count}")
    print(f"  Files unchanged: {processed_count - modified_count}")
    
    if not dry_run and modified_count > 0:
        print(f"\n Backup files created with .bak extension")
        print(f"  Please review changes before committing!")
    
    print("\n Field migration codemod complete!")


if __name__ == "__main__":
    main()