from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

# Функция-заглушка для главной страницы
def home_view(request):
    return JsonResponse({"message": "Welcome to MyHours API. Go to /api/"})

urlpatterns = [
    path('', home_view),  # Заглушка для корневого URL
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),  # Подключаем маршруты из core.urls
]