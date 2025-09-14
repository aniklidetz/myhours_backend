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
from payroll.tests.helpers import make_context

def debug_new_logic():
    # Создаем тестового сотрудника или используем существующего
    try:
        employee = Employee.objects.get(email="debug@example.com")
    except Employee.DoesNotExist:
        employee = Employee.objects.create(
            first_name="Debug", 
            last_name="User",
            email="debug@example.com",
            role="employee"
        )
    
    # Удаляем старые worklogs этого сотрудника
    WorkLog.objects.filter(employee=employee).delete()
    
    salary = Salary.objects.create(
        employee=employee,
        hourly_rate=Decimal("100"),
        calculation_type="hourly"
    )
    
    # Создаем пятничную ночную смену: 22:00 пятница → 06:00 суббота
    check_in = timezone.make_aware(datetime(2025, 7, 4, 22, 0))  # Friday 10 PM
    check_out = timezone.make_aware(datetime(2025, 7, 5, 6, 0))  # Saturday 6 AM
    
    worklog = WorkLog.objects.create(
        employee=employee, 
        check_in=check_in, 
        check_out=check_out
    )
    
    print(f"=== ОТЛАДКА НОВОЙ ЛОГИКИ ===")
    print(f"Смена: {check_in} → {check_out}")
    print(f"Общее время worklog: {worklog.get_total_hours()} часов")
    print(f"Ночные часы (worktime/night_shift): {worklog.get_night_hours()} часов")
    
    # Тестируем Enhanced Strategy
    context = {
        'employee_id': employee.pk,
        'year': 2025,
        'month': 7,
        'user_id': 1,
        'strategy_hint': None,
        'force_recalculate': False,
        'fast_mode': False,
        'include_breakdown': True,
        'include_daily_details': False
    }
    strategy = EnhancedPayrollStrategy(context)
    
    # Тестируем детектор ночной смены
    is_night = strategy._is_night_segment(check_in, check_out)
    print(f"Детектор ночной смены: {is_night}")
    
    # Тестируем классификацию (это пятница, но смена переходит в субботу)
    work_date = check_in.date()
    is_holiday = False
    is_sabbath = work_date.weekday() == 5  # Saturday - должно быть False для пятницы
    print(f"work_date: {work_date}, weekday: {work_date.weekday()}")
    print(f"is_sabbath (from weekday): {is_sabbath}")
    
    # Тестируем логику пятничной смены, переходящей в субботу
    if work_date.weekday() == 4 and is_night:  # Friday night shift
        from datetime import timedelta
        saturday_start = check_in.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        print(f"Saturday start: {saturday_start}")
        print(f"check_out: {check_out}")
        if check_out > saturday_start:
            is_sabbath = True  # Friday night spanning Saturday = Sabbath night
            print(f"Friday night spanning Saturday detected -> is_sabbath = True")
    
    print(f"Итоговая классификация: is_sabbath={is_sabbath}, is_night={is_night}")
    
    # Тестируем систему ступеней
    log_hours = Decimal(str(worklog.get_total_hours()))
    hourly_rate = Decimal("100")
    
    bands_result = strategy._get_bands(is_sabbath, is_night)
    print(f"Ступени: {bands_result}")
    
    segment_result = strategy._apply_bands(log_hours, hourly_rate, is_sabbath, is_night)
    print(f"Результат применения ступеней: {segment_result}")
    
    # Тестируем полный расчет
    try:
        result = strategy.calculate()
        print(f"\n=== ПОЛНЫЙ РЕЗУЛЬТАТ ===")
        print(f"Type: {type(result)}")
        if isinstance(result, dict):
            print(f"total_hours: {result.get('total_hours', 'N/A')}")
            print(f"total_salary: {result.get('total_salary', 'N/A')}")
            print(f"breakdown keys: {list(result.get('breakdown', {}).keys()) if 'breakdown' in result else 'N/A'}")
        else:
            print(f"total_hours: {result.total_hours}")
            print(f"total_salary: {result.total_salary}")
            print(f"breakdown: {result.breakdown}")
    except Exception as e:
        print(f"Ошибка в полном расчете: {e}")
        import traceback
        traceback.print_exc()
    
    # Очистка
    worklog.delete()
    if salary.pk:
        salary.delete()

if __name__ == "__main__":
    debug_new_logic()