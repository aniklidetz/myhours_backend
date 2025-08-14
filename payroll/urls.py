from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import (
    backward_compatible_earnings,
    daily_payroll_calculations,
    enhanced_earnings,
    monthly_payroll_summary,
    payroll_analytics,
    payroll_list,
    recalculate_payroll,
)

# Временно отключаем router до восстановления SalaryViewSet
# router = DefaultRouter()
# router.register(r'salaries', SalaryViewSet)

urlpatterns = [
    # path('', include(router.urls)),  # Temporarily disabled
    path("", payroll_list, name="payroll-list"),  # Root endpoint returns list
    path(
        "salaries/", payroll_list, name="payroll-salaries"
    ),  # Frontend expects this endpoint
    path("earnings/", enhanced_earnings, name="current-earnings"),
    path(
        "enhanced-earnings/", enhanced_earnings, name="enhanced-earnings"
    ),  # Alias for tests
    # New database-backed payroll API endpoints
    path(
        "daily-calculations/",
        daily_payroll_calculations,
        name="daily-payroll-calculations",
    ),
    path("monthly-summary/", monthly_payroll_summary, name="monthly-payroll-summary"),
    path("recalculate/", recalculate_payroll, name="recalculate-payroll"),
    path("analytics/", payroll_analytics, name="payroll-analytics"),
]
