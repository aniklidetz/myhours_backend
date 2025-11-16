#!/usr/bin/env python3
"""
Fix syntax errors introduced by Wave C regex replacement.

This script corrects malformed dictionary access patterns and assertions
that were incorrectly transformed by the automated regex replacement.
"""

import os
import re
import sys
from pathlib import Path


class SyntaxErrorFixer:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.fixes_applied = 0

    def fix_file(self, file_path):
        """Fix syntax errors in a single file"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            original_content = content

            # Fix pattern 1: result.get("regular_hours == Decimal("8.6")XX")
            # Should be: result.get("regular_hours", 0), Decimal("8.6")
            content = re.sub(
                r'result\.get\("regular_hours == Decimal\("8\.6"\)(\d+)"\)',
                r'result.get("regular_hours", 0), Decimal("8.6")',
                content,
            )

            # Fix pattern 2: float(result.get("regular_hours == Decimal("8.6")XX, places=1)
            # Should be: float(result.get("regular_hours", 0)), 8.6, places=1)
            content = re.sub(
                r'float\(result\.get\("regular_hours == Decimal\("8\.6"\)(\d+), places=1\)',
                r'float(result.get("regular_hours", 0)), 8.6, places=1)',
                content,
            )

            # Fix pattern 3: float(regular_hours == Decimal("8.6")XX, places=1)
            # Should be: float(regular_hours), 8.6, places=1)
            content = re.sub(
                r'float\(regular_hours == Decimal\("8\.6"\)(\d+), places=1\)',
                r"float(regular_hours), 8.6, places=1)",
                content,
            )

            # Fix pattern 4: regular_hours == Decimal("8.6")XX")
            # Should be: regular_hours, Decimal("8.6"))
            content = re.sub(
                r'regular_hours == Decimal\("8\.6"\)(\d+)"\)',
                r'regular_hours, Decimal("8.6"))',
                content,
            )

            # Fix pattern 5: Any standalone "regular_hours == Decimal("8.6")" that should be comparison
            # But preserve actual comparisons
            content = re.sub(
                r'self\.assertEqual\(\s*regular_hours == Decimal\("8\.6"\)(\d*)\s*\)',
                r'self.assertEqual(regular_hours, Decimal("8.6"))',
                content,
            )

            if content != original_content:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.fixes_applied += 1
                print(f"✓ Fixed syntax errors in: {file_path}")
                return True
            else:
                print(f"- No fixes needed in: {file_path}")
                return False

        except Exception as e:
            print(f"✗ Error fixing {file_path}: {e}")
            return False

    def find_affected_files(self):
        """Find all files with syntax errors from Wave C"""
        affected_files = []

        # Search for the specific syntax error patterns
        test_dirs = [
            self.project_root / "payroll" / "tests",
            self.project_root / "worktime" / "tests",
        ]

        for test_dir in test_dirs:
            if test_dir.exists():
                for py_file in test_dir.glob("test_*.py"):
                    try:
                        with open(py_file, "r", encoding="utf-8") as f:
                            content = f.read()

                        # Check for syntax error patterns
                        if re.search(r'regular_hours == Decimal\("8\.6"\)', content):
                            affected_files.append(py_file)

                    except Exception as e:
                        print(f"Warning: Could not read {py_file}: {e}")

        return affected_files

    def run(self):
        """Execute the syntax error fixes"""
        print(" Finding files with Wave C syntax errors...")

        affected_files = self.find_affected_files()

        if not affected_files:
            print(" No syntax errors found!")
            return True

        print(f" Found {len(affected_files)} files with syntax errors:")
        for file_path in affected_files:
            print(f"   - {file_path}")

        print("\n Applying fixes...")

        success_count = 0
        for file_path in affected_files:
            if self.fix_file(file_path):
                success_count += 1

        print(f"\n Fixed syntax errors in {success_count}/{len(affected_files)} files")

        if success_count == len(affected_files):
            print(" All syntax errors have been fixed!")
            return True
        else:
            print("  Some files could not be fixed - manual intervention may be needed")
            return False


def main():
    """Main entry point"""
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print(__doc__)
        print("\nUsage: python3 scripts/fix_wave_c_syntax.py")
        return

    print(" Wave C Syntax Error Fixer")
    print("=" * 40)

    fixer = SyntaxErrorFixer()
    success = fixer.run()

    if success:
        print("\n Next step: Execute Wave D to complete the refactoring:")
        print("   python3 scripts/refactor_tests.py --wave D --dry-run")
        print("   python3 scripts/refactor_tests.py --wave D")
        sys.exit(0)
    else:
        print("\n  Manual review needed before proceeding to Wave D")
        sys.exit(1)


if __name__ == "__main__":
    main()
