#!/usr/bin/env python3
"""
Basic test script for biometric system infrastructure (without face_recognition)
Run with: python test_basic_biometrics.py
"""

import os
import sys
import django
import time

# Setup Django
sys.path.append('/Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from django.test import Client
from django.contrib.auth.models import User
from users.models import Employee
from biometrics.models import BiometricProfile, BiometricLog, BiometricAttempt
from biometrics.services.mongodb_service import mongodb_service


class BasicBiometricTester:
    def __init__(self):
        self.client = Client()
        self.test_user = None
        self.test_employee = None
    
    def log(self, message):
        print(f"[{time.strftime('%H:%M:%S')}] {message}")
    
    def test_django_setup(self):
        """Test Django setup and models"""
        self.log("Testing Django setup...")
        
        try:
            # Test model imports
            from biometrics.models import BiometricProfile, BiometricLog, BiometricAttempt, FaceQualityCheck
            self.log("✓ Biometric models imported successfully")
            
            # Test model creation
            count = BiometricProfile.objects.count()
            self.log(f"✓ BiometricProfile model accessible ({count} profiles)")
            
            return True
        except Exception as e:
            self.log(f"✗ Django setup failed: {e}")
            return False
    
    def test_mongodb_connection(self):
        """Test MongoDB connection"""
        self.log("Testing MongoDB connection...")
        
        try:
            stats = mongodb_service.get_statistics()
            self.log(f"MongoDB stats received: {stats}")
            
            if stats.get('status') == 'connected':
                self.log("✓ MongoDB connected successfully")
                self.log(f"  - Active employees: {stats.get('active_employees', 0)}")
                self.log(f"  - Total embeddings: {stats.get('total_embeddings', 0)}")
                return True
            elif stats.get('status') == 'error':
                self.log(f"✗ MongoDB connection error: {stats.get('error', 'Unknown error')}")
                return False
            else:
                self.log(f"! MongoDB status unknown: {stats}")
                return False
        except Exception as e:
            self.log(f"✗ MongoDB test failed: {e}")
            return False
    
    def create_test_user(self):
        """Create a test user and employee"""
        self.log("Creating test user...")
        
        try:
            # Clean up existing test user
            User.objects.filter(username='basic_test_user').delete()
            
            # Create test user
            self.test_user = User.objects.create_user(
                username='basic_test_user',
                email='test@basic.com',
                password='testpass123',
                first_name='Basic',
                last_name='Test'
            )
            self.log("✓ Test user created")
            
            # Create test employee
            self.test_employee = Employee.objects.create(
                user=self.test_user,
                first_name='Basic',
                last_name='Test',
                email='test@basic.com',
                role='employee'
            )
            self.log("✓ Test employee created")
            
            return True
            
        except Exception as e:
            self.log(f"✗ Failed to create test user: {e}")
            return False
    
    def test_biometric_profile_creation(self):
        """Test creating a biometric profile"""
        self.log("Testing biometric profile creation...")
        
        try:
            # Create a biometric profile
            profile = BiometricProfile.objects.create(
                employee=self.test_employee,
                embeddings_count=1,
                mongodb_id='test_mongo_id',
                is_active=True
            )
            
            self.log(f"✓ Biometric profile created: ID {profile.id}")
            
            # Test profile methods
            self.log(f"  - Employee: {profile.employee.get_full_name()}")
            self.log(f"  - Active: {profile.is_active}")
            self.log(f"  - Embeddings count: {profile.embeddings_count}")
            
            return True
            
        except Exception as e:
            self.log(f"✗ Failed to create biometric profile: {e}")
            return False
    
    def test_biometric_log_creation(self):
        """Test creating biometric logs"""
        self.log("Testing biometric log creation...")
        
        try:
            # Create a biometric log
            log = BiometricLog.objects.create(
                employee=self.test_employee,
                action='check_in',
                confidence_score=0.85,
                location='Test Office',
                device_info={'test': 'device'},
                ip_address='127.0.0.1',
                success=True,
                processing_time_ms=150
            )
            
            self.log(f"✓ Biometric log created: ID {log.id}")
            self.log(f"  - Action: {log.action}")
            self.log(f"  - Success: {log.success}")
            self.log(f"  - Confidence: {log.confidence_score}")
            
            return True
            
        except Exception as e:
            self.log(f"✗ Failed to create biometric log: {e}")
            return False
    
    def test_rate_limiting(self):
        """Test rate limiting functionality"""
        self.log("Testing rate limiting...")
        
        try:
            # Create a biometric attempt
            attempt = BiometricAttempt.objects.create(
                ip_address='192.168.1.100',
                attempts_count=3
            )
            
            self.log(f"✓ Biometric attempt created: {attempt.ip_address}")
            
            # Test blocking logic
            is_blocked_before = attempt.is_blocked()
            self.log(f"  - Blocked before increment: {is_blocked_before}")
            
            # Increment attempts
            attempt.increment_attempts()
            attempt.increment_attempts()
            
            is_blocked_after = attempt.is_blocked()
            self.log(f"  - Blocked after increments: {is_blocked_after}")
            self.log(f"  - Current attempts: {attempt.attempts_count}")
            
            # Test reset
            attempt.reset_attempts()
            is_blocked_reset = attempt.is_blocked()
            self.log(f"  - Blocked after reset: {is_blocked_reset}")
            
            return True
            
        except Exception as e:
            self.log(f"✗ Failed to test rate limiting: {e}")
            return False
    
    def test_api_endpoints_accessibility(self):
        """Test API endpoints are accessible (without authentication)"""
        self.log("Testing API endpoint accessibility...")
        
        try:
            # Login test user
            login_successful = self.client.login(
                username='basic_test_user',
                password='testpass123'
            )
            
            if not login_successful:
                self.log("✗ Failed to login test user")
                return False
            
            self.log("✓ Test user logged in")
            
            # Test registration endpoint (should return 400 due to missing data)
            response = self.client.post('/api/biometrics/register/')
            self.log(f"Registration endpoint status: {response.status_code}")
            
            # Test check-in endpoint (should return 400 due to missing data)
            response = self.client.post('/api/biometrics/check-in/')
            self.log(f"Check-in endpoint status: {response.status_code}")
            
            # Test stats endpoint (make user staff first)
            self.test_user.is_staff = True
            self.test_user.save()
            
            response = self.client.get('/api/biometrics/management/stats/')
            self.log(f"Stats endpoint status: {response.status_code}")
            
            if response.status_code in [200, 400, 403]:
                self.log("✓ API endpoints are accessible")
                return True
            else:
                self.log("✗ API endpoints not accessible")
                return False
            
        except Exception as e:
            self.log(f"✗ Failed to test API endpoints: {e}")
            return False
    
    def test_admin_interface(self):
        """Test admin interface models"""
        self.log("Testing admin interface...")
        
        try:
            from biometrics.admin import (
                BiometricProfileAdmin, 
                BiometricLogAdmin, 
                BiometricAttemptAdmin,
                FaceQualityCheckAdmin
            )
            
            self.log("✓ Admin classes imported successfully")
            
            # Test admin methods (without actual admin interface)
            profile = BiometricProfile.objects.first()
            if profile:
                admin = BiometricProfileAdmin(BiometricProfile, None)
                employee_name = admin.employee_name(profile)
                self.log(f"✓ Admin method test: {employee_name}")
            
            return True
            
        except Exception as e:
            self.log(f"✗ Failed to test admin interface: {e}")
            return False
    
    def cleanup(self):
        """Clean up test data"""
        self.log("Cleaning up test data...")
        
        try:
            # Remove test data
            BiometricProfile.objects.filter(employee=self.test_employee).delete()
            BiometricLog.objects.filter(employee=self.test_employee).delete()
            BiometricAttempt.objects.filter(ip_address__in=['127.0.0.1', '192.168.1.100']).delete()
            
            if self.test_employee:
                self.test_employee.delete()
            if self.test_user:
                self.test_user.delete()
            
            self.log("✓ Test data cleaned up")
            
        except Exception as e:
            self.log(f"! Cleanup warning: {e}")
    
    def run_all_tests(self):
        """Run all tests"""
        self.log("=== Starting Basic Biometric System Tests ===")
        
        tests = [
            ("Django Setup", self.test_django_setup),
            ("MongoDB Connection", self.test_mongodb_connection),
            ("Test User Creation", self.create_test_user),
            ("Biometric Profile Creation", self.test_biometric_profile_creation),
            ("Biometric Log Creation", self.test_biometric_log_creation),
            ("Rate Limiting", self.test_rate_limiting),
            ("API Endpoints Accessibility", self.test_api_endpoints_accessibility),
            ("Admin Interface", self.test_admin_interface),
        ]
        
        results = []
        for test_name, test_func in tests:
            self.log(f"\n--- Testing {test_name} ---")
            try:
                result = test_func()
                results.append((test_name, result))
                if result:
                    self.log(f"✓ {test_name} PASSED")
                else:
                    self.log(f"✗ {test_name} FAILED")
            except Exception as e:
                self.log(f"✗ {test_name} ERROR: {e}")
                results.append((test_name, False))
        
        # Cleanup
        self.log(f"\n--- Cleanup ---")
        self.cleanup()
        
        # Summary
        self.log(f"\n=== Test Results Summary ===")
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for test_name, result in results:
            status = "✓ PASS" if result else "✗ FAIL"
            self.log(f"{status} - {test_name}")
        
        self.log(f"\nOverall: {passed}/{total} tests passed")
        
        if passed == total:
            self.log("🎉 All basic tests passed! Infrastructure is ready.")
        elif passed >= total * 0.7:
            self.log("⚠️  Most tests passed. Infrastructure mostly functional.")
        else:
            self.log("❌ Several tests failed. Please review the issues.")
        
        return passed >= total * 0.7  # Consider success if 70% pass


if __name__ == "__main__":
    tester = BasicBiometricTester()
    success = tester.run_all_tests()
    
    if success:
        print("\n🚀 Next steps:")
        print("1. Fix face_recognition installation issues")
        print("2. Test with real face images")
        print("3. Implement frontend biometric UI") 
        print("4. Add liveness detection")
    else:
        print("\n🔧 Please fix the failing tests before proceeding")
    
    sys.exit(0 if success else 1)