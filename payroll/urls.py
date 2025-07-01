from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SalaryViewSet, current_earnings, employee_earnings_summary, 
    attendance_report, enhanced_earnings, compensatory_days_detail,
    demo_enhanced_data, backward_compatible_earnings
)

router = DefaultRouter()
router.register(r'salaries', SalaryViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('earnings/', backward_compatible_earnings, name='current-earnings'),  # Updated to use new logic
    path('earnings/legacy/', current_earnings, name='legacy-earnings'),       # Keep old version for comparison
    path('earnings/enhanced/', enhanced_earnings, name='enhanced-earnings'),
    path('earnings/demo/', demo_enhanced_data, name='demo-enhanced-data'),
    path('earnings/summary/', employee_earnings_summary, name='earnings-summary'),
    path('attendance/', attendance_report, name='attendance-report'),
    path('compensatory-days/', compensatory_days_detail, name='compensatory-days-detail'),
]