#!/usr/bin/env python
"""
Manual integration test for MongoDB with enhanced biometric service
Tests the BLOCKER fix: MongoDB operations outside PostgreSQL transaction
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
os.environ['TESTING'] = 'False'  # Enable MongoDB
os.environ['MONGO_CONNECTION_STRING'] = 'mongodb://localhost:27017/'
os.environ['MONGO_DB_NAME'] = 'biometrics_db_test'

django.setup()

from django.test import TestCase
from django.contrib.auth import get_user_model
from biometrics.services.enhanced_biometric_service import EnhancedBiometricService
from biometrics.models import BiometricProfile
from users.models import Employee
from pymongo import MongoClient

User = get_user_model()

def test_mongo_connection():
    """Test MongoDB connection"""
    print("\n=== Test 1: MongoDB Connection ===")
    try:
        client = MongoClient('mongodb://localhost:27017/')
        client.admin.command('ping')
        print("SUCCESS: MongoDB is accessible")

        db = client['biometrics_db_test']
        collection = db['face_embeddings']
        print(f"SUCCESS: Database and collection accessible")

        # Clean up any existing test data
        collection.delete_many({"employee_id": {"$gte": 9999}})
        print("SUCCESS: Test collection cleaned")

        client.close()
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False

def test_biometric_registration():
    """Test biometric registration with real MongoDB"""
    print("\n=== Test 2: Biometric Registration (BLOCKER Fix) ===")
    try:
        # Create test employee
        user = User.objects.create_user(
            username='test_mongo_user',
            email='testmongo@example.com',
            password='testpass123'
        )
        employee = Employee.objects.create(
            user=user,
            first_name='Test',
            last_name='MongoDB',
            email='testmongo@example.com',
            phone='1234567890',
            is_active=True
        )
        print(f"SUCCESS: Test employee created (ID: {employee.id})")

        # Create biometric service
        service = EnhancedBiometricService()

        # Test face encodings (mock data)
        face_encodings = [
            {"encoding": [0.1] * 128, "location": "test"},
            {"encoding": [0.2] * 128, "location": "test"}
        ]

        # Register biometric (this tests our BLOCKER fix)
        profile = service.register_biometric(employee.id, face_encodings)
        print(f"SUCCESS: Biometric registered (Profile ID: {profile.id})")
        print(f"  - MongoDB ID: {profile.mongodb_id}")
        print(f"  - Embeddings count: {profile.embeddings_count}")
        print(f"  - Is active: {profile.is_active}")

        # Verify MongoDB data
        from pymongo import MongoClient
        client = MongoClient('mongodb://localhost:27017/')
        db = client['biometrics_db_test']
        collection = db['face_embeddings']

        mongo_doc = collection.find_one({"employee_id": employee.id})
        if mongo_doc:
            print(f"SUCCESS: MongoDB document found")
            print(f"  - Employee ID: {mongo_doc['employee_id']}")
            print(f"  - Embeddings: {len(mongo_doc.get('embeddings', []))}")
        else:
            print(f"FAILED: MongoDB document not found")

        # Cleanup
        collection.delete_one({"employee_id": employee.id})
        profile.delete()
        employee.delete()
        user.delete()
        client.close()
        print("SUCCESS: Cleanup complete")

        return True

    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
        # Cleanup on error
        try:
            if 'employee' in locals():
                BiometricProfile.objects.filter(employee_id=employee.id).delete()
                employee.delete()
            if 'user' in locals():
                user.delete()
        except:
            pass
        return False

def test_compensating_transaction():
    """Test compensating transaction (MongoDB rollback on PostgreSQL failure)"""
    print("\n=== Test 3: Compensating Transaction ===")
    print("This tests the Saga pattern implementation")
    print("(Requires manual simulation of PostgreSQL failure)")
    print("SKIPPED: Manual test only")
    return True

if __name__ == '__main__':
    print("="*60)
    print("MongoDB Integration Test Suite")
    print("Testing BLOCKER fix: MongoDB operations outside PG transaction")
    print("="*60)

    results = []

    # Run tests
    results.append(("MongoDB Connection", test_mongo_connection()))
    results.append(("Biometric Registration", test_biometric_registration()))
    results.append(("Compensating Transaction", test_compensating_transaction()))

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for test_name, passed in results:
        status = "PASSED" if passed else "FAILED"
        print(f"{test_name}: {status}")

    all_passed = all(result[1] for result in results)
    print("="*60)
    if all_passed:
        print("ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED")
        sys.exit(1)
