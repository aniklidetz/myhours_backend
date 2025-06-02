# myhours/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/users/', include('users.urls')),
    path('api/worktime/', include('worktime.urls')),
    path('api/payroll/', include('payroll.urls')),
    path('api/biometrics/', include('biometrics.urls')),
    path('api/integrations/', include('integrations.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)