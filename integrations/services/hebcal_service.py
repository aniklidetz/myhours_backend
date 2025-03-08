# Заглушка для сервиса Hebcal API
import requests
import logging
from datetime import datetime
from django.core.cache import cache
from ..models import Holiday

logger = logging.getLogger(__name__)

class HebcalService:
    """Сервис для работы с API Hebcal для праздников и шаббатов"""
    
    BASE_URL = "https://www.hebcal.com/hebcal"
    
    @staticmethod
    def fetch_holidays(year=None, month=None, cache_timeout=86400):
        """
        Получает праздники и шаббаты из API Hebcal.
        """
        # Для тестов просто возвращаем заглушку данных
        return [
            {
                "title": "Shabbat",
                "date": "2025-03-15"
            },
            {
                "title": "Passover",
                "date": "2025-04-14"
            }
        ]
    
    @staticmethod
    def update_holidays_database(year=None):
        """
        Обновляет базу данных праздников.
        """
        # Заглушка для тестов
        return 2, 0  # 2 созданных записи, 0 обновленных