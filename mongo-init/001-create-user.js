// MongoDB User Creation Script for MyHours Application
// This script creates a dedicated user for the MyHours application

// Connect to the biometrics database
db = db.getSiblingDB('biometrics_db');

// Create user for MyHours application
// Note: The password is retrieved from environment variable MONGO_PASSWORD in Docker Compose
db.createUser({
  user: "myhours_user",
  pwd: "mongo_myhours_password_456",  // This matches MONGO_PASSWORD in .env
  roles: [
    {
      role: "readWrite",
      db: "biometrics_db"
    }
  ]
});

print('MongoDB user created successfully for MyHours application');
print('   Database: biometrics_db');
print('   User: myhours_user');
print('   Permissions: readWrite');

// Create indexes for biometric data collection
db.biometric_embeddings.createIndex({ "employee_id": 1 }, { unique: true });
db.biometric_embeddings.createIndex({ "created_at": 1 });

print('MongoDB indexes created for biometric collections');
print('   - employee_id (unique)');
print('   - created_at (for sorting)');

// Insert a test document to verify everything works
db.biometric_embeddings.insertOne({
  _id: "init_test",
  test: "MongoDB authentication setup",
  created_at: new Date(),
  status: "initialized"
});

print('MongoDB initialization completed successfully');