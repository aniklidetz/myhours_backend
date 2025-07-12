from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    backward_compatible_earnings, payroll_list, enhanced_earnings
)

# Временно отключаем router до восстановления SalaryViewSet
# router = DefaultRouter()
# router.register(r'salaries', SalaryViewSet)

urlpatterns = [
    # path('', include(router.urls)),  # Временно отключено
    path('', payroll_list, name='payroll-list'),  # Root endpoint возвращает список
    path('salaries/', payroll_list, name='payroll-salaries'),  # Фронтенд ожидает этот endpoint
    path('earnings/', enhanced_earnings, name='current-earnings'),
]