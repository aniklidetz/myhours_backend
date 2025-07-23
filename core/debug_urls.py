from django.urls import path
from . import debug_views

urlpatterns = [
    path('', debug_views.debug_auth, name='debug-auth'),
    path('worktime/', debug_views.debug_worktime_auth, name='debug-worktime-auth'),
    path('headers/', debug_views.debug_headers, name='debug-headers'),
]