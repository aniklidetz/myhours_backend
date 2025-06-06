# users/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EmployeeViewSet
from .auth_views import login_view, logout_view, test_connection
from .enhanced_auth_views import (
    enhanced_login,
    biometric_verification,
    refresh_token,
    logout_device
)

router = DefaultRouter()
router.register(r'employees', EmployeeViewSet)

urlpatterns = [
    path('', include(router.urls)),
    
    # Legacy authentication endpoints (for backward compatibility)
    path('auth/login/', login_view, name='legacy-login'),
    path('auth/logout/', logout_view, name='legacy-logout'),
    path('test/', test_connection, name='test-connection'),
    
    # Enhanced authentication endpoints
    path('auth/enhanced-login/', enhanced_login, name='enhanced-login'),
    path('auth/biometric-verification/', biometric_verification, name='biometric-verification'),
    path('auth/refresh-token/', refresh_token, name='refresh-token'),
    path('auth/logout-device/', logout_device, name='logout-device'),
]