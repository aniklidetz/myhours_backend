from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def home_view(request):
    return JsonResponse({"message": "Welcome to MyHours API. Go to /api/"})

urlpatterns = [
    path('', home_view),
    path('admin/', admin.site.urls),
    
    # API routes
    path('api/users/', include('users.urls')),
    path('api/worktime/', include('worktime.urls')),
    path('api/payroll/', include('payroll.urls')),
    path('api/biometrics/', include('biometrics.urls')),
    path('api/integrations/', include('integrations.urls')),

    # For backward compatibility
    path('api/', include('core.urls')),
]