from django.urls import path
from .views import (
    FaceRegistrationView,
    FaceRecognitionCheckInView,
    FaceRecognitionCheckOutView
)

urlpatterns = [
    path('register/', FaceRegistrationView.as_view(), name='face-register'),
    path('check-in/', FaceRecognitionCheckInView.as_view(), name='face-check-in'),
    path('check-out/', FaceRecognitionCheckOutView.as_view(), name='face-check-out'),
]