#!/usr/bin/env python
"""
Diagnose camera initialization issues for specific users
"""
import os
import sys
import django

# Setup Django
sys.path.append('/Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from users.models import Employee
from biometrics.models import BiometricProfile, BiometricLog
from django.contrib.auth.models import User

def diagnose_mishka_camera_issue():
    print("🔍 Diagnosing camera issue for mikhail.plotnik@gmail.com")
    print("=" * 60)
    
    try:
        # Check if employee exists
        employee = Employee.objects.get(email='mikhail.plotnik@gmail.com')
        print(f"✅ Employee found: {employee.first_name} {employee.last_name}")
        print(f"   ID: {employee.id}")
        print(f"   Email: {employee.email}")
        print(f"   Role: {employee.role}")
        print(f"   Active: {employee.is_active}")
        
        # Check Django user
        if hasattr(employee, 'user') and employee.user:
            user = employee.user
            print(f"✅ Django user: {user.username}")
            print(f"   Active: {user.is_active}")
        else:
            print("⚠️ No Django user linked")
        
        # Check biometric profile
        try:
            profile = BiometricProfile.objects.get(employee=employee)
            print(f"✅ BiometricProfile found:")
            print(f"   MongoDB ID: {profile.mongo_id}")
            print(f"   Is Active: {profile.is_active}")
            print(f"   Created: {profile.created_at}")
            print(f"   Updated: {profile.updated_at}")
        except BiometricProfile.DoesNotExist:
            print("❌ No BiometricProfile found - this might be the issue!")
            print("💡 User may need to register biometric data first")
            return False
        
        # Check recent biometric logs
        print("\n📊 Recent biometric activity:")
        recent_logs = BiometricLog.objects.filter(employee=employee).order_by('-timestamp')[:5]
        if recent_logs:
            for log in recent_logs:
                status_icon = "✅" if log.success else "❌"
                print(f"   {status_icon} {log.timestamp} - {log.action} - {log.result}")
        else:
            print("   No recent biometric activity found")
        
        # Test MongoDB connection
        print("\n🔌 Testing MongoDB connection...")
        try:
            from biometrics.services.mongodb_service import MongoDBService
            mongo_service = MongoDBService()
            
            # Try to connect and get collection info
            face_embeddings = mongo_service.get_face_embeddings(employee.id)
            if face_embeddings:
                print(f"✅ Found {len(face_embeddings)} face embeddings in MongoDB")
            else:
                print("⚠️ No face embeddings found in MongoDB")
                print("💡 User needs to complete biometric registration")
                return False
                
        except Exception as mongo_error:
            print(f"❌ MongoDB connection failed: {mongo_error}")
            print("💡 This is likely the root cause of camera hanging!")
            print("🔧 Solution: Start MongoDB service")
            return False
        
        print("\n✅ All biometric systems appear normal for this user")
        print("🤔 Camera issue might be frontend-specific or device-related")
        return True
        
    except Employee.DoesNotExist:
        print("❌ Employee not found in database")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def suggest_solutions():
    print("\n🔧 SUGGESTED SOLUTIONS:")
    print("=" * 40)
    print("1. Check if MongoDB is running:")
    print("   brew services start mongodb-community")
    print("   # or")
    print("   mongod --config /usr/local/etc/mongod.conf")
    print()
    print("2. If MongoDB is running, check biometric registration:")
    print("   - User may need to complete biometric registration first")
    print("   - Check if face embeddings exist in MongoDB")
    print()
    print("3. Frontend camera issues:")
    print("   - Check camera permissions on device")
    print("   - Try restarting the Expo dev server")
    print("   - Clear React Native cache")
    print()
    print("4. Check backend logs for more details:")
    print("   tail -f logs/django.log")

if __name__ == '__main__':
    success = diagnose_mishka_camera_issue()
    if not success:
        suggest_solutions()