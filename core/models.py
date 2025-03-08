# core/models.py
# Импортируем модели из новых приложений для обратной совместимости
from users.models import Employee
from worktime.models import WorkLog
from payroll.models import Salary
from integrations.models import Holiday

# Теперь, если какой-то существующий код импортирует из core.models, 
# он всё равно получит доступ к нужным моделям