from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import HolidayViewSet

router = DefaultRouter()
router.register(r"holidays", HolidayViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
