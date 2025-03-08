from django.db import models
from decimal import Decimal, ROUND_HALF_UP
from users.models import Employee

class Salary(models.Model):
    """
    Модель расчёта зарплаты.
    Salary calculation model.
    """
    employee = models.OneToOneField(
        Employee,
        on_delete=models.CASCADE
    )  # Один сотрудник – одна зарплата / One employee - one salary

    base_salary = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )  # Фиксированная месячная ставка / Fixed monthly salary

    hourly_rate = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, null=True, blank=True
    )  # Почасовая ставка / Hourly rate

    bonus = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )  # Бонусы / Bonuses

    deductions = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )  # Удержания (налоги, штрафы) / Deductions (taxes, fines)

    calculated_salary = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )  # Итоговая зарплата / Final salary

    updated_at = models.DateTimeField(auto_now=True)  
    # Время последнего обновления / Last update time

    CURRENCY_CHOICES = [
        ('NIS', 'New Israeli Shekel'),
        ('USD', 'US Dollar'),
        ('EUR', 'Euro'),
    ]
    currency = models.CharField(
        max_length=3, choices=CURRENCY_CHOICES, default='NIS'
    )  # Валюта зарплаты / Salary currency

    def calculate_salary(self):
        """ 
        Рассчитывает итоговую зарплату сотрудника, учитывая тип занятости, бонусы и вычеты.
        Calculates the final salary considering employment type, bonuses, and deductions.
        """
        from worktime.models import WorkLog
        
        work_logs = WorkLog.objects.filter(employee=self.employee)
        total_hours = sum(log.get_total_hours() for log in work_logs)

        if self.employee.employment_type == "monthly":
            salary = self.base_salary
        else:
            salary = Decimal(total_hours) * self.hourly_rate

        # Добавляем бонусы и удержания
        salary += Decimal(self.bonus)
        salary -= Decimal(self.deductions)

        # Зарплата не может быть отрицательной
        salary = max(salary, Decimal(0))

        # Округляем до 2 знаков после запятой
        self.calculated_salary = salary.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.save()

    def __str__(self):
        return f"{self.employee} - {self.calculated_salary} {self.currency}"