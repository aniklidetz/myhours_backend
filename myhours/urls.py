from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

# Функция-заглушка для главной страницы
def home_view(request):
    return JsonResponse({"message": "Welcome to MyHours API. Go to /api/"})

urlpatterns = [
    path('', home_view),  # Заглушка для корневого URL
    path('admin/', admin.site.urls),
    # Новые URL-пути для реструктурированных приложений
    path('api/users/', include('users.urls')),
    path('api/worktime/', include('worktime.urls')),
    path('api/payroll/', include('payroll.urls')),
    path('api/biometrics/', include('biometrics.urls')),
    # Если у вас есть urls.py в integrations - сейчас закомментировано
    # path('api/integrations/', include('integrations.urls')),
    # Сохраняем для обратной совместимости
    path('api/', include('core.urls')),  # Подключаем маршруты из core.urls
]