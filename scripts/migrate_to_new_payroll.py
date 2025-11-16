#!/usr/bin/env python
"""
Migration script for Wave C: Import sweep
Replaces legacy imports with new PayrollService architecture
"""

import os
import re
from pathlib import Path


def migrate_imports(content):
    """Replace legacy imports with new architecture imports"""

    # Replace legacy service imports
    content = re.sub(
        r"from payroll\.services import EnhancedPayrollCalculationService",
        "from payroll.services.payroll_service import PayrollService\nfrom payroll.services.enums import CalculationStrategy",
        content,
    )

    content = re.sub(
        r"from payroll\.services import PayrollCalculationService",
        "from payroll.services.payroll_service import PayrollService\nfrom payroll.services.enums import CalculationStrategy",
        content,
    )

    # Add CalculationContext import if PayrollService is used
    if "PayrollService" in content and "CalculationContext" not in content:
        # Find the right place to add the import
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "from payroll.services.payroll_service import PayrollService" in line:
                # Check if next line already has the import
                if i + 1 < len(lines) and "CalculationContext" not in lines[i + 1]:
                    lines.insert(
                        i + 1,
                        "from payroll.services.contracts import CalculationContext",
                    )
                break
        content = "\n".join(lines)

    return content


def migrate_service_instantiation(content):
    """Replace legacy service instantiation with new pattern"""

    # Pattern for EnhancedPayrollCalculationService instantiation
    pattern = r"(\s+)service = EnhancedPayrollCalculationService\((.*?)\)"

    def replacement(match):
        indent = match.group(1)
        params = match.group(2)

        # Extract parameters
        param_mapping = {
            "employee": "employee_id=employee.id",
            "year": "year=year",
            "month": "month=month",
            "fast_mode": "fast_mode=fast_mode",
        }

        new_lines = [
            f"{indent}context = CalculationContext(",
            f"{indent}    employee_id=employee.id,",
            f"{indent}    year=year,",
            f"{indent}    month=month,",
            f"{indent}    user_id=1,",
            f"{indent}    fast_mode=False",
            f"{indent})",
            f"{indent}service = PayrollService()",
        ]

        return "\n".join(new_lines)

    content = re.sub(pattern, replacement, content)

    return content


def migrate_field_names(content):
    """Replace old field names with new ones"""

    replacements = [
        ("total_gross_pay", "total_salary"),
        ("regular_pay", "base_regular_pay"),
        ("overtime_pay_1", "bonus_overtime_pay_1"),
        ("overtime_pay_2", "bonus_overtime_pay_2"),
        ("sabbath_overtime_pay_1", "bonus_sabbath_overtime_pay_1"),
        ("sabbath_overtime_pay_2", "bonus_sabbath_overtime_pay_2"),
    ]

    for old, new in replacements:
        # Replace in dictionary access
        content = re.sub(f'\\["{old}"\\]', f'["{new}"]', content)
        content = re.sub(f"\\['{old}'\\]", f"['{new}']", content)
        # Replace in dot notation
        content = re.sub(f"\\.{old}(?![a-zA-Z_])", f".{new}", content)
        # Replace in assertions
        content = re.sub(f'"{old}"', f'"{new}"', content)
        content = re.sub(f"'{old}'", f"'{new}'", content)

    return content


def process_file(filepath):
    """Process a single test file"""

    with open(filepath, "r") as f:
        content = f.read()

    original = content

    # Apply migrations
    content = migrate_imports(content)
    content = migrate_service_instantiation(content)
    content = migrate_field_names(content)

    if content != original:
        with open(filepath, "w") as f:
            f.write(content)
        return True
    return False


def main():
    """Main migration function"""

    test_dir = Path("payroll/tests")
    files_to_migrate = [
        "test_enhanced_payroll_service_core.py",
        "test_monthly_employee_calculations.py",
        "test_sabbath_calculations.py",
        "test_salary_active_constraint.py",
        "test_management_commands_e2e_comprehensive.py",
    ]

    migrated = []

    for filename in files_to_migrate:
        filepath = test_dir / filename
        if filepath.exists():
            if process_file(filepath):
                migrated.append(filename)
                print(f"✓ Migrated {filename}")
            else:
                print(f"  No changes needed for {filename}")
        else:
            print(f"✗ File not found: {filename}")

    print(f"\n{'='*50}")
    print(f"Migration complete: {len(migrated)} files updated")
    print(f"{'='*50}")

    if migrated:
        print("\nUpdated files:")
        for filename in migrated:
            print(f"  - {filename}")


if __name__ == "__main__":
    main()
