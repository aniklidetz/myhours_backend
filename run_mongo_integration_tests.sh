#!/bin/bash
# Script to run MongoDB integration tests with real MongoDB instance

echo "=== Running MongoDB Integration Tests ==="
echo "MongoDB connection: mongodb://localhost:27017/"
echo "Database: biometrics_db"
echo ""

# Set environment variables for MongoDB
export MONGO_CONNECTION_STRING="mongodb://localhost:27017/"
export MONGO_DB_NAME="biometrics_db"
export MONGO_HOST="localhost"
export MONGO_PORT=27017
export TESTING=False  # Enable MongoDB for these tests

# Run the specific tests that were skipped
echo "Running biometric authentication tests..."
python manage.py test \
  biometrics.tests.test_biometric_authentication.BiometricRegistrationTest.test_successful_biometric_registration \
  biometrics.tests.test_biometric_authentication.BiometricRegistrationTest.test_duplicate_registration_updates_existing \
  biometrics.tests.test_biometric_authentication.BiometricVerificationTest.test_successful_verification \
  biometrics.tests.test_biometrics_fixed.BiometricAPITest.test_face_registration_success \
  biometrics.tests.test_biometrics_fixed.BiometricAPITest.test_face_recognition_check_in_success \
  biometrics.tests.test_biometric_service.BiometricServiceSaveFaceEncodingTest.test_save_face_encoding_success \
  biometrics.tests.test_biometric_service.BiometricServiceIntegrationTest.test_biometric_service_workflow \
  --verbosity=2

echo ""
echo "=== Integration Tests Complete ==="
