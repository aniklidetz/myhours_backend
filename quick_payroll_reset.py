#!/usr/bin/env python3
"""
Быстрый reset и пересчет payroll данных только за текущий месяц
"""

import os
import sys
import django
from decimal import Decimal
from datetime import datetime, date, timedelta
import logging

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from django.db import transaction
from users.models import Employee
from payroll.models import Salary, CompensatoryDay
from payroll.services import PayrollCalculationService
from worktime.models import WorkLog

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def quick_reset_current_month():
    """
    Быстрый reset только для текущего месяца
    """
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    
    logger.info(f"🚀 Быстрый reset payroll данных за {current_year}-{current_month:02d}")
    
    # Очищаем компенсационные дни только за текущий месяц
    current_month_comp_days = CompensatoryDay.objects.filter(
        date_earned__year=current_year,
        date_earned__month=current_month
    )
    
    comp_count = current_month_comp_days.count()
    logger.info(f"🧹 Найдено {comp_count} компенсационных дней за текущий месяц")
    
    if comp_count > 0:
        # Создаем резервную копию в логах
        logger.info("💾 Backup компенсационных дней:")
        for comp_day in current_month_comp_days:
            logger.info(f"  {comp_day.employee.get_full_name()} - {comp_day.date_earned} - {comp_day.reason}")
        
        current_month_comp_days.delete()
        logger.info(f"✅ Удалено {comp_count} компенсационных дней за текущий месяц")
    
    # Очищаем кэш
    try:
        from django.core.cache import cache
        cache.clear()
        logger.info("✅ Очищен кэш")
    except:
        pass
    
    # Пересчитываем для всех сотрудников
    employees = Employee.objects.filter(salary_info__isnull=False)
    logger.info(f"👥 Найдено {employees.count()} сотрудников")
    
    success_count = 0
    results = []
    
    for employee in employees:
        try:
            logger.info(f"\n📊 Пересчет для: {employee.get_full_name()}")
            
            # Проверяем есть ли рабочие логи
            work_logs = WorkLog.objects.filter(
                employee=employee,
                check_in__year=current_year,
                check_in__month=current_month,
                check_out__isnull=False
            )
            
            if not work_logs.exists():
                logger.info(f"ℹ️  Нет рабочих сессий")
                continue
            
            logger.info(f"📋 Найдено {work_logs.count()} рабочих сессий")
            
            # Пересчитываем
            calc_service = PayrollCalculationService(employee, current_year, current_month)
            result = calc_service.calculate_monthly_salary()
            
            # Сохраняем результат
            employee_result = {
                'name': employee.get_full_name(),
                'total_pay': result['total_gross_pay'],
                'regular_hours': result['regular_hours'],
                'overtime_hours': result['overtime_hours'],
                'holiday_hours': result['holiday_hours'],
                'sabbath_hours': result['sabbath_hours'],
                'comp_days': result['compensatory_days_earned'],
                'warnings': result.get('warnings', []),
                'violations': result.get('legal_violations', [])
            }
            
            results.append(employee_result)
            success_count += 1
            
            logger.info(f"✅ Результат:")
            logger.info(f"   💰 Зарплата: {result['total_gross_pay']} ₪")
            logger.info(f"   ⏰ Обычные: {result['regular_hours']}ч")
            logger.info(f"   ⏰ Сверхурочные: {result['overtime_hours']}ч")
            logger.info(f"   📅 Компенсационные дни: {result['compensatory_days_earned']}")
            
            if result.get('warnings'):
                logger.warning("⚠️  Предупреждения:")
                for warning in result['warnings']:
                    logger.warning(f"   - {warning}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка для {employee.get_full_name()}: {e}")
            continue
    
    # Сводка
    logger.info(f"\n{'='*60}")
    logger.info(f"📊 ИТОГИ ПЕРЕСЧЕТА ЗА {current_year}-{current_month:02d}:")
    logger.info(f"   ✅ Обработано: {success_count} сотрудников")
    
    logger.info(f"\n📋 ПОДРОБНЫЕ РЕЗУЛЬТАТЫ:")
    total_payroll = 0
    for result in results:
        logger.info(f"   {result['name']}:")
        logger.info(f"      💰 {result['total_pay']} ₪")
        logger.info(f"      ⏰ {result['regular_hours']}ч обычных + {result['overtime_hours']}ч сверхурочных")
        if result['comp_days'] > 0:
            logger.info(f"      📅 {result['comp_days']} компенсационных дней")
        total_payroll += result['total_pay']
    
    logger.info(f"\n💰 ОБЩИЙ PAYROLL ЗА МЕСЯЦ: {total_payroll} ₪")
    
    # Проверяем созданные компенсационные дни
    new_comp_days = CompensatoryDay.objects.filter(
        date_earned__year=current_year,
        date_earned__month=current_month
    ).count()
    
    logger.info(f"📅 Создано компенсационных дней: {new_comp_days}")
    
    logger.info(f"\n🎉 БЫСТРЫЙ RESET ЗАВЕРШЕН!")
    logger.info(f"🔄 Все данные за {current_year}-{current_month:02d} пересчитаны с новыми правилами")

if __name__ == "__main__":
    quick_reset_current_month()