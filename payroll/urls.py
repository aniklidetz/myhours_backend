from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SalaryViewSet, current_earnings, employee_earnings_summary

router = DefaultRouter()
router.register(r'salaries', SalaryViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('earnings/', current_earnings, name='current-earnings'),
    path('earnings/summary/', employee_earnings_summary, name='earnings-summary'),
]