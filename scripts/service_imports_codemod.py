#!/usr/bin/env python3
"""
Service Imports Codemod Script
Standardizes PayrollService usage across all test files.

This script will:
1. Remove old/deprecated service imports (EnhancedPayrollCalculationService, adapters)
2. Add standardized PayrollService imports
3. Replace service instantiation patterns
4. Update service method calls to use the new architecture

Usage:
    python scripts/service_imports_codemod.py [--dry-run|--apply]
"""

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Deprecated imports and references to remove
DEPRECATED_PATTERNS = [
    # Direct imports
    (
        r"from\s+payroll\.services\.enhanced_payroll_calculation_service\s+import\s+EnhancedPayrollCalculationService",
        "",
    ),
    (r"from\s+payroll\.services\s+import\s+EnhancedPayrollCalculationService", ""),
    (r"import\s+payroll\.services\.enhanced_payroll_calculation_service", ""),
    # Adapter imports
    (r"from\s+payroll\.services\.adapters\s+import\s+.*", ""),
    (r"import\s+payroll\.services\.adapters.*", ""),
    # Other deprecated patterns
    (r"from\s+payroll\.optimized_service\s+import\s+.*", ""),
    (r"import\s+payroll\.optimized_service.*", ""),
    # Mock/patch patterns in decorators and calls
    (
        r'@patch\("payroll\.services\.EnhancedPayrollCalculationService"\)',
        '@patch("payroll.services.payroll_service.PayrollService")',
    ),
    (
        r'@patch\("payroll\.views\.EnhancedPayrollCalculationService"\)',
        '@patch("payroll.services.payroll_service.PayrollService")',
    ),
    (
        r'patch\("payroll\.services\.EnhancedPayrollCalculationService"\)',
        'patch("payroll.services.payroll_service.PayrollService")',
    ),
    (
        r'patch\("payroll\.views\.EnhancedPayrollCalculationService"\)',
        'patch("payroll.services.payroll_service.PayrollService")',
    ),
    # String references in comments and docstrings
    (r"EnhancedPayrollCalculationService", "PayrollService"),
]

# Standard imports to add (if not already present)
STANDARD_IMPORTS = [
    "from payroll.services.payroll_service import PayrollService",
    "from payroll.services.enums import CalculationStrategy",
]

# Service instantiation patterns
OLD_SERVICE_PATTERNS = [
    # Old service instantiation
    (
        r"service\s*=\s*EnhancedPayrollCalculationService\(\)",
        "service = PayrollService()",
    ),
    (
        r"self\.service\s*=\s*EnhancedPayrollCalculationService\(\)",
        "self.service = PayrollService()",
    ),
    (
        r"enhanced_service\s*=\s*EnhancedPayrollCalculationService\(\)",
        "enhanced_service = PayrollService()",
    ),
    # Method call patterns - these are more complex and will need context-aware replacement
]

# Method call patterns to replace
OLD_METHOD_CALLS = {
    "calculate_daily_pay_hourly": "calculate",
    "calculate_daily_bonuses_monthly": "calculate",
    "calculate_daily_pay": "calculate",
    "calculate_monthly_summary": "calculate",
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
    backup_path = file_path.with_suffix(file_path.suffix + ".service_bak")
    shutil.copy2(file_path, backup_path)
    print(f"  Created backup: {backup_path}")


def remove_deprecated_patterns(content: str) -> Tuple[str, List[str]]:
    """Remove deprecated patterns from content."""
    changes = []
    modified_content = content

    for pattern, replacement in DEPRECATED_PATTERNS:
        matches = re.findall(pattern, modified_content, re.MULTILINE)
        if matches:
            modified_content = re.sub(
                pattern, replacement, modified_content, flags=re.MULTILINE
            )
            if replacement == "":
                changes.append(
                    f"Removed deprecated pattern: {len(matches)} occurrences"
                )
            else:
                changes.append(
                    f"Updated deprecated pattern: {len(matches)} occurrences"
                )

    return modified_content, changes


def add_standard_imports(content: str) -> Tuple[str, List[str]]:
    """Add standard imports if not already present."""
    changes = []
    modified_content = content

    # Check if we need to add imports
    needs_payroll_service = (
        "PayrollService" in modified_content
        and "from payroll.services.payroll_service import PayrollService"
        not in modified_content
    )
    needs_calculation_strategy = (
        "CalculationStrategy" in modified_content
        and "from payroll.services.enums import CalculationStrategy"
        not in modified_content
    )

    if needs_payroll_service or needs_calculation_strategy:
        # Find the best place to insert imports (after existing imports)
        lines = modified_content.split("\n")
        import_end_idx = 0

        # Find the last import line
        for i, line in enumerate(lines):
            if line.strip().startswith(("import ", "from ")) and "import" in line:
                import_end_idx = i

        # Insert new imports after the last import
        new_imports = []
        if needs_payroll_service:
            new_imports.append(
                "from payroll.services.payroll_service import PayrollService"
            )
            changes.append("Added PayrollService import")
        if needs_calculation_strategy:
            new_imports.append("from payroll.services.enums import CalculationStrategy")
            changes.append("Added CalculationStrategy import")

        # Insert the new imports
        for i, new_import in enumerate(new_imports):
            lines.insert(import_end_idx + 1 + i, new_import)

        modified_content = "\n".join(lines)

    return modified_content, changes


def update_service_instantiation(content: str) -> Tuple[str, List[str]]:
    """Update service instantiation patterns."""
    changes = []
    modified_content = content

    for old_pattern, new_pattern in OLD_SERVICE_PATTERNS:
        matches = re.findall(old_pattern, modified_content)
        if matches:
            modified_content = re.sub(old_pattern, new_pattern, modified_content)
            changes.append(f"Updated service instantiation: {len(matches)} occurrences")

    return modified_content, changes


def update_method_calls(content: str) -> Tuple[str, List[str]]:
    """Update service method calls to use new architecture."""
    changes = []
    modified_content = content

    # Pattern to match service method calls
    for old_method, new_method in OLD_METHOD_CALLS.items():
        # Match patterns like: service.old_method(args) or self.service.old_method(args)
        pattern = rf"(\w*\.?service\.)({old_method})\s*\("
        matches = re.findall(pattern, modified_content)

        if matches:
            # For calculate methods, we need to add context and strategy
            if new_method == "calculate":
                # This is complex - we need to analyze the context
                # For now, let's just replace the method name and add a comment
                replacement = rf"\1{new_method}(context, CalculationStrategy.ENHANCED  # TODO: Review parameters"
                modified_content = re.sub(pattern, replacement, modified_content)
                changes.append(
                    f"Updated {old_method} -> {new_method}: {len(matches)} occurrences (manual review needed)"
                )
            else:
                replacement = rf"\1{new_method}("
                modified_content = re.sub(pattern, replacement, modified_content)
                changes.append(
                    f"Updated {old_method} -> {new_method}: {len(matches)} occurrences"
                )

    return modified_content, changes


def clean_up_whitespace(content: str) -> str:
    """Clean up extra whitespace from removed imports."""
    # Remove multiple consecutive empty lines
    content = re.sub(r"\n\s*\n\s*\n", "\n\n", content)
    return content


def migrate_service_imports(content: str, file_path: Path) -> Tuple[str, List[str]]:
    """Apply service import migration to file content."""
    all_changes = []
    modified_content = content

    # Step 1: Remove deprecated patterns
    modified_content, changes = remove_deprecated_patterns(modified_content)
    all_changes.extend(changes)

    # Step 2: Add standard imports if needed
    modified_content, changes = add_standard_imports(modified_content)
    all_changes.extend(changes)

    # Step 3: Update service instantiation
    modified_content, changes = update_service_instantiation(modified_content)
    all_changes.extend(changes)

    # Step 4: Update method calls
    modified_content, changes = update_method_calls(modified_content)
    all_changes.extend(changes)

    # Step 5: Clean up whitespace
    modified_content = clean_up_whitespace(modified_content)

    return modified_content, all_changes


def process_file(file_path: Path, dry_run: bool = False) -> bool:
    """Process a single file for service import migration."""
    print(f"\nProcessing: {file_path.relative_to(Path.cwd())}")

    try:
        # Read original content
        with open(file_path, "r", encoding="utf-8") as f:
            original_content = f.read()

        # Apply service migrations
        modified_content, changes = migrate_service_imports(original_content, file_path)

        if changes:
            print(f"  Found {len(changes)} service migration(s):")
            for change in changes:
                print(f"    {change}")

            if not dry_run:
                # Create backup
                create_backup(file_path)

                # Write modified content
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(modified_content)

                print(f"   Applied migrations to {file_path}")
            else:
                print(f"   [DRY RUN] Would apply migrations to {file_path}")

            return True
        else:
            print(f"   No service migrations needed")
            return False

    except Exception as e:
        print(f"   Error processing {file_path}: {e}")
        return False


def main():
    """Main execution function."""
    print(" Service Imports Codemod Script")
    print("=" * 50)

    # Parse command line arguments
    dry_run = True  # Default to safe mode
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg == "--dry-run" or arg == "dry":
            dry_run = True
            print(" DRY RUN MODE (from command line)")
        elif arg == "--apply" or arg == "apply":
            dry_run = False
            print("⚡ APPLY MODE (from command line)")
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
    print(f"Standard imports: {len(STANDARD_IMPORTS)} imports")
    print(f"Deprecated patterns: {len(DEPRECATED_PATTERNS)} patterns")

    # Find test files
    test_files = find_test_files(base_dir)
    print(f"Found {len(test_files)} test files to process")

    if not test_files:
        print("No test files found. Exiting.")
        return

    # Show what will be done
    print("\nStandard imports to add:")
    for imp in STANDARD_IMPORTS:
        print(f"  {imp}")

    print(f"\nDeprecated patterns to migrate: {len(DEPRECATED_PATTERNS)} patterns")
    print(
        "Service method migrations: calculate_daily_* -> calculate(context, strategy)"
    )

    if dry_run:
        print("\n DRY RUN MODE - No files will be modified")
    else:
        print("\n⚡ LIVE MODE - Files will be modified")

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
        print(f"\n Backup files created with .service_bak extension")
        print(f"  Please review changes before committing!")
        print(f"  TODO comments added for manual review of method parameters!")

    print("\n Service imports codemod complete!")


if __name__ == "__main__":
    main()
