from django.db import models
from django.utils.timezone import now
from decimal import Decimal, ROUND_HALF_UP

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

class WorkLog(models.Model):
    """Модель записи о рабочем времени"""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    check_in = models.DateTimeField()
    check_out = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)  # Дата создания записи

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

class Salary(models.Model):
    """
    Модель расчёта зарплаты.
    Salary calculation model.
    """
    employee = models.OneToOneField(
        "core.Employee",
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
        work_logs = self.employee.worklog_set.all()
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