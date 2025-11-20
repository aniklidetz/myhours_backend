"""
URL configuration for AI Assistant app.
"""

from django.urls import path

from .views import SalaryExplanationHealthView, SalaryExplanationView, test_page

app_name = "ai_assistant"

urlpatterns = [
    # Main endpoint for salary explanations
    path("explain/", SalaryExplanationView.as_view(), name="explain"),
    # Health check endpoint
    path("health/", SalaryExplanationHealthView.as_view(), name="health"),
    # Test page for demo
    path("test/", test_page, name="test"),
]
