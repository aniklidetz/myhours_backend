#!/usr/bin/env python
"""
Run enhanced payroll service tests to check if they pass.
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings_ci')
django.setup()

# Now we can import and run tests
from django.test import TestCase
from django.test.utils import setup_test_environment, teardown_test_environment
from django.db import connection
from django.test.runner import DiscoverRunner

def run_tests():
    """Run specific test class."""
    print("=== Running Enhanced Payroll Service Tests ===\n")

    # Setup test environment
    runner = DiscoverRunner(verbosity=2, interactive=False, keepdb=False)
    runner.setup_test_environment()

    # Create test database
    old_config = runner.setup_databases()

    try:
        # Import the test class
        from payroll.tests.test_enhanced_payroll_service_core import EnhancedPayrollServiceCoreRefactor

        # Get all test methods
        test_methods = [method for method in dir(EnhancedPayrollServiceCoreRefactor)
                       if method.startswith('test_')]

        print(f"Found {len(test_methods)} test methods\n")

        results = {
            'passed': [],
            'failed': [],
            'errors': []
        }

        for test_name in test_methods:
            print(f"Running {test_name}...", end=" ")

            try:
                # Create test instance
                test_suite = EnhancedPayrollServiceCoreRefactor(test_name)
                test_suite._testMethodDoc = None  # Prevent doc string issues

                # Run setUp
                test_suite.setUp()

                # Run the test
                test_method = getattr(test_suite, test_name)
                test_method()

                # Run tearDown
                test_suite.tearDown()

                print("✅ PASSED")
                results['passed'].append(test_name)

            except AssertionError as e:
                print(f"❌ FAILED: {str(e)[:100]}")
                results['failed'].append((test_name, str(e)))

            except Exception as e:
                print(f"💥 ERROR: {str(e)[:100]}")
                results['errors'].append((test_name, str(e)))

        # Print summary
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        print(f"✅ Passed: {len(results['passed'])}")
        print(f"❌ Failed: {len(results['failed'])}")
        print(f"💥 Errors: {len(results['errors'])}")

        if results['failed']:
            print("\n❌ FAILED TESTS:")
            for test_name, error in results['failed']:
                print(f"  - {test_name}")
                print(f"    Error: {error[:200]}")

        if results['errors']:
            print("\n💥 ERROR TESTS:")
            for test_name, error in results['errors']:
                print(f"  - {test_name}")
                print(f"    Error: {error[:200]}")

        return results

    finally:
        # Cleanup
        runner.teardown_databases(old_config)
        teardown_test_environment()

if __name__ == '__main__':
    try:
        results = run_tests()
        # Exit with error code if any tests failed
        if results['failed'] or results['errors']:
            sys.exit(1)
    except Exception as e:
        print(f"\n💥 Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)