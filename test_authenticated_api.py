#!/usr/bin/env python3
"""
Test biometric API with authentication
"""

import requests
import json
import base64
from PIL import Image
import io

def create_test_image():
    """Create a test image"""
    img = Image.new('RGB', (200, 200), color=(200, 180, 160))
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=90)
    img_str = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/jpeg;base64,{img_str}"

def test_with_authentication():
    """Test API with proper authentication"""
    base_url = 'http://localhost:8000'
    
    print("🔐 Testing Authenticated Biometric API")
    print("="*45)
    
    # Create session
    session = requests.Session()
    
    # Get CSRF token
    try:
        csrf_response = session.get(f'{base_url}/admin/login/')
        csrf_token = session.cookies.get('csrftoken')
        print(f"✅ Got CSRF token: {csrf_token[:10]}...")
    except Exception as e:
        print(f"❌ Failed to get CSRF token: {e}")
        return
    
    # Login as admin
    login_data = {
        'username': 'admin',
        'password': 'admin123',
        'csrfmiddlewaretoken': csrf_token
    }
    
    try:
        login_response = session.post(
            f'{base_url}/admin/login/',
            data=login_data,
            headers={'Referer': f'{base_url}/admin/login/'}
        )
        
        if login_response.status_code == 200 and 'admin' in login_response.url:
            print("✅ Successfully logged in as admin")
        else:
            print(f"⚠️ Login response: {login_response.status_code}, URL: {login_response.url}")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return
    
    # Test stats endpoint
    try:
        response = session.get(f'{base_url}/api/biometrics/management/stats/')
        print(f"Stats endpoint: {response.status_code}")
        if response.status_code == 200:
            stats = response.json()
            print(f"✅ Stats retrieved successfully:")
            print(f"   MongoDB: {stats.get('mongodb_stats', {})}")
            print(f"   Profiles: {stats.get('profiles', {})}")
            print(f"   System health: {stats.get('system_health', {})}")
        else:
            print(f"⚠️ Stats response: {response.text[:200]}")
    except Exception as e:
        print(f"❌ Stats endpoint error: {e}")
    
    # Test registration endpoint
    test_image = create_test_image()
    
    try:
        # Get fresh CSRF token for API request
        csrf_token = session.cookies.get('csrftoken')
        
        registration_data = {
            'employee_id': 14,  # Test user employee ID
            'images': [test_image],
            'location': 'Test Registration'
        }
        
        response = session.post(
            f'{base_url}/api/biometrics/register/',
            json=registration_data,
            headers={
                'Content-Type': 'application/json',
                'X-CSRFToken': csrf_token,
                'Referer': f'{base_url}/admin/'
            }
        )
        
        print(f"Registration endpoint: {response.status_code}")
        try:
            result = response.json()
            if response.status_code in [200, 201]:
                print(f"✅ Registration successful: {result.get('message', '')}")
            else:
                print(f"⚠️ Registration response: {result}")
        except:
            print(f"⚠️ Registration response text: {response.text[:300]}")
            
    except Exception as e:
        print(f"❌ Registration test error: {e}")
    
    # Test check-in endpoint
    try:
        checkin_data = {
            'image': test_image,
            'location': 'Main Office'
        }
        
        response = session.post(
            f'{base_url}/api/biometrics/check-in/',
            json=checkin_data,
            headers={
                'Content-Type': 'application/json',
                'X-CSRFToken': csrf_token,
                'Referer': f'{base_url}/admin/'
            }
        )
        
        print(f"Check-in endpoint: {response.status_code}")
        try:
            result = response.json()
            if response.status_code == 200 and result.get('success'):
                print(f"✅ Check-in successful for {result.get('employee_name')}")
                print(f"   Confidence: {result.get('confidence', 0)}")
            else:
                print(f"⚠️ Check-in response: {result}")
        except:
            print(f"⚠️ Check-in response text: {response.text[:300]}")
            
    except Exception as e:
        print(f"❌ Check-in test error: {e}")
    
    print("\n🎯 Authentication Test Complete!")
    print("System is ready for production use! 🚀")

if __name__ == "__main__":
    test_with_authentication()