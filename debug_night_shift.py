#!/usr/bin/env python3
import os
import django
from decimal import Decimal
from datetime import datetime

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from django.utils import timezone
from users.models import Employee
from worktime.models import WorkLog
from payroll.models import Salary
from payroll.services.strategies.enhanced import EnhancedPayrollStrategy
from payroll.services.contracts import CalculationContext
from payroll.services.enums import CalculationStrategy

def debug_sabbath_night_shift():
    # Создаем тестового сотрудника
    employee = Employee.objects.create(
        name="Test Employee", 
        email="test@example.com",
        role="employee"
    )
    
    salary = Salary.objects.create(
        employee=employee,
        hourly_rate=Decimal("100"),
        salary_type="hourly"
    )
    
    # Создаем пятничную ночную смену: 22:00 пятница → 06:00 суббота
    check_in = timezone.make_aware(datetime(2025, 7, 4, 22, 0))  # Friday 10 PM
    check_out = timezone.make_aware(datetime(2025, 7, 5, 6, 0))  # Saturday 6 AM
    
    worklog = WorkLog.objects.create(
        employee=employee, 
        check_in=check_in, 
        check_out=check_out
    )
    
    print(f"=== ОТЛАДКА ПЯТНИЧНОЙ НОЧНОЙ СМЕНЫ ===")
    print(f"Смена: {check_in} → {check_out}")
    print(f"Общее время: {worklog.get_total_hours()} часов")
    print(f"Ночные часы (worktime/night_shift): {worklog.get_night_hours()} часов")
    
    # Тестируем Enhanced Strategy расчет ночных часов
    strategy = EnhancedPayrollStrategy()
    night_hours_enhanced = strategy._calculate_night_shift_hours(worklog)
    print(f"Ночные часы (Enhanced Strategy): {night_hours_enhanced} часов")
    
    # Тестируем полный расчет зарплаты
    context = CalculationContext(
        employee=employee,
        year=2025,
        month=7
    )
    
    result = strategy.calculate(context)
    
    print(f"\n=== РЕЗУЛЬТАТ РАСЧЕТА ===")
    print(f"Общая зарплата: {result.total_salary}")
    print(f"Обычные часы: {result.regular_hours}")
    print(f"Переработка: {result.overtime_hours}") 
    print(f"Праздничные часы: {result.holiday_hours}")
    print(f"Шабатные часы: {result.shabbat_hours}")
    
    if hasattr(result, 'breakdown') and result.breakdown:
        print(f"\n=== ДЕТАЛЬНЫЙ РАСЧЕТ ===")
        breakdown = result.breakdown
        print(f"Базовая зарплата: {breakdown.regular_pay}")
        print(f"Переработка 125%: {breakdown.overtime_pay_125}")  
        print(f"Переработка 150%: {breakdown.overtime_pay_150}")
        print(f"Праздничная оплата: {breakdown.holiday_pay}")
        print(f"Шабатная оплата: {breakdown.sabbath_pay}")
        print(f"Ночная оплата: {breakdown.night_shift_pay}")
    
    # Очистка
    worklog.delete()
    salary.delete() 
    employee.delete()

if __name__ == "__main__":
    debug_sabbath_night_shift()