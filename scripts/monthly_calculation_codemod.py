#!/usr/bin/env python3
"""
Monthly payroll calculation standardization codemod script.

Standardizes monthly payroll calculations according to Israeli labor law:
- monthly_hourly = base_salary / 182
- proportional = monthly_hourly * worked_hours  
- Bonuses calculated as additions to base rate:
  * Weekdays: 0.25 (25%) for 8.6-10.6h, 0.50 (50%) for >10.6h
  * Sabbath: 0.50 (50%) for 8.6-10.6h, 0.75 (75%) for 10.6+h, 1.00 (100%) for extreme overtime
  * Night (weekdays): 0% for 0-7h, 25% for 7-9h, 50% for >9h
  * Night (sabbath): 50% for 0-7h, 75% for 7-9h, 100% for >9h
- Final: proportional_monthly + total_bonuses_monthly
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import List, Tuple, Dict

# Monthly calculation formula standardizations
MONTHLY_CALCULATION_PATTERNS = {
    # Base hourly rate calculation from monthly salary
    'base_hourly_formula': [
        # Standardize monthly norm divisor to 182
        (r"base_salary\s*/\s*180", "base_salary / 182"),
        (r"base_salary\s*/\s*Decimal\(['\"]180['\"]\)", "base_salary / MONTHLY_NORM_HOURS"),
        (r"monthly_salary\s*/\s*180", "monthly_salary / 182"),
        (r"monthly_salary\s*/\s*Decimal\(['\"]180['\"]\)", "monthly_salary / MONTHLY_NORM_HOURS"),
        
        # Standardize hourly rate variable names
        (r"hourly_rate\s*=\s*base_salary\s*/\s*\d+", "monthly_hourly = base_salary / MONTHLY_NORM_HOURS"),
        (r"hour_rate\s*=\s*base_salary\s*/\s*\d+", "monthly_hourly = base_salary / MONTHLY_NORM_HOURS"),
    ],
    
    # Proportional calculation
    'proportional_calculation': [
        (r"proportional\s*=\s*hourly_rate\s*\*\s*worked_hours", "proportional = monthly_hourly * worked_hours"),
        (r"base_pay\s*=\s*hourly_rate\s*\*\s*regular_hours", "proportional = monthly_hourly * worked_hours"),
        (r"regular_pay\s*=\s*hourly_rate\s*\*\s*hours", "proportional = monthly_hourly * worked_hours"),
    ],
    
    # Overtime bonus calculations - weekdays
    'weekday_bonuses': [
        # 8.6-10.6 hours: 25% bonus (0.25)
        (r"if\s+hours\s*>\s*8\.6\s+and\s+hours\s*<=\s*10\.6.*\*\s*1\.25", 
         "if hours > 8.6 and hours <= 10.6:\n        bonus_hours = hours - 8.6\n        bonus_pay += monthly_hourly * bonus_hours * Decimal('0.25')"),
        
        # >10.6 hours: 50% bonus (0.50) 
        (r"if\s+hours\s*>\s*10\.6.*\*\s*1\.50",
         "if hours > 10.6:\n        bonus_hours = hours - 10.6\n        bonus_pay += monthly_hourly * bonus_hours * Decimal('0.50')"),
    ],
    
    # Overtime bonus calculations - sabbath
    'sabbath_bonuses': [
        # 8.6-10.6 hours: 50% bonus (0.50)
        (r"sabbath.*hours\s*>\s*8\.6\s+and\s+hours\s*<=\s*10\.6.*\*\s*1\.75",
         "if hours > 8.6 and hours <= 10.6:\n        bonus_hours = hours - 8.6\n        sabbath_bonus += monthly_hourly * bonus_hours * Decimal('0.50')"),
        
        # 10.6+ hours: 75% bonus (0.75) 
        (r"sabbath.*hours\s*>\s*10\.6.*\*\s*2\.00",
         "if hours > 10.6:\n        bonus_hours = hours - 10.6\n        sabbath_bonus += monthly_hourly * bonus_hours * Decimal('0.75')"),
        
        # Extreme overtime: 100% bonus (1.00)
        (r"sabbath.*hours\s*>\s*12.*\*\s*2\.50",
         "if hours > 12:\n        extreme_hours = hours - 12\n        sabbath_bonus += monthly_hourly * extreme_hours * Decimal('1.00')"),
    ],
    
    # Night shift bonuses - weekdays  
    'night_weekday_bonuses': [
        # 0-7 hours: no bonus
        (r"night.*hours\s*<=\s*7.*\*\s*1\.0", "# Night 0-7 hours: no bonus (base rate only)"),
        
        # 7-9 hours: 25% bonus
        (r"night.*hours\s*>\s*7\s+and\s+hours\s*<=\s*9.*\*\s*1\.25",
         "if hours > 7 and hours <= 9:\n        bonus_hours = hours - 7\n        night_bonus += monthly_hourly * bonus_hours * Decimal('0.25')"),
        
        # >9 hours: 50% bonus
        (r"night.*hours\s*>\s*9.*\*\s*1\.50",
         "if hours > 9:\n        bonus_hours = hours - 9\n        night_bonus += monthly_hourly * bonus_hours * Decimal('0.50')"),
    ],
    
    # Night shift bonuses - sabbath
    'night_sabbath_bonuses': [
        # 0-7 hours: 50% bonus
        (r"night.*sabbath.*hours\s*<=\s*7.*\*\s*1\.50",
         "if hours <= 7:\n        night_sabbath_bonus += monthly_hourly * hours * Decimal('0.50')"),
        
        # 7-9 hours: 75% bonus  
        (r"night.*sabbath.*hours\s*>\s*7\s+and\s+hours\s*<=\s*9.*\*\s*1\.75",
         "if hours > 7 and hours <= 9:\n        bonus_hours = hours - 7\n        night_sabbath_bonus += monthly_hourly * bonus_hours * Decimal('0.75')"),
        
        # >9 hours: 100% bonus
        (r"night.*sabbath.*hours\s*>\s*9.*\*\s*2\.00",
         "if hours > 9:\n        bonus_hours = hours - 9\n        night_sabbath_bonus += monthly_hourly * bonus_hours * Decimal('1.00')"),
    ],
    
    # Final calculation formula
    'final_calculation': [
        (r"total_salary\s*=\s*base_pay\s*\+\s*overtime_pay", 
         "total_salary = proportional_monthly + total_bonuses_monthly"),
        (r"total_pay\s*=\s*regular_pay\s*\+\s*bonus_pay",
         "total_salary = proportional_monthly + total_bonuses_monthly"),
        (r"final_amount\s*=.*base.*\+.*bonus", 
         "total_salary = proportional_monthly + total_bonuses_monthly"),
    ],
    
    # Variable name standardization
    'variable_names': [
        (r"\bbase_pay\b", "proportional_monthly"),
        (r"\bregular_pay\b", "proportional_monthly"), 
        (r"\bovertime_pay\b", "total_bonuses_monthly"),
        (r"\bbonus_pay\b", "total_bonuses_monthly"),
        (r"\bhourly_rate\b", "monthly_hourly"),
    ],
    
    # Import standardization
    'imports': [
        (r"from decimal import Decimal",
         "from decimal import Decimal\nfrom payroll.tests.conftest import MONTHLY_NORM_HOURS"),
    ],
}

def find_test_files(base_path: str) -> List[str]:
    """Find all test files in payroll module, excluding legacy files."""
    test_files = []
    payroll_path = Path(base_path) / "payroll"
    
    for test_file in payroll_path.rglob("test_*.py"):
        # Skip legacy test files
        if "legacy" in str(test_file) or "archive" in str(test_file):
            continue
        test_files.append(str(test_file))
    
    return sorted(test_files)

def apply_monthly_calculation_standardizations(content: str) -> Tuple[str, int]:
    """Apply monthly calculation formula standardizations to content."""
    modified_content = content
    replacements_made = 0
    
    for category, patterns in MONTHLY_CALCULATION_PATTERNS.items():
        for old_pattern, new_pattern in patterns:
            # Check if content contains patterns related to monthly calculations
            if not re.search(r"(monthly|salary|hourly|proportional|bonus)", modified_content, re.IGNORECASE):
                continue
                
            matches = re.findall(old_pattern, modified_content, re.IGNORECASE | re.MULTILINE)
            if matches:
                modified_content = re.sub(old_pattern, new_pattern, modified_content, flags=re.IGNORECASE | re.MULTILINE)
                replacements_made += len(matches)
                print(f"    {category}: {len(matches)} replacements ({old_pattern[:50]}... -> {new_pattern[:50]}...)")
    
    return modified_content, replacements_made

def process_test_file(file_path: str, dry_run: bool = True) -> Tuple[bool, int]:
    """Process a single test file for monthly calculation standardization."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"  ERROR: Could not read {file_path}: {e}")
        return False, 0
    
    modified_content, replacements_made = apply_monthly_calculation_standardizations(original_content)
    
    if replacements_made == 0:
        return False, 0
    
    if not dry_run:
        # Create backup
        backup_path = file_path + '.monthly_calc_bak'
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
    parser = argparse.ArgumentParser(description='Standardize monthly payroll calculation formulas')
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='Show what would be changed without modifying files (default)')
    parser.add_argument('--apply', action='store_true',
                        help='Actually apply the changes to files')
    args = parser.parse_args()
    
    # Determine if we should apply changes
    apply_changes = args.apply
    
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_files = find_test_files(base_path)
    
    print(f"Monthly Payroll Calculation Formula Standardization")
    print(f"Mode: {'APPLY' if apply_changes else 'DRY RUN'}")
    print(f"Found {len(test_files)} test files to process\n")
    
    print("Standardizing formulas:")
    print("  • monthly_hourly = base_salary / 182")
    print("  • proportional = monthly_hourly * worked_hours")
    print("  • Bonuses as additions to base rate:")
    print("    - Weekdays: 25% (8.6-10.6h), 50% (>10.6h)")
    print("    - Sabbath: 50% (8.6-10.6h), 75% (10.6+h), 100% (extreme)")
    print("    - Night weekdays: 0% (0-7h), 25% (7-9h), 50% (>9h)")
    print("    - Night sabbath: 50% (0-7h), 75% (7-9h), 100% (>9h)")
    print("  • Final: proportional_monthly + total_bonuses_monthly\n")
    
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
            print(f"  No changes needed")
        
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