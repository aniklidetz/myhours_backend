from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import WorkLogViewSet

router = DefaultRouter()
router.register(r"worklogs", WorkLogViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
