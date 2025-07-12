#!/usr/bin/env python3
"""
Полная очистка и пересчет всех payroll данных с новыми правилами 5-дневной недели
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

def clear_cached_payroll_data():
    """
    Очистить все кэшированные payroll данные
    """
    logger.info("🧹 Очистка кэшированных payroll данных...")
    
    try:
        # Очищаем компенсационные дни (они будут пересчитаны)
        comp_days_count = CompensatoryDay.objects.count()
        logger.info(f"📋 Найдено {comp_days_count} компенсационных дней")
        
        if comp_days_count > 0:
            # Создаем резервную копию в логах
            logger.info("💾 Создание резервной копии компенсационных дней...")
            for comp_day in CompensatoryDay.objects.all():
                logger.info(f"  Backup: {comp_day.employee.get_full_name()} - {comp_day.date_earned} - {comp_day.reason}")
            
            # Очищаем компенсационные дни
            CompensatoryDay.objects.all().delete()
            logger.info(f"✅ Удалено {comp_days_count} компенсационных дней")
        
        # Очищаем Django кэш (если используется)
        try:
            from django.core.cache import cache
            cache.clear()
            logger.info("✅ Очищен Django кэш")
        except:
            logger.info("ℹ️  Django кэш не настроен")
        
        logger.info("✅ Очистка завершена")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка при очистке данных: {e}")
        import traceback
        traceback.print_exc()
        return False

def recalculate_all_employees_payroll(months_back=3):
    """
    Пересчитать payroll для всех сотрудников за указанное количество месяцев
    """
    logger.info(f"🔄 Начинаем пересчет payroll для всех сотрудников за последние {months_back} месяцев...")
    
    # Получаем все сотрудники с salary configuration
    employees = Employee.objects.filter(salary_info__isnull=False)
    logger.info(f"👥 Найдено {employees.count()} сотрудников с salary configuration")
    
    if employees.count() == 0:
        logger.warning("⚠️  Не найдено сотрудников с salary configuration!")
        return False
    
    # Определяем периоды для пересчета
    now = datetime.now()
    periods = []
    for i in range(months_back):
        target_date = now - timedelta(days=30*i)
        periods.append((target_date.year, target_date.month))
    
    logger.info(f"📅 Периоды для пересчета: {periods}")
    
    success_count = 0
    error_count = 0
    
    for employee in employees:
        logger.info(f"\n{'='*60}")
        logger.info(f"👤 Пересчет для: {employee.get_full_name()}")
        
        # Проверяем salary configuration
        try:
            salary = employee.salary_info
            logger.info(f"💼 Тип расчета: {salary.calculation_type}")
            
            if salary.calculation_type == 'hourly':
                logger.info(f"💰 Часовая ставка: {salary.hourly_rate} ₪/ч")
            elif salary.calculation_type == 'monthly':
                logger.info(f"💰 Месячная зарплата: {salary.base_salary} ₪")
                
        except Exception as e:
            logger.error(f"❌ Ошибка salary configuration для {employee.get_full_name()}: {e}")
            error_count += 1
            continue
        
        # Пересчитываем для каждого периода
        employee_success = True
        for year, month in periods:
            try:
                logger.info(f"📊 Пересчет за {year}-{month:02d}...")
                
                # Проверяем есть ли рабочие логи за этот период
                work_logs = WorkLog.objects.filter(
                    employee=employee,
                    check_in__year=year,
                    check_in__month=month,
                    check_out__isnull=False
                )
                
                if not work_logs.exists():
                    logger.info(f"ℹ️  Нет рабочих сессий за {year}-{month:02d}")
                    continue
                
                logger.info(f"📋 Найдено {work_logs.count()} рабочих сессий")
                
                # Используем новый сервис для расчета
                calc_service = PayrollCalculationService(employee, year, month)
                result = calc_service.calculate_monthly_salary()
                
                logger.info(f"✅ Расчет завершен:")
                logger.info(f"   💰 Общая зарплата: {result['total_gross_pay']} ₪")
                logger.info(f"   ⏰ Обычные часы: {result['regular_hours']}ч")
                logger.info(f"   ⏰ Сверхурочные: {result['overtime_hours']}ч")
                logger.info(f"   🎉 Праздничные: {result['holiday_hours']}ч")
                logger.info(f"   🕯️  Субботние: {result['sabbath_hours']}ч")
                logger.info(f"   📅 Компенсационные дни: {result['compensatory_days_earned']}")
                
                # Проверяем предупреждения
                if result.get('warnings'):
                    logger.warning("⚠️  Предупреждения:")
                    for warning in result['warnings']:
                        logger.warning(f"   - {warning}")
                
                # Проверяем нарушения
                if result.get('legal_violations'):
                    logger.warning("🚨 Нарушения трудового законодательства:")
                    for violation in result['legal_violations']:
                        logger.warning(f"   - {violation}")
                
            except Exception as e:
                logger.error(f"❌ Ошибка при пересчете {employee.get_full_name()} за {year}-{month:02d}: {e}")
                employee_success = False
                # Продолжаем с другими периодами
                continue
        
        if employee_success:
            success_count += 1
            logger.info(f"✅ {employee.get_full_name()} - пересчет завершен успешно")
        else:
            error_count += 1
            logger.error(f"❌ {employee.get_full_name()} - ошибки при пересчете")
    
    logger.info(f"\n{'='*60}")
    logger.info(f"📊 ИТОГИ ПЕРЕСЧЕТА:")
    logger.info(f"   ✅ Успешно: {success_count} сотрудников")
    logger.info(f"   ❌ Ошибки: {error_count} сотрудников")
    logger.info(f"   📅 Периоды: {len(periods)} месяцев")
    
    return success_count > 0

def validate_new_calculations():
    """
    Проверить корректность новых расчетов
    """
    logger.info("🔍 Проверка корректности новых расчетов...")
    
    try:
        # Проверяем константы в сервисе
        from payroll.services import PayrollCalculationService
        
        # Создаем временный экземпляр для проверки констант
        logger.info("📋 Проверка констант:")
        logger.info(f"   MAX_WEEKLY_REGULAR_HOURS: {PayrollCalculationService.MAX_WEEKLY_REGULAR_HOURS}")
        logger.info(f"   MONTHLY_WORK_HOURS: {PayrollCalculationService.MONTHLY_WORK_HOURS}")
        logger.info(f"   OVERTIME_RATE_1: {PayrollCalculationService.OVERTIME_RATE_1}")
        logger.info(f"   OVERTIME_RATE_2: {PayrollCalculationService.OVERTIME_RATE_2}")
        
        # Проверяем что используются правильные константы
        if PayrollCalculationService.MAX_WEEKLY_REGULAR_HOURS == 42:
            logger.info("✅ Недельный лимит: 42 часа (5-дневная неделя)")
        else:
            logger.warning(f"⚠️  Недельный лимит: {PayrollCalculationService.MAX_WEEKLY_REGULAR_HOURS} часов")
        
        if PayrollCalculationService.MONTHLY_WORK_HOURS == 182:
            logger.info("✅ Месячная норма: 182 часа (5-дневная неделя)")
        else:
            logger.warning(f"⚠️  Месячная норма: {PayrollCalculationService.MONTHLY_WORK_HOURS} часов")
        
        # Проверяем созданные компенсационные дни
        comp_days_count = CompensatoryDay.objects.count()
        logger.info(f"📅 Создано компенсационных дней: {comp_days_count}")
        
        if comp_days_count > 0:
            latest_comp_days = CompensatoryDay.objects.order_by('-created_at')[:5]
            logger.info("🔄 Последние созданные компенсационные дни:")
            for comp_day in latest_comp_days:
                logger.info(f"   {comp_day.employee.get_full_name()} - {comp_day.date_earned} - {comp_day.reason}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке: {e}")
        return False

def main():
    """
    Основная функция - полный reset и пересчет
    """
    logger.info("🚀 Начинаем полный reset и пересчет payroll данных...")
    logger.info("=" * 80)
    
    # Подтверждение от пользователя
    if len(sys.argv) < 2 or sys.argv[1] != '--confirm':
        logger.info("⚠️  ВНИМАНИЕ: Этот скрипт удалит все существующие payroll данные!")
        logger.info("💡 Для подтверждения запустите:")
        logger.info("   python full_payroll_reset_and_recalc.py --confirm")
        logger.info("   или добавьте --months N для указания количества месяцев")
        return
    
    # Количество месяцев для пересчета
    months_back = 3
    if len(sys.argv) > 2 and sys.argv[2] == '--months':
        months_back = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    
    logger.info(f"📅 Будет выполнен пересчет за последние {months_back} месяцев")
    
    # Шаг 1: Очистка
    logger.info("\n🧹 ШАГ 1: Очистка старых данных")
    if not clear_cached_payroll_data():
        logger.error("❌ Не удалось очистить данные. Прерываем выполнение.")
        return
    
    # Шаг 2: Пересчет
    logger.info(f"\n🔄 ШАГ 2: Пересчет всех данных")
    if not recalculate_all_employees_payroll(months_back):
        logger.error("❌ Пересчет завершился с ошибками.")
        return
    
    # Шаг 3: Проверка
    logger.info(f"\n🔍 ШАГ 3: Проверка результатов")
    if not validate_new_calculations():
        logger.warning("⚠️  Проверка выявила проблемы.")
    
    logger.info("\n" + "=" * 80)
    logger.info("🎉 ПОЛНЫЙ RESET И ПЕРЕСЧЕТ ЗАВЕРШЕН!")
    logger.info("💡 Теперь все payroll данные рассчитаны по новым правилам 5-дневной недели")
    logger.info("🔄 Рекомендуется перезапустить Docker контейнеры для применения изменений")

if __name__ == "__main__":
    main()