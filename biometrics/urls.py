# biometrics/urls.py
from django.urls import path
from .views import (
    register_face,
    check_in,
    check_out,
    check_work_status,
    biometric_stats,
    get_biometric_status
)

urlpatterns = [
    # Face recognition endpoints
    path('register/', register_face, name='face-register'),
    path('check-in/', check_in, name='face-check-in'),
    path('check-out/', check_out, name='face-check-out'),
    
    # Status endpoints
    path('status/', get_biometric_status, name='biometric-status'),
    path('work-status/', check_work_status, name='work-status'),
    
    # Statistics endpoint
    path('management/stats/', biometric_stats, name='biometric-stats'),
]