#!/usr/bin/env python3
"""
Overtime thresholds and rates standardization codemod script.

Standardizes overtime calculations according to Israeli labor law:
- Weekdays: 0-8.6 @100%, 8.6-10.6 @125%, >10.6 @150%
- Sabbath: 0-8.6 @150%, 8.6-10.6 @175%, >10.6 @200%
- Night (weekdays): 0-7 @100%, 7-9 @125%, >9 @150%
- Night (sabbath): 0-7 @150%, 7-9 @175%, >9 @200%

Uses constants from payroll/tests/conftest.py:
- ISRAELI_DAILY_NORM_HOURS = Decimal('8.6')
- NIGHT_NORM_HOURS = Decimal('7')
- MONTHLY_NORM_HOURS = Decimal('182')
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Israeli labor law overtime thresholds and rates
OVERTIME_STANDARDIZATIONS = {
    # Replace hardcoded 8.0 with 8.6 for daily norm
    "daily_norm_8_0": [
        (r"Decimal\(['\"]8\.0['\"]\)", "Decimal('8.6')"),
        (r"8\.0", "8.6"),  # Only in overtime context
    ],
    # Replace hardcoded 7.0 with 7 for night norm
    "night_norm_7_0": [
        (r"Decimal\(['\"]7\.0['\"]\)", "Decimal('7')"),
    ],
    # Replace hardcoded monthly norms with 182
    "monthly_norm_180": [
        (r"Decimal\(['\"]180['\"]\)", "Decimal('182')"),
        (r"180", "182"),  # Only in monthly context
    ],
    # Standardize overtime rate patterns
    "overtime_rates_weekday": [
        # Weekdays: 0-8.6 @100%, 8.6-10.6 @125%, >10.6 @150%
        (r"hours <= 8\.0", "hours <= 8.6"),
        (r"hours > 8\.0 and hours <= 10\.0", "hours > 8.6 and hours <= 10.6"),
        (r"hours > 10\.0", "hours > 10.6"),
        (r"if hours <= 8:", "if hours <= Decimal('8.6'):"),
        (r"elif hours <= 10:", "elif hours <= Decimal('10.6'):"),
    ],
    # Standardize sabbath overtime patterns
    "overtime_rates_sabbath": [
        # Sabbath: 0-8.6 @150%, 8.6-10.6 @175%, >10.6 @200%
        (r"sabbath.*hours <= 8\.0", "hours <= 8.6"),
        (r"sabbath.*hours > 8\.0 and hours <= 10\.0", "hours > 8.6 and hours <= 10.6"),
        (r"sabbath.*hours > 10\.0", "hours > 10.6"),
    ],
    # Standardize night shift patterns
    "overtime_rates_night": [
        # Night: 0-7 @100%/150%, 7-9 @125%/175%, >9 @150%/200%
        (r"night.*hours <= 7\.0", "hours <= 7"),
        (r"night.*hours > 7\.0 and hours <= 9\.0", "hours > 7 and hours <= 9"),
        (r"night.*hours > 9\.0", "hours > 9"),
    ],
    # Import standardization for conftest constants
    "conftest_imports": [
        (
            r"from decimal import Decimal",
            "from decimal import Decimal\nfrom payroll.tests.conftest import ISRAELI_DAILY_NORM_HOURS, NIGHT_NORM_HOURS, MONTHLY_NORM_HOURS",
        ),
        (r"Decimal\(['\"]8\.6['\"]\)", "ISRAELI_DAILY_NORM_HOURS"),
        (r"Decimal\(['\"]7['\"]\)", "NIGHT_NORM_HOURS"),
        (r"Decimal\(['\"]182['\"]\)", "MONTHLY_NORM_HOURS"),
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


def apply_overtime_standardizations(content: str) -> Tuple[str, int]:
    """Apply overtime threshold and rate standardizations to content."""
    modified_content = content
    replacements_made = 0

    for category, patterns in OVERTIME_STANDARDIZATIONS.items():
        for old_pattern, new_pattern in patterns:
            # Use word boundaries for number replacements to avoid false matches
            if category.endswith("_8_0") and old_pattern == r"8\.0":
                # Only replace 8.0 in overtime/hours context
                if re.search(
                    r"(hours?|overtime|daily.*norm)", modified_content, re.IGNORECASE
                ):
                    old_pattern = r"\b8\.0\b"
            elif category.endswith("_180") and old_pattern == "180":
                # Only replace 180 in monthly/norm context
                if re.search(r"(monthly|norm)", modified_content, re.IGNORECASE):
                    old_pattern = r"\b180\b"

            matches = re.findall(old_pattern, modified_content)
            if matches:
                modified_content = re.sub(old_pattern, new_pattern, modified_content)
                replacements_made += len(matches)
                print(
                    f"    {category}: {len(matches)} replacements ({old_pattern} -> {new_pattern})"
                )

    return modified_content, replacements_made


def process_test_file(file_path: str, dry_run: bool = True) -> Tuple[bool, int]:
    """Process a single test file for overtime standardization."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            original_content = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"  ERROR: Could not read {file_path}: {e}")
        return False, 0

    modified_content, replacements_made = apply_overtime_standardizations(
        original_content
    )

    if replacements_made == 0:
        return False, 0

    if not dry_run:
        # Create backup
        backup_path = file_path + ".overtime_bak"
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(original_content)

        # Write modified content
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(modified_content)

        print(f"  UPDATED: {file_path} (backup: {backup_path})")
    else:
        print(f"  DRY RUN: Would update {file_path}")

    return True, replacements_made


def main():
    parser = argparse.ArgumentParser(
        description="Standardize overtime thresholds and rates"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show what would be changed without modifying files (default)",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Actually apply the changes to files"
    )
    args = parser.parse_args()

    # Determine if we should apply changes
    apply_changes = args.apply

    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_files = find_test_files(base_path)

    print(f"Overtime Thresholds and Rates Standardization")
    print(f"Mode: {'APPLY' if apply_changes else 'DRY RUN'}")
    print(f"Found {len(test_files)} test files to process\n")

    # Process files
    modified_files = []
    total_replacements = 0

    for file_path in test_files:
        rel_path = os.path.relpath(file_path, base_path)
        print(f"Processing {rel_path}...")

        was_modified, replacements = process_test_file(
            file_path, dry_run=not apply_changes
        )

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


if __name__ == "__main__":
    sys.exit(main())
