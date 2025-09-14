#!/usr/bin/env python3
"""
Static check script for legacy payroll imports.

This script scans the entire repository for legacy payroll service imports
and reports any violations outside of explicitly allowed locations.
"""

import os
import re
import sys
from pathlib import Path


# Patterns to detect legacy imports
LEGACY_PATTERNS = [re.compile(r'from\s+payroll\.services\s+import\s+.*PayrollCalculationService'),
    re.compile(r'from\s+payroll\.optimized_service\s+import'),
    re.compile(r'import\s+payroll\.optimized_service'),
    re.compile(r'from\s+payroll\.services\.adapters\s+import'),
]

# Allowed locations for legacy imports
ALLOWED_PATTERNS = [
    'tests/legacy/',
    'test_payroll_optimization.py',
    'archive/',
    'backup/',
    # Allow in services.py where legacy classes might be defined
    'payroll/services.py',
    'payroll/services/__init__.py',
    # Allow in check script itself (contains examples)
    'check_legacy_imports.py',
]


def is_allowed_location(filepath: str) -> bool:
    """Check if file is in an allowed location for legacy imports."""
    for pattern in ALLOWED_PATTERNS:
        if pattern in filepath:
            return True
    return False


def check_file_for_legacy_imports(filepath: Path) -> list:
    """Check a single file for legacy import patterns."""
    violations = []
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            
        for line_num, line in enumerate(content.splitlines(), 1):
            for pattern in LEGACY_PATTERNS:
                if pattern.search(line):
                    violations.append({
                        'file': str(filepath),
                        'line': line_num,
                        'content': line.strip(),
                        'pattern': pattern.pattern
                    })
                    
    except Exception as e:
        print(f"WARNING: Could not read {filepath}: {e}")
        
    return violations


def scan_repository(root_dir: Path) -> list:
    """Scan entire repository for legacy imports."""
    all_violations = []
    
    # Find all Python files
    python_files = list(root_dir.rglob('*.py'))
    
    print(f"Scanning {len(python_files)} Python files...")
    
    for py_file in python_files:
        # Skip virtual environment and cache directories
        if any(part in str(py_file) for part in ['.venv', 'venv', '__pycache__', '.git']):
            continue
            
        # Skip allowed locations
        if is_allowed_location(str(py_file)):
            print(f"  SKIPPING (allowed): {py_file}")
            continue
            
        violations = check_file_for_legacy_imports(py_file)
        all_violations.extend(violations)
        
    return all_violations


def main():
    """Main function to run legacy import check."""
    print("Static Legacy Import Check")
    print("=" * 50)
    
    # Get repository root
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    
    print(f"Repository root: {repo_root}")
    print()
    
    # Scan for violations
    violations = scan_repository(repo_root)
    
    if not violations:
        print("SUCCESS: No legacy import violations found!")
        print()
        print("All payroll code is using the new architecture:")
        print("  - PayrollService")
        print("  - CalculationContext") 
        print("  - CalculationStrategy.ENHANCED")
        return 0
    
    # Report violations
    print(f"ERROR: {len(violations)} legacy imports detected")
    print()
    
    for violation in violations:
        print(f"File: {violation['file']}")
        print(f"Line {violation['line']}: {violation['content']}")
        print(f"Pattern: {violation['pattern']}")
        print("-" * 40)
    
    print()
    print("SOLUTION:")
    print("Replace legacy imports with new architecture:")
    print()
    print("# Remove legacy imports:")
    print("# from payroll.services import PayrollCalculationService")
    print("# from payroll.optimized_service import ...")
    print()
    print("# Add new imports:")
    print("from payroll.services.payroll_service import PayrollService")
    print("from payroll.services.contracts import CalculationContext")
    print("from payroll.services.enums import CalculationStrategy, EmployeeType")
    print()
    print("# Update service usage:")
    print("service = PayrollService()")
    print("context = CalculationContext(...)")
    print("result = service.calculate(context, CalculationStrategy.ENHANCED)")
    
    return 1


if __name__ == '__main__':
    sys.exit(main())