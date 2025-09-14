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
from payroll.services.payroll_service import PayrollService
from payroll.services.enums import CalculationStrategy
from payroll.tests.helpers import make_context
from payroll.models import MonthlyPayrollSummary

def debug_monthly_logic():
    # Создаем тестового месячного сотрудника
    try:
        employee = Employee.objects.get(email="monthly_debug@example.com")
    except Employee.DoesNotExist:
        employee = Employee.objects.create(
            first_name="Monthly", 
            last_name="Debug",
            email="monthly_debug@example.com",
            role="employee"
        )
    
    # Удаляем старые данные
    WorkLog.objects.filter(employee=employee).delete()
    
    salary = Salary.objects.create(
        employee=employee,
        calculation_type="monthly",
        base_salary=Decimal("15000.00"),
        currency="ILS"
    )
    
    # Создаем 10 рабочих дней, как в тесте
    for day in range(1, 11):  # 10 work days
        check_in = timezone.make_aware(datetime(2025, 7, day, 9, 0))
        check_out = timezone.make_aware(datetime(2025, 7, day, 17, 0))
        WorkLog.objects.create(
            employee=employee, check_in=check_in, check_out=check_out
        )
    
    print(f"=== ОТЛАДКА МЕСЯЧНОЙ ЛОГИКИ ===")
    print(f"Создано 10 смен: 9:00 → 17:00 (каждая по 8 часов)")
    print(f"Общее время: 80 часов")
    print(f"Base salary: {salary.base_salary}")
    print(f"Calculation type: {salary.calculation_type}")
    
    # Тестируем PayrollService (как в тесте)
    payroll_service = PayrollService()
    context = make_context(employee, 2025, 7)
    
    # Тестируем полный расчет
    try:
        result = payroll_service.calculate(context, CalculationStrategy.ENHANCED)
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

        # Test with fast_mode=True to see if that helps
        context_fast = make_context(employee, 2025, 7)
        context_fast['fast_mode'] = True
        result_fast = payroll_service.calculate(context_fast, CalculationStrategy.ENHANCED)
        print(f"\n=== FAST MODE РЕЗУЛЬТАТ ===")
        print(f"Type: {type(result_fast)}")
        if isinstance(result_fast, dict):
            print(f"total_hours: {result_fast.get('total_hours', 'N/A')}")
            print(f"total_salary: {result_fast.get('total_salary', 'N/A')}")
        else:
            print(f"total_hours: {result_fast.total_hours}")
            print(f"total_salary: {result_fast.total_salary}")
            
        # Проверим, создалась ли запись MonthlyPayrollSummary
        monthly_summary = MonthlyPayrollSummary.objects.filter(
            employee=employee, year=2025, month=7
        ).first()
        if monthly_summary:
            print(f"\n=== MONTHLY SUMMARY НАЙДЕН ===")
            print(f"total_salary: {monthly_summary.total_salary}")
            print(f"worked_days: {monthly_summary.worked_days}")
        else:
            print(f"\n=== MONTHLY SUMMARY НЕ НАЙДЕН ===")
            
    except Exception as e:
        print(f"Ошибка в полном расчете: {e}")
        import traceback
        traceback.print_exc()
    
    # Очистка
    WorkLog.objects.filter(employee=employee).delete()
    if salary.pk:
        salary.delete()

if __name__ == "__main__":
    debug_monthly_logic()