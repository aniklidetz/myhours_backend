from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FaceRegistrationView,
    FaceRecognitionCheckInView,
    FaceRecognitionCheckOutView,
    BiometricManagementViewSet
)

# Create router for ViewSets
router = DefaultRouter()
router.register(r'management', BiometricManagementViewSet, basename='biometric-management')

urlpatterns = [
    # Face recognition endpoints
    path('register/', FaceRegistrationView.as_view(), name='face-register'),
    path('check-in/', FaceRecognitionCheckInView.as_view(), name='face-check-in'),
    path('check-out/', FaceRecognitionCheckOutView.as_view(), name='face-check-out'),
    
    # Management endpoints (stats, admin functions)
    path('', include(router.urls)),
]