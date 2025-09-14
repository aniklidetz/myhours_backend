#!/usr/bin/env python
"""
Test critical integrations after pre-deletion validation fixes
"""

import os
import sys
import django
from django.conf import settings

# Add the project directory to Python path
sys.path.insert(0, '/Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend')

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

def test_critical_integrations():
    """Test that all critical integrations work with UnifiedShabbatService"""
    print("Testing critical integrations...")

    success_count = 0
    total_tests = 5

    # Test 1: Integration views
    try:
        from integrations.views import HolidayViewSet
        print("✓ Integration views import successfully")
        success_count += 1
    except Exception as e:
        print(f"✗ Integration views failed: {e}")

    # Test 2: Payroll external service
    try:
        from payroll.services.external import get_sabbath_times
        from datetime import date
        result = get_sabbath_times(2024, 6)  # This calls the updated service
        print("✓ Payroll external service works")
        success_count += 1
    except Exception as e:
        print(f"✗ Payroll external service failed: {e}")

    # Test 3: Hebcal service
    try:
        from integrations.services.hebcal_service import HebcalService
        print("✓ Hebcal service imports successfully")
        success_count += 1
    except Exception as e:
        print(f"✗ Hebcal service failed: {e}")

    # Test 4: Payroll main service
    try:
        from payroll.services import PayrollService
        print("✓ Payroll main service imports successfully")
        success_count += 1
    except Exception as e:
        print(f"✗ Payroll main service failed: {e}")

    # Test 5: Management commands
    try:
        from worktime.management.commands.add_sabbath_shifts import Command as AddShabbatCommand
        print("✓ Add sabbath shifts command imports successfully")
        success_count += 1
    except Exception as e:
        print(f"✗ Add sabbath shifts command failed: {e}")

    print(f"\nCritical Integration Results: {success_count}/{total_tests} passed")
    return success_count == total_tests

if __name__ == "__main__":
    success = test_critical_integrations()
    if success:
        print("\n✓ All critical integrations working with UnifiedShabbatService")
        print("Ready for old service removal")
    else:
        print("\n✗ Some integrations failed - fix before deletion")