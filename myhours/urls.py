# myhours/urls.py
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from rest_framework.permissions import AllowAny
from rest_framework.authentication import TokenAuthentication
from django.utils import timezone

from rest_framework.decorators import permission_classes, authentication_classes
from .health import health_check as detailed_health_check

@api_view(['GET'])
@permission_classes([AllowAny])
@authentication_classes([])
def health_check(request):
    """Public health check endpoint"""
    return Response({
        'status': 'online',
        'message': 'API is connected successfully!',
        'version': '1.0',
        'timestamp': timezone.now().isoformat()
    })

@api_view(['GET'])
def api_root(request):
    """API root endpoint showing available endpoints"""
    return Response({
        'message': 'MyHours API',
        'version': '1.0',
        'api_versions': {
            'current': 'v1',
            'supported': ['v1'],
            'deprecated': []
        },
        'endpoints': {
            'admin': request.build_absolute_uri('/admin/'),
            'api_docs': request.build_absolute_uri('/api/docs/'),
            'current_api': request.build_absolute_uri('/api/v1/'),
            'v1_users': request.build_absolute_uri('/api/v1/users/'),
            'v1_employees': request.build_absolute_uri('/api/v1/users/employees/'),
            'v1_auth_login': request.build_absolute_uri('/api/v1/users/auth/login/'),
            'v1_worktime': request.build_absolute_uri('/api/v1/worktime/'),
            'v1_payroll': request.build_absolute_uri('/api/v1/payroll/'),
            'v1_biometrics': request.build_absolute_uri('/api/v1/biometrics/'),
            'v1_integrations': request.build_absolute_uri('/api/v1/integrations/'),
        }
    })

# Explicitly set permission and authentication classes
api_root.permission_classes = [AllowAny]
api_root.authentication_classes = []

urlpatterns = [
    # Root redirect to API
    path('', RedirectView.as_view(url='/api/', permanent=False)),
    
    path('admin/', admin.site.urls),
    
    # Health check endpoints (public)
    path('api/health/', health_check, name='health-check'),
    path('health/', detailed_health_check, name='detailed-health-check'),
    
    # Debug endpoints (temporary for authentication troubleshooting)
    path('api/debug/auth/', include('core.debug_urls')),
    
    # API root
    path('api/', api_root, name='api-root'),
    
    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # API v1 endpoints (current version)
    path('api/v1/', api_root, name='api-v1-root'),
    path('api/v1/users/', include('users.urls')),
    path('api/v1/worktime/', include('worktime.urls')),
    path('api/v1/payroll/', include('payroll.urls')),
    path('api/v1/biometrics/', include(('biometrics.urls', 'biometrics'), namespace='biometrics')),
    path('api/v1/integrations/', include('integrations.urls')),
    
    # Legacy API endpoints removed - all traffic goes to v1 directly
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)