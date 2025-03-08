from django.db import models

class Holiday(models.Model):
    """Модель для хранения информации о праздниках и шаббатах"""
    date = models.DateField()
    name = models.CharField(max_length=100)
    is_shabbat = models.BooleanField(default=False)
    is_holiday = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.name} - {self.date}"