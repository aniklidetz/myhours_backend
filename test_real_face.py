#!/usr/bin/env python3
"""
Test biometric system with real face image
"""

import os
import sys
import django
import base64
import time
from PIL import Image, ImageDraw
import io
import numpy as np

# Setup Django
sys.path.append('/Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from django.test import Client
from django.contrib.auth.models import User
from users.models import Employee
from biometrics.services.face_processor import face_processor
from biometrics.services.mongodb_service import mongodb_service


def create_realistic_face_image():
    """Create a more realistic test face image"""
    # Create a 400x400 image
    img = Image.new('RGB', (400, 400), color='white')
    draw = ImageDraw.Draw(img)
    
    # Draw face outline (circle)
    face_center = (200, 200)
    face_radius = 120
    draw.ellipse([face_center[0]-face_radius, face_center[1]-face_radius, 
                  face_center[0]+face_radius, face_center[1]+face_radius], 
                 fill='#F4C2A1', outline='#D4A574', width=2)
    
    # Draw eyes
    left_eye = (170, 170)
    right_eye = (230, 170)
    eye_radius = 15
    
    # Left eye
    draw.ellipse([left_eye[0]-eye_radius, left_eye[1]-eye_radius,
                  left_eye[0]+eye_radius, left_eye[1]+eye_radius],
                 fill='white', outline='black', width=2)
    draw.ellipse([left_eye[0]-7, left_eye[1]-7,
                  left_eye[0]+7, left_eye[1]+7],
                 fill='#4A4A4A')
    draw.ellipse([left_eye[0]-3, left_eye[1]-3,
                  left_eye[0]+3, left_eye[1]+3],
                 fill='black')
    
    # Right eye
    draw.ellipse([right_eye[0]-eye_radius, right_eye[1]-eye_radius,
                  right_eye[0]+eye_radius, right_eye[1]+eye_radius],
                 fill='white', outline='black', width=2)
    draw.ellipse([right_eye[0]-7, right_eye[1]-7,
                  right_eye[0]+7, right_eye[1]+7],
                 fill='#4A4A4A')
    draw.ellipse([right_eye[0]-3, right_eye[1]-3,
                  right_eye[0]+3, right_eye[1]+3],
                 fill='black')
    
    # Draw nose
    nose_points = [(200, 190), (195, 210), (205, 210)]
    draw.polygon(nose_points, fill='#E6B18A', outline='#D4A574', width=1)
    
    # Draw mouth
    mouth_center = (200, 240)
    draw.ellipse([mouth_center[0]-20, mouth_center[1]-8,
                  mouth_center[0]+20, mouth_center[1]+8],
                 fill='#8B4513', outline='#654321', width=1)
    
    # Add some texture/noise to make it more realistic
    img_array = np.array(img)
    noise = np.random.normal(0, 5, img_array.shape).astype(np.int16)
    img_array = np.clip(img_array.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    img = Image.fromarray(img_array)
    
    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=85)
    img_str = base64.b64encode(buffer.getvalue()).decode()
    
    return f"data:image/jpeg;base64,{img_str}"


def test_full_biometric_workflow():
    """Test complete biometric workflow"""
    print("🧪 Testing Complete Biometric Workflow")
    print("="*50)
    
    # 1. Create test user and employee
    print("\n1️⃣ Creating test user...")
    try:
        User.objects.filter(username='real_face_test').delete()
        user = User.objects.create_user(
            username='real_face_test',
            password='testpass123',
            first_name='Real',
            last_name='Face',
            email='realface@test.com'
        )
        
        employee = Employee.objects.create(
            user=user,
            first_name='Real',
            last_name='Face',
            email='realface@test.com',
            role='employee'
        )
        print(f"✅ Created employee: {employee.get_full_name()} (ID: {employee.id})")
    except Exception as e:
        print(f"❌ Failed to create user: {e}")
        return False
    
    # 2. Test face image creation and processing
    print("\n2️⃣ Creating realistic face image...")
    try:
        face_image = create_realistic_face_image()
        print("✅ Face image created successfully")
        print(f"   Image size: {len(face_image)} characters")
        
        # Test face processor directly
        print("\n3️⃣ Testing face processor...")
        result = face_processor.process_registration_image(face_image)
        print(f"   Processing result: {result.get('success', False)}")
        if result.get('success'):
            print(f"   ✅ Face encoding extracted: {len(result.get('encoding', []))} dimensions")
            print(f"   Quality score: {result.get('quality_check', {}).get('quality_score', 0):.2f}")
        else:
            print(f"   ⚠️ No face detected: {result.get('error', 'Unknown error')}")
            print(f"   Quality info: {result.get('quality_check', {})}")
        
    except Exception as e:
        print(f"❌ Face processing failed: {e}")
        return False
    
    # 3. Test MongoDB operations
    print("\n4️⃣ Testing MongoDB operations...")
    try:
        if result.get('success'):
            # Save embeddings to MongoDB
            embeddings = [{'vector': result['encoding'], 'quality_score': 0.8}]
            mongo_id = mongodb_service.save_face_embeddings(employee.id, embeddings)
            
            if mongo_id:
                print(f"✅ Embeddings saved to MongoDB: {mongo_id}")
                
                # Retrieve embeddings
                retrieved = mongodb_service.get_face_embeddings(employee.id)
                if retrieved:
                    print(f"✅ Retrieved {len(retrieved)} embeddings from MongoDB")
                else:
                    print("⚠️ Failed to retrieve embeddings")
            else:
                print("❌ Failed to save embeddings to MongoDB")
        else:
            print("⚠️ Skipping MongoDB test (no face encoding)")
            
    except Exception as e:
        print(f"❌ MongoDB operations failed: {e}")
    
    # 4. Test API endpoints
    print("\n5️⃣ Testing API endpoints...")
    try:
        client = Client()
        
        # Login
        login_success = client.login(username='real_face_test', password='testpass123')
        if not login_success:
            print("❌ Failed to login")
            return False
        print("✅ User logged in successfully")
        
        # Test registration endpoint
        registration_data = {
            'employee_id': employee.id,
            'images': [face_image],
            'location': 'Test Office'
        }
        
        response = client.post('/api/biometrics/register/', 
                             registration_data, 
                             content_type='application/json')
        
        print(f"Registration response: {response.status_code}")
        if response.status_code in [200, 201]:
            try:
                response_data = response.json()
                print(f"✅ Registration successful: {response_data.get('message', '')}")
            except:
                print("✅ Registration endpoint responded positively")
        else:
            try:
                error_data = response.json()
                print(f"⚠️ Registration response: {error_data}")
            except:
                print(f"⚠️ Registration returned status {response.status_code}")
        
        # Test check-in endpoint
        checkin_data = {
            'image': face_image,
            'location': 'Main Office'
        }
        
        response = client.post('/api/biometrics/check-in/', 
                             checkin_data, 
                             content_type='application/json')
        
        print(f"Check-in response: {response.status_code}")
        if response.status_code == 200:
            try:
                response_data = response.json()
                if response_data.get('success'):
                    print(f"✅ Check-in successful for {response_data.get('employee_name')}")
                    print(f"   Confidence: {response_data.get('confidence', 0):.2f}")
                else:
                    print(f"⚠️ Check-in failed: {response_data.get('error')}")
            except:
                print("✅ Check-in endpoint responded")
        else:
            try:
                error_data = response.json()
                print(f"⚠️ Check-in response: {error_data}")
            except:
                print(f"⚠️ Check-in returned status {response.status_code}")
        
    except Exception as e:
        print(f"❌ API testing failed: {e}")
    
    # 5. Statistics
    print("\n6️⃣ System statistics...")
    try:
        stats = mongodb_service.get_statistics()
        print(f"MongoDB stats: {stats}")
        
        # Count profiles
        from biometrics.models import BiometricProfile, BiometricLog
        profiles = BiometricProfile.objects.count()
        logs = BiometricLog.objects.count()
        print(f"Database: {profiles} profiles, {logs} logs")
        
    except Exception as e:
        print(f"⚠️ Stats error: {e}")
    
    # Cleanup
    print("\n7️⃣ Cleanup...")
    try:
        # Clean MongoDB
        mongodb_service.delete_embeddings(employee.id)
        # Clean Django
        from biometrics.models import BiometricProfile
        BiometricProfile.objects.filter(employee=employee).delete()
        employee.delete()
        user.delete()
        print("✅ Cleanup completed")
    except Exception as e:
        print(f"⚠️ Cleanup warning: {e}")
    
    print("\n🎉 Biometric workflow test completed!")
    return True


if __name__ == "__main__":
    test_full_biometric_workflow()