from django.urls import path
from . import views

urlpatterns = [
    # Face recognition endpoints
    path("register/", views.register_face, name="face-register"),
    path("check-in/", views.check_in, name="face-check-in"),
    path("check-out/", views.check_out, name="face-check-out"),
    # Generic endpoints for authentication tests
    path("register/", views.register_face, name="register"),  # Alias for tests
    # Test endpoint
    path("test/", views.test_endpoint, name="test-endpoint"),
    # Work status endpoint - placed before status to test pattern matching
    path("work-status/", views.check_work_status, name="biometric-work-status"),
    # Status endpoints
    path("status/", views.get_biometric_status, name="biometric-status"),
    # Statistics endpoint
    path("management/stats/", views.biometric_stats, name="biometric-stats"),
    # Verification endpoint for tests
    path("verify/", views.verify_face, name="verify"),
]
