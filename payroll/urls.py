from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    backward_compatible_earnings,
    payroll_list,
    enhanced_earnings,
    daily_payroll_calculations,
    monthly_payroll_summary,
    recalculate_payroll,
    payroll_analytics,
)

# Временно отключаем router до восстановления SalaryViewSet
# router = DefaultRouter()
# router.register(r'salaries', SalaryViewSet)

urlpatterns = [
    # path('', include(router.urls)),  # Временно отключено
    path("", payroll_list, name="payroll-list"),  # Root endpoint возвращает список
    path(
        "salaries/", payroll_list, name="payroll-salaries"
    ),  # Фронтенд ожидает этот endpoint
    path("earnings/", enhanced_earnings, name="current-earnings"),
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
