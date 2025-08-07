from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import EmployeeViewSet, SalaryViewSet, WorkLogViewSet

router = DefaultRouter()
router.register(r"employees", EmployeeViewSet)
router.register(r"salaries", SalaryViewSet)
router.register(r"worklogs", WorkLogViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
