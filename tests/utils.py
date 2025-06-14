"""Testing utilities"""

import os
import sys
from django.test.utils import get_runner
from django.conf import settings


def run_tests_with_coverage():
    """Run tests with coverage"""
    import coverage
    
    cov = coverage.Coverage()
    cov.start()
    
    # Run tests
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(['tests', 'users', 'worktime', 'payroll', 'biometrics', 'integrations'])
    
    cov.stop()
    cov.save()
    
    # Generate report
    print("\n\nCoverage Report:")
    cov.report()
    
    return failures == 0


if __name__ == '__main__':
    run_tests_with_coverage()
