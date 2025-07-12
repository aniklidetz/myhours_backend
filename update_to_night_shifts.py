#!/usr/bin/env python
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from worktime.models import WorkLog
from users.models import Employee
from datetime import datetime, timedelta
import pytz

# Получаем все рабочие логи Итая за июль (кроме уже обновлённого шабата)
employee = Employee.objects.get(id=1)
israel_tz = pytz.timezone('Asia/Jerusalem')

# Словарь с правильными часами для каждого дня
work_hours = {
    '2025-07-01': 8.62,
    '2025-07-02': 8.62,
    '2025-07-03': 8.73,
    '2025-07-04': 8.68,
    # 5 июля уже обновлено
    '2025-07-08': 8.62,
    '2025-07-09': 8.62,
    '2025-07-10': 8.62,
    '2025-07-11': 8.62,
}

print("Обновление рабочих логов на ночные смены:")
print("=" * 60)

for date_str, hours in work_hours.items():
    # Удаляем существующий лог
    WorkLog.objects.filter(
        employee=employee,
        check_in__date=date_str
    ).delete()
    
    # Создаём новый лог для ночной смены
    year, month, day = map(int, date_str.split('-'))
    
    # Ночная смена: предыдущий день 22:00 - текущий день рано утром
    check_in = israel_tz.localize(datetime(year, month, day - 1 if day > 1 else day, 22, 0, 0))
    
    # Вычисляем время окончания на основе часов
    minutes = int((hours % 1) * 60)
    hours_int = int(hours)
    check_out = check_in + timedelta(hours=hours_int, minutes=minutes)
    
    work_log = WorkLog.objects.create(
        employee=employee,
        check_in=check_in,
        check_out=check_out
    )
    
    print(f"Дата: {date_str}")
    print(f"  Check in:  {check_in}")
    print(f"  Check out: {check_out}")
    print(f"  Часы: {work_log.get_total_hours():.2f}")
    print()

print("\nОбновление завершено!")
print("\nПримечание: Все смены теперь ночные (22:00 - утро)")
print("Это соответствует расчёту: 63 обычных часа / 8 дней = 7.875 часов/день")