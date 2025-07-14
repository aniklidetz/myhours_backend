#!/usr/bin/env python3
"""
Быстрая проверка изменений в payroll после обновления до 5-дневной недели
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

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_employee_overtime_changes(employee_name_or_id, year=None, month=None):
    """
    Проверить изменения в сверхурочных часах для сотрудника
    """
    try:
        # Найти сотрудника
        if isinstance(employee_name_or_id, str):
            # Попробовать найти по имени или фамилии
            employee = Employee.objects.filter(
                first_name__icontains=employee_name_or_id
            ).first()
            if not employee:
                employee = Employee.objects.filter(
                    last_name__icontains=employee_name_or_id
                ).first()
            if not employee:
                # Попробовать найти по полному имени
                employee = Employee.objects.filter(
                    first_name__icontains=employee_name_or_id.split()[0]
                ).filter(
                    last_name__icontains=employee_name_or_id.split()[-1]
                ).first() if ' ' in employee_name_or_id else None
        else:
            employee = Employee.objects.get(id=employee_name_or_id)
        
        if not employee:
            from core.logging_utils import hash_user_id
            logger.error("Сотрудник не найден", extra={"employee_ref": hash_user_id(str(employee_name_or_id))})
            return None
        
        from core.logging_utils import safe_log_employee
        logger.info("📊 Начат анализ сотрудника", extra=safe_log_employee(employee, "payroll_analysis"))
        
        # Если не указан период, используем текущий месяц
        if not year or not month:
            now = datetime.now()
            year = now.year
            month = now.month
        
        logger.info(f"📅 Период: {year}-{month:02d}")
        
        # Получить рабочие логи
        work_logs = WorkLog.objects.filter(
            employee=employee,
            check_in__year=year,
            check_in__month=month,
            check_out__isnull=False
        ).order_by('check_in')
        
        if not work_logs.exists():
            logger.info("❌ Нет рабочих сессий за этот период")
            return None
        
        logger.info(f"📋 Найдено {work_logs.count()} рабочих сессий")
        
        # Анализ по старым правилам (45ч/неделю)
        logger.info("\n🔍 АНАЛИЗ ПО СТАРЫМ ПРАВИЛАМ (6-дневная неделя, 45ч/неделю):")
        old_weekly_limit = 45
        old_daily_limit = 8
        
        # Анализ по новым правилам (42ч/неделю)
        logger.info("\n🆕 АНАЛИЗ ПО НОВЫМ ПРАВИЛАМ (5-дневная неделя, 42ч/неделю):")
        new_weekly_limit = 42
        new_daily_limit = 8.6  # 4 дня по 8.6ч + 1 день по 7.6ч
        
        # Группировка по неделям
        weeks = {}
        for log in work_logs:
            monday = log.check_in.date() - datetime.timedelta(days=log.check_in.weekday())
            if monday not in weeks:
                weeks[monday] = []
            weeks[monday].append(log)
        
        total_old_overtime = 0
        total_new_overtime = 0
        
        for week_start, week_logs in weeks.items():
            week_end = week_start + datetime.timedelta(days=6)
            total_hours = sum(log.get_total_hours() for log in week_logs)
            
            # Старые правила
            old_regular = min(total_hours, old_weekly_limit)
            old_overtime = max(0, total_hours - old_weekly_limit)
            
            # Новые правила
            new_regular = min(total_hours, new_weekly_limit)
            new_overtime = max(0, total_hours - new_weekly_limit)
            
            total_old_overtime += old_overtime
            total_new_overtime += new_overtime
            
            if old_overtime != new_overtime:
                logger.info(f"📊 Неделя {week_start}:")
                logger.info(f"   Всего часов: {total_hours}")
                logger.info(f"   Старые правила: {old_regular}ч обычных + {old_overtime}ч сверхурочных")
                logger.info(f"   Новые правила: {new_regular}ч обычных + {new_overtime}ч сверхурочных")
                logger.info(f"   Разница: {new_overtime - old_overtime:+.1f}ч сверхурочных")
        
        logger.info(f"\n📈 ОБЩИЕ ИТОГИ:")
        logger.info(f"   Старые правила: {total_old_overtime}ч сверхурочных")
        logger.info(f"   Новые правила: {total_new_overtime}ч сверхурочных")
        logger.info(f"   Изменение: {total_new_overtime - total_old_overtime:+.1f}ч")
        
        # Расчет влияния на зарплату (если есть salary info)
        try:
            salary = employee.salary_info
            if salary and salary.calculation_type == 'hourly' and salary.hourly_rate:
                hourly_rate = salary.hourly_rate
                
                # Старый расчет сверхурочных
                old_overtime_pay = total_old_overtime * hourly_rate * Decimal('1.25')  # Упрощенно
                
                # Новый расчет сверхурочных (125% первые 2ч, 150% остальные)
                new_overtime_pay = Decimal('0')
                if total_new_overtime > 0:
                    first_2h = min(total_new_overtime, 2)
                    remaining_h = max(0, total_new_overtime - 2)
                    new_overtime_pay = first_2h * hourly_rate * Decimal('1.25') + remaining_h * hourly_rate * Decimal('1.50')
                
                logger.info(f"\n💰 ВЛИЯНИЕ НА ЗАРПЛАТУ:")
                logger.info(f"   Часовая ставка: {hourly_rate} ₪/ч")
                logger.info(f"   Старая доплата за сверхурочные: {old_overtime_pay} ₪")
                logger.info(f"   Новая доплата за сверхурочные: {new_overtime_pay} ₪")
                logger.info(f"   Разница: {new_overtime_pay - old_overtime_pay:+.2f} ₪")
                
        except Exception as e:
            logger.warning(f"Не удалось рассчитать влияние на зарплату: {e}")
        
        # Использовать новый сервис для актуального расчета
        logger.info(f"\n🔄 АКТУАЛЬНЫЙ РАСЧЕТ (новый сервис):")
        try:
            calc_service = PayrollCalculationService(employee, year, month)
            result = calc_service.calculate_monthly_salary()
            
            logger.info(f"   Общая зарплата: {result['total_gross_pay']} ₪")
            logger.info(f"   Обычные часы: {result['regular_hours']}ч")
            logger.info(f"   Сверхурочные часы: {result['overtime_hours']}ч")
            logger.info(f"   Часы в праздники: {result['holiday_hours']}ч")
            logger.info(f"   Часы в субботу: {result['sabbath_hours']}ч")
            
            if result.get('warnings'):
                logger.warning("⚠️  Предупреждения:")
                for warning in result['warnings']:
                    logger.warning(f"   - {warning}")
            
        except Exception as e:
            logger.error(f"Ошибка при расчете: {e}")
        
        return {
            'employee': employee.get_full_name(),
            'old_overtime': total_old_overtime,
            'new_overtime': total_new_overtime,
            'overtime_change': total_new_overtime - total_old_overtime
        }
        
    except Exception:
        logger.exception("Ошибка при анализе сотрудника", extra=safe_log_employee(employee, "analysis_error"))
        return None

def check_all_employees_changes(year=None, month=None):
    """
    Проверить изменения для всех сотрудников
    """
    employees = Employee.objects.all()
    results = []
    
    for employee in employees:
        logger.info(f"\n{'='*60}")
        result = check_employee_overtime_changes(employee.id, year, month)
        if result:
            results.append(result)
    
    # Сводка
    logger.info(f"\n{'='*60}")
    logger.info("📊 СВОДКА ИЗМЕНЕНИЙ:")
    from core.logging_utils import mask_name
    for result in results:
        logger.info(f"   Employee {mask_name(result['employee'])}: {result['overtime_change']:+.1f}h overtime change")
    
    return results

if __name__ == "__main__":
    if len(sys.argv) > 1:
        employee_name = sys.argv[1]
        year = int(sys.argv[2]) if len(sys.argv) > 2 else None
        month = int(sys.argv[3]) if len(sys.argv) > 3 else None
        
        check_employee_overtime_changes(employee_name, year, month)
    else:
        logger.info("Использование:")
        logger.info("python check_payroll_changes.py 'Itai Shapiro' [year] [month]")
        logger.info("python check_payroll_changes.py 'Itai' 2025 7")
        logger.info("python check_payroll_changes.py 52  # по ID")