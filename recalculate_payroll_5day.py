#!/usr/bin/env python3
"""
Скрипт для пересчета payroll с новыми правилами 5-дневной недели
"""

import os
import sys
import django
from decimal import Decimal
from datetime import datetime, date
import logging

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from users.models import Employee
from payroll.models import Salary
from payroll.services import PayrollCalculationService
from worktime.models import WorkLog
from core.logging_utils import safe_log_employee

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def recalculate_employee_payroll(employee_name_or_id, year=None, month=None):
    """
    Пересчитать payroll для конкретного сотрудника
    """
    try:
        # Найти сотрудника
        if isinstance(employee_name_or_id, str):
            employee = Employee.objects.filter(
                first_name__icontains=employee_name_or_id
            ).first() or Employee.objects.filter(
                last_name__icontains=employee_name_or_id
            ).first()
        else:
            employee = Employee.objects.get(id=employee_name_or_id)
        
        if not employee:
            from core.logging_utils import hash_user_id
            logger.error("Сотрудник не найден", extra={"employee_ref": hash_user_id(str(employee_name_or_id))})
            return None
        
        logger.info("Пересчет для сотрудника", extra=safe_log_employee(employee, "payroll_recalc"))
        
        # Если не указан период, используем текущий месяц
        if not year or not month:
            now = datetime.now()
            year = now.year
            month = now.month
        
        logger.info(f"Период: {year}-{month:02d}")
        
        # Проверить есть ли salary configuration
        try:
            salary = employee.salary_info
            if not salary:
                logger.error("У сотрудника нет salary configuration", extra=safe_log_employee(employee, "missing_salary"))
                return None
        except Exception as e:
            logger.error("Ошибка получения salary для сотрудника", extra={
                **safe_log_employee(employee, "salary_error"),
                "error_type": type(e).__name__
            })
            return None
        
        # Показать старые данные безопасно
        logger.info("Salary configuration loaded", extra={
            **safe_log_employee(employee, "salary_loaded"),
            "calculation_type": salary.calculation_type
        })
        
        # Получить рабочие логи для анализа
        work_logs = WorkLog.objects.filter(
            employee=employee,
            check_in__year=year,
            check_in__month=month,
            check_out__isnull=False
        ).order_by('check_in')
        
        logger.info(f"Найдено {work_logs.count()} рабочих сессий")
        
        # Показать сводку по часам ДО обновления
        total_old_hours = sum(log.get_total_hours() for log in work_logs)
        logger.info(f"Общее количество часов: {total_old_hours}")
        
        # Пересчитать с новыми правилами
        calc_service = PayrollCalculationService(employee, year, month)
        new_result = calc_service.calculate_monthly_salary()
        
        logger.info("Payroll calculation completed", extra={
            **safe_log_employee(employee, "payroll_calculated"),
            "regular_hours": float(new_result['regular_hours']),
            "overtime_hours": float(new_result['overtime_hours']),
            "holiday_hours": float(new_result['holiday_hours']),
            "sabbath_hours": float(new_result['sabbath_hours']),
            "compensatory_days": new_result['compensatory_days_earned']
        })
        
        # Показать нарушения и предупреждения
        if new_result.get('legal_violations'):
            logger.warning("Нарушения трудового законодательства:")
            for violation in new_result['legal_violations']:
                logger.warning(f"  - {violation}")
        
        if new_result.get('warnings'):
            logger.warning("Предупреждения:")
            for warning in new_result['warnings']:
                logger.warning(f"  - {warning}")
        
        # Показать недельную разбивку
        logger.info("\n=== НЕДЕЛЬНАЯ РАЗБИВКА ===")
        weeks = {}
        for log in work_logs:
            # Получить понедельник недели
            monday = log.check_in.date() - datetime.timedelta(days=log.check_in.weekday())
            if monday not in weeks:
                weeks[monday] = []
            weeks[monday].append(log)
        
        for week_start, week_logs in weeks.items():
            week_end = week_start + datetime.timedelta(days=6)
            total_hours = sum(log.get_total_hours() for log in week_logs)
            
            # Новые правила: 42 часа регулярных + 16 сверхурочных = 58 максимум
            regular_hours = min(total_hours, 42)
            overtime_hours = max(0, total_hours - 42)
            
            logger.info(f"Неделя {week_start} - {week_end}:")
            logger.info(f"  Всего часов: {total_hours}")
            logger.info(f"  Регулярных: {regular_hours}")
            logger.info(f"  Сверхурочных: {overtime_hours}")
            
            if total_hours > 58:
                logger.warning(f"  ⚠️  Превышение максимума (58ч): {total_hours - 58}ч")
            elif overtime_hours > 16:
                logger.warning(f"  ⚠️  Превышение сверхурочных (16ч): {overtime_hours - 16}ч")
        
        return new_result
        
    except Exception:
        logger.exception("Ошибка при пересчете зарплаты")
        return None

def recalculate_all_employees(year=None, month=None):
    """
    Пересчитать payroll для всех сотрудников
    """
    employees = Employee.objects.all()
    results = {}
    
    for employee in employees:
        logger.info(f"\n{'='*50}")
        result = recalculate_employee_payroll(employee.id, year, month)
        if result:
            results[employee.get_full_name()] = result
    
    return results

if __name__ == "__main__":
    if len(sys.argv) > 1:
        employee_name = sys.argv[1]
        year = int(sys.argv[2]) if len(sys.argv) > 2 else None
        month = int(sys.argv[3]) if len(sys.argv) > 3 else None
        
        logger.info("Пересчет зарплаты начат")
        result = recalculate_employee_payroll(employee_name, year, month)
        
        if result:
            logger.info("\n✅ Пересчет завершен успешно!")
        else:
            logger.error("\n❌ Ошибка при пересчете")
    else:
        logger.info("Использование:")
        logger.info("python recalculate_payroll_5day.py 'Itai Shapiro' [year] [month]")
        logger.info("python recalculate_payroll_5day.py 'Itai' 2025 7")
        logger.info("python recalculate_payroll_5day.py 52  # по ID")