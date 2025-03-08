from django.db import models
from users.models import Employee

class WorkLog(models.Model):
    """Модель записи о рабочем времени"""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    check_in = models.DateTimeField()
    check_out = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)  # Дата создания записи
    location_check_in = models.CharField(max_length=255, blank=True, null=True)
    location_check_out = models.CharField(max_length=255, blank=True, null=True)

    def get_total_hours(self):
        """
        Рассчитывает общее количество часов, отработанных в смене.
        Calculates the total hours worked in a shift.
        """
        if self.check_out:
            duration = self.check_out - self.check_in
            return duration.total_seconds() / 3600  # Преобразуем в часы
        return 0  # Если check_out нет, значит сотрудник всё ещё работает

    def __str__(self):
        return f"{self.employee} - {self.check_in} to {self.check_out or 'Still working'}"