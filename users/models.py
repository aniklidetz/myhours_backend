from django.db import models

class Employee(models.Model):
    """Модель сотрудника"""
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    EMPLOYMENT_TYPES = [
        ('monthly', 'Monthly Salary'),  # Фиксированная месячная зарплата
        ('hourly', 'Hourly Wage'),  # Почасовая ставка
        ('contract', 'Contract Work'),  # Контрактная работа
    ]
    employment_type = models.CharField(
        max_length=10, choices=EMPLOYMENT_TYPES, default='hourly'
    )  # Тип занятости сотрудника

    def __str__(self):
        return f"{self.first_name} {self.last_name}"