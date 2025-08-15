#!/usr/bin/env python
"""
Test that only simple notification system remains
"""
import os
import sys

import django

# Django setup
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myhours.settings")
django.setup()


def test_clean_architecture():
    """Test that complex notification system was removed"""
    print("🧹 TESTING CLEAN NOTIFICATION ARCHITECTURE")
    print("=" * 80)

    # 1. Test that complex models don't exist
    print("\n1️⃣ Testing that complex notification models are removed...")
    try:
        from notifications.models import Notification

        print("❌ FAIL: Complex Notification model still exists!")
        return False
    except ImportError:
        print("✅ PASS: Complex notification models removed")

    # 2. Test that simple notifications work
    print("\n2️⃣ Testing that simple notification system works...")
    try:
        from users.models import Employee
        from worktime.simple_notifications import SimpleNotificationService

        # Test with first employee
        employee = Employee.objects.first()
        if employee:
            # This should not raise any errors
            print(f"   Testing with employee: {employee.get_full_name()}")

            # Test holiday notification
            SimpleNotificationService.notify_holiday_work(employee, "Test Holiday")
            print("✅ PASS: Simple notification system works")
        else:
            print("⚠️  SKIP: No employees to test with")

    except Exception as e:
        print(f"❌ FAIL: Simple notification system error: {e}")
        return False

    # 3. Test that no complex imports remain
    print("\n3️⃣ Testing for leftover complex imports...")
    try:
        # These should fail
        from notifications.services import NotificationService

        print("❌ FAIL: Complex NotificationService still exists!")
        return False
    except ImportError:
        print("✅ PASS: Complex services removed")

    # 4. Test file structure
    print("\n4️⃣ Testing file structure...")
    import glob

    # Should not exist
    notification_files = glob.glob("**/notifications/**", recursive=True)
    if notification_files:
        print(f"❌ FAIL: Complex notification files still exist: {notification_files}")
        return False
    else:
        print("✅ PASS: Complex notification directory removed")

    # Should exist
    simple_files = ["worktime/simple_notifications.py", "worktime/simple_signals.py"]

    for file_path in simple_files:
        if os.path.exists(file_path):
            print(f"✅ PASS: {file_path} exists")
        else:
            print(f"❌ FAIL: {file_path} missing")
            return False

    print("\n" + "=" * 80)
    print("🎉 SUCCESS: Clean notification architecture verified!")
    print("\n📋 WHAT REMAINS:")
    print("• worktime/simple_notifications.py - Simple push notifications")
    print("• worktime/simple_signals.py - Auto-trigger on WorkLog save")
    print("• demo_simple_notifications.py - Demo script")
    print("• simple_notification_guide.md - Documentation")

    print("\n🗑️ WHAT WAS REMOVED:")
    print("• notifications/ directory - Complex notification models")
    print("• labor_law_validator.py - Complex validation")
    print("• Old signal files - Complex automation")
    print("• Management commands - Complex CLI tools")
    print("• Demo files - Old complex demos")

    return True


if __name__ == "__main__":
    success = test_clean_architecture()
    sys.exit(0 if success else 1)
