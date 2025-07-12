#!/usr/bin/env python
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from payroll.services import PayrollCalculationService
from users.models import Employee
from worktime.models import WorkLog
from datetime import date
from decimal import Decimal

# Получаем все рабочие логи за июль
employee = Employee.objects.get(id=1)
work_logs = WorkLog.objects.filter(
    employee=employee,
    check_in__year=2025,
    check_in__month=7
).order_by('check_in')

service = PayrollCalculationService(employee, 2025, 7)

print("Детальный расчёт по дням (июль 2025):")
print("=" * 80)

total_regular = Decimal('0')
total_overtime_125 = Decimal('0')
total_overtime_150 = Decimal('0')
total_sabbath_regular = Decimal('0')
total_sabbath_overtime = Decimal('0')

for log in work_logs:
    daily_calc = service.calculate_daily_pay_enhanced(log)
    hours = log.get_total_hours()
    
    print(f"\nДата: {log.check_in.date()}")
    print(f"  Часы: {hours:.2f}")
    
    if daily_calc['is_sabbath']:
        print(f"  ⚡ ШАБАТ - Ночная смена: {daily_calc['is_night_shift']}")
        
    breakdown = daily_calc['breakdown']
    if breakdown['regular_hours'] > 0:
        if daily_calc['is_sabbath']:
            print(f"  Обычные часы (150%): {breakdown['regular_hours']:.2f} × ₪165 = ₪{breakdown['regular_pay']:.2f}")
            total_sabbath_regular += breakdown['regular_pay']
        else:
            print(f"  Обычные часы: {breakdown['regular_hours']:.2f} × ₪110 = ₪{breakdown['regular_pay']:.2f}")
            total_regular += breakdown['regular_pay']
            
    if breakdown['overtime_hours_1'] > 0:
        if daily_calc['is_sabbath']:
            print(f"  Сверхурочные (175%): {breakdown['overtime_hours_1']:.2f} × ₪192.5 = ₪{breakdown['overtime_pay_1']:.2f}")
            total_sabbath_overtime += breakdown['overtime_pay_1']
        else:
            print(f"  Сверхурочные (125%): {breakdown['overtime_hours_1']:.2f} × ₪137.5 = ₪{breakdown['overtime_pay_1']:.2f}")
            total_overtime_125 += breakdown['overtime_pay_1']
            
    if breakdown['overtime_hours_2'] > 0:
        print(f"  Доп. сверхурочные (150%): {breakdown['overtime_hours_2']:.2f} × ₪165 = ₪{breakdown['overtime_pay_2']:.2f}")
        total_overtime_150 += breakdown['overtime_pay_2']
        
    print(f"  Итого за день: ₪{daily_calc['total_pay']:.2f}")

print("\n" + "=" * 80)
print("ИТОГОВАЯ РАЗБИВКА:")
print(f"  Обычные часы: ₪{total_regular:.2f}")
print(f"  Сверхурочные 125%: ₪{total_overtime_125:.2f}")
print(f"  Сверхурочные 150%: ₪{total_overtime_150:.2f}")
print(f"  Шабат обычные (150%): ₪{total_sabbath_regular:.2f}")
print(f"  Шабат сверхурочные (175%): ₪{total_sabbath_overtime:.2f}")
print(f"  ВСЕГО: ₪{(total_regular + total_overtime_125 + total_overtime_150 + total_sabbath_regular + total_sabbath_overtime):.2f}")

# Проверяем ожидаемый расчёт
print("\n" + "=" * 80)
print("ОЖИДАЕМЫЙ РАСЧЁТ:")
print("• Regular: 63.00 h × ₪110 = ₪6,930.00")
print("• Overtime (weekday): 12.37 h × ₪137.5 (125%) = ₪1,700.88")
print("• Shabbat:")
print("  ├── 7.00 h × ₪165 (150%) = ₪1,155.00")
print("  └── 1.53 h × ₪192.5 (175%) = ₪294.53")
print("💰 Total Expected: ₪10,080.40")