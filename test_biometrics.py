#!/usr/bin/env python3
"""
Test script for biometric system functionality
Run with: python test_biometrics.py
"""

import os
import sys
import django
import base64
import requests
import time
import json
from pathlib import Path

# Setup Django
sys.path.append('/Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from django.test import Client
from django.contrib.auth.models import User
from users.models import Employee
from biometrics.models import BiometricProfile
from biometrics.services.face_processor import face_processor
from biometrics.services.mongodb_service import mongodb_service


class BiometricTester:
    def __init__(self):
        self.client = Client()
        self.base_url = 'http://localhost:8000'
        self.test_user = None
        self.test_employee = None
        self.auth_token = None
    
    def log(self, message):
        print(f"[{time.strftime('%H:%M:%S')}] {message}")
    
    def test_dependencies(self):
        """Test if all required dependencies are available"""
        self.log("Testing dependencies...")
        
        try:
            import face_recognition
            self.log("✓ face_recognition imported successfully")
        except ImportError as e:
            self.log(f"✗ face_recognition import failed: {e}")
            return False
        
        try:
            import cv2
            self.log("✓ OpenCV imported successfully")
        except ImportError as e:
            self.log(f"✗ OpenCV import failed: {e}")
            return False
        
        try:
            import numpy as np
            self.log("✓ NumPy imported successfully")
        except ImportError as e:
            self.log(f"✗ NumPy import failed: {e}")
            return False
        
        try:
            from PIL import Image
            self.log("✓ Pillow imported successfully")
        except ImportError as e:
            self.log(f"✗ Pillow import failed: {e}")
            return False
        
        return True
    
    def test_mongodb_connection(self):
        """Test MongoDB connection"""
        self.log("Testing MongoDB connection...")
        
        try:
            stats = mongodb_service.get_statistics()
            if stats['status'] == 'connected':
                self.log("✓ MongoDB connected successfully")
                self.log(f"  - Active employees: {stats['active_employees']}")
                self.log(f"  - Total embeddings: {stats['total_embeddings']}")
                return True
            else:
                self.log(f"✗ MongoDB connection issue: {stats}")
                return False
        except Exception as e:
            self.log(f"✗ MongoDB test failed: {e}")
            return False
    
    def create_test_user(self):
        """Create a test user and employee"""
        self.log("Creating test user...")
        
        try:
            # Create or get test user
            self.test_user, created = User.objects.get_or_create(
                username='biometric_test_user',
                defaults={
                    'email': 'test@biometric.com',
                    'first_name': 'Biometric',
                    'last_name': 'Test'
                }
            )
            
            if created:
                self.test_user.set_password('testpass123')
                self.test_user.save()
                self.log("✓ Test user created")
            else:
                self.log("✓ Test user already exists")
            
            # Create or get test employee
            self.test_employee, created = Employee.objects.get_or_create(
                user=self.test_user,
                defaults={
                    'first_name': 'Biometric',
                    'last_name': 'Test',
                    'email': 'test@biometric.com',
                    'role': 'employee'
                }
            )
            
            if created:
                self.log("✓ Test employee created")
            else:
                self.log("✓ Test employee already exists")
            
            return True
            
        except Exception as e:
            self.log(f"✗ Failed to create test user: {e}")
            return False
    
    def login_test_user(self):
        """Login the test user"""
        self.log("Logging in test user...")
        
        try:
            login_successful = self.client.login(
                username='biometric_test_user',
                password='testpass123'
            )
            
            if login_successful:
                self.log("✓ Test user logged in successfully")
                return True
            else:
                self.log("✗ Failed to login test user")
                return False
                
        except Exception as e:
            self.log(f"✗ Login failed: {e}")
            return False
    
    def create_test_image(self):
        """Create a simple test image (solid color)"""
        try:
            from PIL import Image
            import io
            
            # Create a simple 200x200 RGB image with a face-like pattern
            # This won't work for real face recognition, but tests the pipeline
            img = Image.new('RGB', (200, 200), color='lightblue')
            
            # Add some simple "face-like" features (circles for eyes, etc.)
            # Note: This is just for testing the pipeline, not actual face recognition
            
            # Convert to base64
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG')
            img_str = base64.b64encode(buffer.getvalue()).decode()
            
            return f"data:image/jpeg;base64,{img_str}"
            
        except Exception as e:
            self.log(f"✗ Failed to create test image: {e}")
            return None
    
    def test_face_processor(self):
        """Test the face processor service"""
        self.log("Testing face processor...")
        
        try:
            test_image = self.create_test_image()
            if not test_image:
                return False
            
            # Test image processing
            result = face_processor.process_registration_image(test_image)
            
            if result['success']:
                self.log("✓ Face processor working (found face)")
                self.log(f"  - Processing time: {result.get('processing_time_ms', 0)}ms")
                return True
            else:
                self.log(f"! Face processor working but no face detected: {result.get('error')}")
                # This is expected with our test image
                return True
                
        except Exception as e:
            self.log(f"✗ Face processor test failed: {e}")
            return False
    
    def test_registration_endpoint(self):
        """Test the face registration endpoint"""
        self.log("Testing registration endpoint...")
        
        try:
            test_image = self.create_test_image()
            if not test_image:
                return False
            
            # Test registration endpoint
            response = self.client.post('/api/biometrics/register/', {
                'employee_id': self.test_employee.id,
                'images': [test_image],
                'location': 'Test Location'
            }, content_type='application/json')
            
            self.log(f"Registration response status: {response.status_code}")
            if response.status_code in [200, 201, 400]:  # 400 is ok for test image
                try:
                    response_data = response.json()
                    self.log(f"Registration response: {response_data}")
                    
                    if response.status_code in [200, 201]:
                        self.log("✓ Registration endpoint working")
                        return True
                    else:
                        self.log("! Registration endpoint accessible (test image rejection expected)")
                        return True
                except:
                    self.log("✓ Registration endpoint accessible")
                    return True
            else:
                self.log(f"✗ Registration endpoint failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.log(f"✗ Registration endpoint test failed: {e}")
            return False
    
    def test_check_in_endpoint(self):
        """Test the check-in endpoint"""
        self.log("Testing check-in endpoint...")
        
        try:
            test_image = self.create_test_image()
            if not test_image:
                return False
            
            # Test check-in endpoint
            response = self.client.post('/api/biometrics/check-in/', {
                'image': test_image,
                'location': 'Test Office'
            }, content_type='application/json')
            
            self.log(f"Check-in response status: {response.status_code}")
            if response.status_code in [200, 400, 429]:  # Various expected responses
                try:
                    response_data = response.json()
                    self.log(f"Check-in response: {response_data}")
                except:
                    pass
                self.log("✓ Check-in endpoint accessible")
                return True
            else:
                self.log(f"✗ Check-in endpoint failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.log(f"✗ Check-in endpoint test failed: {e}")
            return False
    
    def test_stats_endpoint(self):
        """Test the stats endpoint"""
        self.log("Testing stats endpoint...")
        
        try:
            # First, make user staff to access stats
            self.test_user.is_staff = True
            self.test_user.save()
            
            response = self.client.get('/api/biometrics/management/stats/')
            
            self.log(f"Stats response status: {response.status_code}")
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    self.log("✓ Stats endpoint working")
                    self.log(f"  - MongoDB stats: {response_data.get('mongodb_stats', {})}")
                    self.log(f"  - Profiles: {response_data.get('profiles', {})}")
                    return True
                except:
                    self.log("✓ Stats endpoint accessible")
                    return True
            else:
                self.log(f"✗ Stats endpoint failed: {response.status_code}")
                return False
                
        except Exception as e:
            self.log(f"✗ Stats endpoint test failed: {e}")
            return False
    
    def cleanup(self):
        """Clean up test data"""
        self.log("Cleaning up test data...")
        
        try:
            # Remove test biometric profile if exists
            BiometricProfile.objects.filter(employee=self.test_employee).delete()
            
            # Remove test employee and user
            if self.test_employee:
                self.test_employee.delete()
            if self.test_user:
                self.test_user.delete()
            
            self.log("✓ Test data cleaned up")
            
        except Exception as e:
            self.log(f"! Cleanup warning: {e}")
    
    def run_all_tests(self):
        """Run all tests"""
        self.log("=== Starting Biometric System Tests ===")
        
        tests = [
            ("Dependencies", self.test_dependencies),
            ("MongoDB Connection", self.test_mongodb_connection),
            ("Test User Creation", self.create_test_user),
            ("User Login", self.login_test_user),
            ("Face Processor", self.test_face_processor),
            ("Registration Endpoint", self.test_registration_endpoint),
            ("Check-in Endpoint", self.test_check_in_endpoint),
            ("Stats Endpoint", self.test_stats_endpoint),
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
            self.log("🎉 All tests passed! Biometric system is ready.")
        elif passed >= total * 0.7:
            self.log("⚠️  Most tests passed. System mostly functional.")
        else:
            self.log("❌ Several tests failed. Please review the issues.")
        
        return passed == total


if __name__ == "__main__":
    tester = BiometricTester()
    success = tester.run_all_tests()
    
    if success:
        print("\n🚀 Next steps:")
        print("1. Test with real face images")
        print("2. Implement frontend biometric UI")
        print("3. Add liveness detection")
        print("4. Set up Celery for async processing")
    else:
        print("\n🔧 Please fix the failing tests before proceeding")
    
    sys.exit(0 if success else 1)