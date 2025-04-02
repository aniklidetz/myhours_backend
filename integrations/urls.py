from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import HolidayViewSet

router = DefaultRouter()
router.register(r'holidays', HolidayViewSet)

urlpatterns = [
    path('', include(router.urls)),
]