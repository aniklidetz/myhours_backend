"""
Исправленный сервис расчёта зарплаты согласно израильскому трудовому законодательству

Основные исправления:
1. Корректная фильтрация сессий по месяцам
2. Правильные коэффициенты сверхурочных (125% → 150%)
3. Точный расчёт шабатных часов (150% + 175%)
4. Правильная обработка ночных смен (7ч лимит)
5. Исправленная логика компенсационных дней
"""

from django.utils import timezone
from django.db import models
from datetime import datetime, date, timedelta
from decimal import Decimal
import logging
import calendar

from worktime.models import WorkLog
from payroll.models import Salary, CompensatoryDay
from integrations.models import Holiday
from integrations.services.sunrise_sunset_service import SunriseSunsetService

logger = logging.getLogger(__name__)

class PayrollCalculationService:
    """
    Исправленный сервис расчёта зарплаты согласно израильскому трудовому законодательству
    """
    
    # Константы израильского трудового права для 5-дневной рабочей недели
    MAX_DAILY_HOURS = Decimal('12')
    MAX_WEEKLY_REGULAR_HOURS = Decimal('42')  # 5-дневная неделя
    MAX_WEEKLY_OVERTIME_HOURS = Decimal('16')
    MINIMUM_WAGE_ILS = Decimal('5300')
    MONTHLY_WORK_HOURS = Decimal('182')
    
    # Дневные нормы часов для 5-дневной недели
    REGULAR_DAILY_HOURS = Decimal('8.6')  # 4 дня в неделю
    SHORT_DAILY_HOURS = Decimal('7.6')    # 1 день в неделю (обычно пятница)
    
    # Константы для ночных смен
    NIGHT_SHIFT_START = 22  # 22:00
    NIGHT_SHIFT_END = 6     # 06:00
    NIGHT_SHIFT_MAX_REGULAR_HOURS = Decimal('7')  # Макс. обычные часы для ночной смены
    
    # Коэффициенты оплаты
    OVERTIME_RATE_1 = Decimal('1.25')  # Первые 2 часа сверхурочных
    OVERTIME_RATE_2 = Decimal('1.50')  # Дополнительные сверхурочные
    HOLIDAY_RATE = Decimal('1.50')     # Коэффициент работы в праздник
    SABBATH_RATE = Decimal('1.50')     # Коэффициент работы в шабат
    
    def __init__(self, employee, year, month):
        """
        Инициализация расчёта зарплаты для конкретного сотрудника и периода
        
        Args:
            employee (Employee): Объект сотрудника
            year (int): Год для расчёта
            month (int): Месяц для расчёта
        """
        self.employee = employee
        self.year = year
        self.month = month
        self.salary = employee.salary_info
        self.calculation_errors = []
        self.warnings = []
        
    def get_work_logs_for_month(self):
        """
        ИСПРАВЛЕНО: Корректная фильтрация рабочих логов для месяца
        
        Проблема: предыдущий код мог терять сессии, которые начинались в одном месяце,
        а заканчивались в другом.
        
        Returns:
            QuerySet: Рабочие логи для указанного месяца
        """
        # Вычисляем точные границы месяца
        start_date = date(self.year, self.month, 1)
        _, last_day = calendar.monthrange(self.year, self.month)
        end_date = date(self.year, self.month, last_day)
        
        # ИСПРАВЛЕНО: более точная фильтрация
        # Включаем сессии, которые:
        # 1. Начались в этом месяце (независимо от окончания)
        # 2. Закончились в этом месяце (независимо от начала)
        work_logs = WorkLog.objects.filter(
            employee=self.employee,
            check_out__isnull=False  # Только завершённые сессии
        ).filter(
            # Сессия пересекается с месяцем
            models.Q(check_in__date__lte=end_date) & 
            models.Q(check_out__date__gte=start_date)
        ).order_by('check_in')
        
        logger.info(f"📊 Найдено {work_logs.count()} рабочих сессий для {self.employee.get_full_name()} "
                   f"в {self.year}-{self.month:02d}")
        
        return work_logs
    
    def is_sabbath_work(self, work_datetime):
        """
        ИСПРАВЛЕНО: Определение работы в шабат согласно израильскому закону
        
        Шабат: от пятницы вечером (18 минут до заката) до субботы вечером
        (42 минуты после заката). Для практических целей рассматриваем работу
        в пятницу вечером и субботу как работу в шабат.
        
        Args:
            work_datetime (datetime): Время начала работы
            
        Returns:
            tuple: (is_sabbath, sabbath_type, precise_timing)
        """
        work_date = work_datetime.date()
        work_time = work_datetime.time()
        
        # Проверяем наличие записи о шабате в таблице праздников
        sabbath_holiday = Holiday.objects.filter(
            date=work_date,
            is_shabbat=True
        ).first()
        
        if sabbath_holiday:
            return True, 'registered_sabbath', sabbath_holiday
        
        # Проверяем работу в пятницу вечером или субботу
        if work_date.weekday() == 4:  # Пятница
            # Считаем работу после 18:00 в пятницу работой в шабат
            if work_time.hour >= 18:
                return True, 'friday_evening', None
        elif work_date.weekday() == 5:  # Суббота
            # Вся работа в субботу считается работой в шабат
            return True, 'saturday', None
            
        return False, None, None
    
    def is_night_shift(self, work_log):
        """
        ИСПРАВЛЕНО: Проверка ночной смены согласно израильскому праву
        Ночная смена = минимум 2 часа между 22:00-06:00
        
        Args:
            work_log (WorkLog): Рабочий лог для проверки
            
        Returns:
            tuple: (is_night_shift, night_hours_count)
        """
        check_in = work_log.check_in
        check_out = work_log.check_out
        
        # Вычисляем часы, попадающие в ночное время (22:00-06:00)
        night_hours = Decimal('0')
        
        # Создаём объекты datetime для границ ночного периода
        night_start = check_in.replace(hour=self.NIGHT_SHIFT_START, minute=0, second=0)
        night_end = check_in.replace(hour=self.NIGHT_SHIFT_END, minute=0, second=0)
        
        # Если night_end меньше night_start, это следующий день
        if night_end <= night_start:
            night_end += timedelta(days=1)
        
        # Проверяем пересечение смены с ночным периодом
        if check_out > night_start and check_in < night_end:
            # Вычисляем пересечение
            overlap_start = max(check_in, night_start)
            overlap_end = min(check_out, night_end)
            
            if overlap_end > overlap_start:
                night_hours = Decimal((overlap_end - overlap_start).total_seconds() / 3600)
        
        # Ночная смена требует минимум 2 часа в ночном периоде
        is_night = night_hours >= Decimal('2')
        
        return is_night, night_hours
    
    def get_daily_hour_norm(self, work_date, is_night_shift=False):
        """
        ИСПРАВЛЕНО: Получение дневной нормы часов для конкретной даты
        
        Args:
            work_date (date): Дата работы
            is_night_shift (bool): Является ли смена ночной
            
        Returns:
            Decimal: Дневная норма часов
        """
        # Ночные смены имеют специальный лимит
        if is_night_shift:
            return self.NIGHT_SHIFT_MAX_REGULAR_HOURS
        
        # Пятница (weekday 4) имеет сокращённые часы
        if work_date.weekday() == 4:
            return self.SHORT_DAILY_HOURS
        
        # Проверяем выходные
        if work_date.weekday() >= 5:  # Суббота или воскресенье
            return Decimal('0')  # Обычные часы не ожидаются
        
        # Обычный рабочий день
        return self.REGULAR_DAILY_HOURS
    
    def calculate_overtime_pay(self, hours_worked, base_rate, is_special_day=False, is_night_shift=False):
        """
        ИСПРАВЛЕНО: Расчёт сверхурочной оплаты согласно израильскому трудовому праву
        
        Основные изменения:
        1. Правильные коэффициенты: 125% для первых 2ч, 150% для остальных
        2. Специальная обработка шабата/праздников
        3. Корректная обработка ночных смен
        
        Args:
            hours_worked (Decimal): Общее количество отработанных часов
            base_rate (Decimal): Базовая часовая ставка
            is_special_day (bool): Праздник/шабат (разные коэффициенты)
            is_night_shift (bool): Ночная смена (лимит 7ч)
            
        Returns:
            dict: Детализированный расчёт оплаты
        """
        # Обработка None для месячных сотрудников
        if base_rate is None:
            base_rate = Decimal('0')
        
        result = {
            'regular_hours': Decimal('0'),
            'regular_pay': Decimal('0'),
            'overtime_hours_1': Decimal('0'),  # Первые 2 часа сверхурочных
            'overtime_pay_1': Decimal('0'),
            'overtime_hours_2': Decimal('0'),  # Дополнительные сверхурочные
            'overtime_pay_2': Decimal('0'),
            'total_pay': Decimal('0'),
            'rate_used': base_rate
        }
        
        if hours_worked <= 0:
            return result
        
        # Проверка превышения максимального рабочего дня
        if hours_worked > self.MAX_DAILY_HOURS:
            warning = (f"Сотрудник {self.employee.get_full_name()} превысил максимальный "
                      f"рабочий день: {hours_worked}ч > {self.MAX_DAILY_HOURS}ч")
            self.warnings.append(warning)
            logger.warning(warning)
        
        # ИСПРАВЛЕНО: Определение обычных часов в зависимости от типа смены
        if is_night_shift:
            # Ночная смена имеет макс. 7 обычных часов
            max_regular_hours = self.NIGHT_SHIFT_MAX_REGULAR_HOURS
        else:
            # Дневная смена - используем 8.6 часов как базу (израильский стандарт)
            max_regular_hours = Decimal('8.6')
        
        regular_hours = min(hours_worked, max_regular_hours)
        result['regular_hours'] = regular_hours
        
        # ИСПРАВЛЕНО: Расчёт обычной оплаты
        if is_special_day:
            # Работа в праздник/шабат получает 150% за все часы
            result['regular_pay'] = regular_hours * base_rate * self.HOLIDAY_RATE
        else:
            result['regular_pay'] = regular_hours * base_rate
        
        # ИСПРАВЛЕНО: Сверхурочные часы
        if hours_worked > max_regular_hours:
            overtime_total = hours_worked - max_regular_hours
            
            if is_special_day:
                # ИСПРАВЛЕНО: Коэффициенты для сверхурочных в праздник/шабат
                # Первые 2 часа сверхурочных: 175% (150% базовый + 25% сверхурочный)
                overtime_rate_1 = base_rate * Decimal('1.75')
                overtime_hours_1 = min(overtime_total, Decimal('2'))
                result['overtime_hours_1'] = overtime_hours_1
                result['overtime_pay_1'] = overtime_hours_1 * overtime_rate_1
                
                # Дополнительные сверхурочные: 200% (150% базовый + 50% сверхурочный)
                if overtime_total > 2:
                    overtime_rate_2 = base_rate * Decimal('2.0')
                    overtime_hours_2 = overtime_total - Decimal('2')
                    result['overtime_hours_2'] = overtime_hours_2
                    result['overtime_pay_2'] = overtime_hours_2 * overtime_rate_2
            else:
                # ИСПРАВЛЕНО: Обычные дневные коэффициенты сверхурочных
                # Первые 2 часа сверхурочных: 125%
                overtime_rate_1 = base_rate * self.OVERTIME_RATE_1
                overtime_hours_1 = min(overtime_total, Decimal('2'))
                result['overtime_hours_1'] = overtime_hours_1
                result['overtime_pay_1'] = overtime_hours_1 * overtime_rate_1
                
                # Дополнительные сверхурочные: 150%
                if overtime_total > 2:
                    overtime_rate_2 = base_rate * self.OVERTIME_RATE_2
                    overtime_hours_2 = overtime_total - Decimal('2')
                    result['overtime_hours_2'] = overtime_hours_2
                    result['overtime_pay_2'] = overtime_hours_2 * overtime_rate_2
        
        result['total_pay'] = result['regular_pay'] + result['overtime_pay_1'] + result['overtime_pay_2']
        return result
    
    def calculate_daily_pay(self, work_log):
        """
        ИСПРАВЛЕНО: Расчёт оплаты за один рабочий день с учётом особых дней
        
        Args:
            work_log (WorkLog): Запись о рабочем дне
            
        Returns:
            dict: Детализированный расчёт оплаты за день
        """
        work_date = work_log.check_in.date()
        hours_worked = work_log.get_total_hours()
        base_rate = self.salary.hourly_rate or Decimal('0')
        
        result = {
            'date': work_date,
            'hours_worked': hours_worked,
            'is_holiday': False,
            'is_sabbath': False,
            'is_night_shift': False,
            'night_hours': Decimal('0'),
            'holiday_name': None,
            'compensatory_day_created': False,
            'regular_pay': Decimal('0'),
            'overtime_pay': Decimal('0'),
            'special_day_bonus': Decimal('0'),
            'total_pay': Decimal('0'),
            'breakdown': {}
        }
        
        # ИСПРАВЛЕНО: Проверка ночной смены
        is_night, night_hours = self.is_night_shift(work_log)
        result['is_night_shift'] = is_night
        result['night_hours'] = night_hours
        
        # Проверка работы в праздник
        holiday = Holiday.objects.filter(date=work_date, is_holiday=True, is_shabbat=False).first()
        if holiday:
            result['is_holiday'] = True
            result['holiday_name'] = holiday.name
            
            # Создание компенсационного дня
            created, _ = self.create_compensatory_day(work_date, 'holiday', hours_worked)
            result['compensatory_day_created'] = created
            
            # Расчёт оплаты по праздничным коэффициентам
            pay_breakdown = self.calculate_overtime_pay(hours_worked, base_rate, 
                                                       is_special_day=True, is_night_shift=is_night)
            result['breakdown'] = pay_breakdown
            result['total_pay'] = pay_breakdown['total_pay']
            
            return result
        
        # ИСПРАВЛЕНО: Проверка работы в шабат
        is_sabbath, sabbath_type, sabbath_info = self.is_sabbath_work(work_log.check_in)
        if is_sabbath:
            result['is_sabbath'] = True
            result['sabbath_type'] = sabbath_type
            
            # Создание компенсационного дня
            created, _ = self.create_compensatory_day(work_date, 'shabbat', hours_worked)
            result['compensatory_day_created'] = created
            
            # Расчёт оплаты по шабатным коэффициентам
            pay_breakdown = self.calculate_overtime_pay(hours_worked, base_rate, 
                                                       is_special_day=True, is_night_shift=is_night)
            result['breakdown'] = pay_breakdown
            result['total_pay'] = pay_breakdown['total_pay']
            
            return result
        
        # Расчёт обычного рабочего дня
        pay_breakdown = self.calculate_overtime_pay(hours_worked, base_rate, 
                                                   is_special_day=False, is_night_shift=is_night)
        result['breakdown'] = pay_breakdown
        result['total_pay'] = pay_breakdown['total_pay']
        
        return result
    
    def create_compensatory_day(self, work_date, reason, work_hours=None):
        """
        ИСПРАВЛЕНО: Создание компенсационного дня за работу в праздник или шабат
        
        Args:
            work_date (date): Дата работы
            reason (str): 'holiday' или 'shabbat'
            work_hours (Decimal, optional): Отработанные часы
            
        Returns:
            tuple: (created, compensatory_day)
        """
        try:
            # Проверяем, существует ли уже компенсационный день
            existing = CompensatoryDay.objects.filter(
                employee=self.employee,
                date_earned=work_date,
                reason=reason
            ).first()
            
            if existing:
                logger.debug(f"Компенсационный день уже существует для {self.employee.get_full_name()} "
                           f"на {work_date} (причина: {reason})")
                return False, existing
            
            # Создаём новый компенсационный день
            comp_day = CompensatoryDay.objects.create(
                employee=self.employee,
                date_earned=work_date,
                reason=reason
            )
            
            logger.info(f"Создан компенсационный день для {self.employee.get_full_name()} "
                       f"на {work_date} (причина: {reason})"
                       + (f" - {work_hours}ч отработано" if work_hours else ""))
            
            return True, comp_day
            
        except Exception as e:
            error_msg = f"Ошибка создания компенсационного дня для {self.employee.get_full_name()}: {e}"
            self.calculation_errors.append(error_msg)
            logger.error(error_msg)
            return False, None
    
    def calculate_monthly_salary(self):
        """
        ИСПРАВЛЕНО: Расчёт полной месячной зарплаты со всеми компонентами
        
        Returns:
            dict: Комплексный расчёт зарплаты
        """
        # ИСПРАВЛЕНО: Получение рабочих логов с правильной фильтрацией
        work_logs = self.get_work_logs_for_month()
        
        result = {
            'employee': self.employee.get_full_name(),
            'period': f"{self.year}-{self.month:02d}",
            'calculation_type': self.salary.calculation_type,
            'currency': self.salary.currency,
            'base_hourly_rate': self.salary.hourly_rate,
            'daily_calculations': [],
            'total_hours': Decimal('0'),
            'regular_hours': Decimal('0'),
            'overtime_hours': Decimal('0'),
            'holiday_hours': Decimal('0'),
            'sabbath_hours': Decimal('0'),
            'total_gross_pay': Decimal('0'),
            'compensatory_days_earned': 0,
            'legal_violations': [],
            'warnings': [],
            'errors': self.calculation_errors,
            'minimum_wage_applied': False,
            'work_sessions_count': work_logs.count(),
            'worked_days': 0
        }
        
        if not work_logs.exists():
            result['note'] = 'Нет рабочих логов для этого периода'
            logger.info(f"Нет рабочих логов для {self.employee.get_full_name()} в {self.year}-{self.month:02d}")
            return result
        
        # ИСПРАВЛЕНО: Расчёт оплаты для каждого рабочего дня
        for log in work_logs:
            daily_calc = self.calculate_daily_pay(log)
            result['daily_calculations'].append(daily_calc)
            
            # Накопление итогов
            result['total_hours'] += daily_calc['hours_worked']
            result['total_gross_pay'] += daily_calc['total_pay']
            
            if daily_calc['breakdown']:
                # ИСПРАВЛЕНО: Для обычных дней добавляем к обычным часам
                if not daily_calc['is_holiday'] and not daily_calc['is_sabbath']:
                    result['regular_hours'] += daily_calc['breakdown'].get('regular_hours', Decimal('0'))
                    # Считаем сверхурочные ТОЛЬКО для обычных рабочих дней
                    result['overtime_hours'] += (
                        daily_calc['breakdown'].get('overtime_hours_1', Decimal('0')) +
                        daily_calc['breakdown'].get('overtime_hours_2', Decimal('0'))
                    )
            
            if daily_calc['is_holiday']:
                result['holiday_hours'] += daily_calc['hours_worked']
            elif daily_calc['is_sabbath']:
                result['sabbath_hours'] += daily_calc['hours_worked']
                
            if daily_calc['compensatory_day_created']:
                result['compensatory_days_earned'] += 1
        
        # ИСПРАВЛЕНО: Подсчёт отработанных дней (уникальные даты)
        worked_days = len(set(log.check_in.date() for log in work_logs))
        result['worked_days'] = worked_days
        
        # Проверка соответствия законодательству
        violations = self.validate_weekly_limits(work_logs)
        result['legal_violations'] = violations
        result['warnings'] = self.warnings
        
        # ИСПРАВЛЕНО: Применение минимальной зарплаты
        if (self.salary.currency == 'ILS' and 
            result['total_gross_pay'] < self.MINIMUM_WAGE_ILS and
            result['total_hours'] >= 186):  # Примерно полный рабочий месяц
            
            result['original_gross_pay'] = result['total_gross_pay']
            result['total_gross_pay'] = self.MINIMUM_WAGE_ILS
            result['minimum_wage_applied'] = True
            result['minimum_wage_supplement'] = self.MINIMUM_WAGE_ILS - result['original_gross_pay']
        
        # Округление финальных сумм
        result['total_gross_pay'] = round(result['total_gross_pay'], 2)
        result['total_hours'] = round(result['total_hours'], 2)
        result['regular_hours'] = round(result['regular_hours'], 2)
        result['overtime_hours'] = round(result['overtime_hours'], 2)
        result['holiday_hours'] = round(result['holiday_hours'], 2)
        result['sabbath_hours'] = round(result['sabbath_hours'], 2)
        
        logger.info(f"✅ Расчёт зарплаты завершён для {self.employee.get_full_name()}: "
                   f"{result['total_gross_pay']}₪ за {result['total_hours']}ч")
        
        return result
    
    def validate_weekly_limits(self, work_logs):
        """
        ИСПРАВЛЕНО: Проверка соблюдения недельных ограничений по израильскому трудовому праву
        
        Args:
            work_logs (QuerySet): Рабочие логи для месяца
            
        Returns:
            list: Список найденных нарушений
        """
        violations = []
        
        # Группируем рабочие логи по неделям
        weeks = {}
        for log in work_logs:
            # Получаем понедельник недели (начало рабочей недели)
            monday = log.check_in.date() - timedelta(days=log.check_in.weekday())
            if monday not in weeks:
                weeks[monday] = []
            weeks[monday].append(log)
        
        # Проверяем каждую неделю
        for week_start, week_logs in weeks.items():
            week_end = week_start + timedelta(days=6)
            total_hours = sum(log.get_total_hours() for log in week_logs)
            
            regular_hours = min(total_hours, self.MAX_WEEKLY_REGULAR_HOURS)
            overtime_hours = max(Decimal('0'), total_hours - self.MAX_WEEKLY_REGULAR_HOURS)
            
            # Проверка максимального недельного времени (42 обычных + 16 сверхурочных = 58 всего)
            max_total = self.MAX_WEEKLY_REGULAR_HOURS + self.MAX_WEEKLY_OVERTIME_HOURS
            if total_hours > max_total:
                violation = {
                    'type': 'weekly_hours_exceeded',
                    'week_start': week_start,
                    'week_end': week_end,
                    'total_hours': total_hours,
                    'max_allowed': max_total,
                    'excess_hours': total_hours - max_total
                }
                violations.append(violation)
                
            # Проверка максимальных сверхурочных часов
            elif overtime_hours > self.MAX_WEEKLY_OVERTIME_HOURS:
                violation = {
                    'type': 'overtime_exceeded',
                    'week_start': week_start,
                    'week_end': week_end,
                    'overtime_hours': overtime_hours,
                    'max_overtime': self.MAX_WEEKLY_OVERTIME_HOURS,
                    'excess_overtime': overtime_hours - self.MAX_WEEKLY_OVERTIME_HOURS
                }
                violations.append(violation)
        
        return violations
    
    def get_detailed_breakdown(self):
        """
        ИСПРАВЛЕНО: Получение детализированного разбора по типам работы для максимальной прозрачности
        
        Returns:
            dict: Детализированный разбор с отдельными категориями для отображения в UI
        """
        # Сначала получаем стандартный месячный расчёт
        standard_result = self.calculate_monthly_salary()
        
        # Инициализируем детализированный разбор
        breakdown = {
            'employee': self.employee.get_full_name(),
            'period': f"{self.year}-{self.month:02d}",
            'hourly_rate': float(self.salary.hourly_rate) if self.salary.hourly_rate else 0,
            'currency': self.salary.currency,
            
            # Детализированные категории
            'regular_hours': 0.0,
            'regular_pay': 0.0,
            
            'overtime_day_hours': 0.0,
            'overtime_day_pay': 0.0,
            
            'overtime_night_hours': 0.0,
            'overtime_night_pay': 0.0,
            
            # ИСПРАВЛЕНО: Разбор сверхурочных по коэффициентам
            'overtime_125_hours': 0.0,
            'overtime_125_pay': 0.0,
            'overtime_150_hours': 0.0,
            'overtime_150_pay': 0.0,
            
            'sabbath_regular_hours': 0.0,
            'sabbath_regular_pay': 0.0,
            
            'sabbath_overtime_hours': 0.0,
            'sabbath_overtime_pay': 0.0,
            
            'holiday_regular_hours': 0.0,
            'holiday_regular_pay': 0.0,
            
            'holiday_overtime_hours': 0.0,
            'holiday_overtime_pay': 0.0,
            
            'total_hours': 0.0,
            'total_pay': 0.0,
            
            'compensatory_days': standard_result.get('compensatory_days_earned', 0),
            'legal_violations': standard_result.get('legal_violations', []),
            'warnings': standard_result.get('warnings', [])
        }
        
        # Обрабатываем каждый дневной расчёт
        for daily_calc in standard_result.get('daily_calculations', []):
            hours = daily_calc['hours_worked']
            is_night = daily_calc['is_night_shift']
            is_sabbath = daily_calc['is_sabbath']
            is_holiday = daily_calc['is_holiday']
            
            if daily_calc['breakdown']:
                regular_hours = daily_calc['breakdown'].get('regular_hours', 0)
                overtime_hours_1 = daily_calc['breakdown'].get('overtime_hours_1', 0)
                overtime_hours_2 = daily_calc['breakdown'].get('overtime_hours_2', 0)
                total_overtime = overtime_hours_1 + overtime_hours_2
                
                regular_pay = daily_calc['breakdown'].get('regular_pay', 0)
                overtime_pay = daily_calc['breakdown'].get('overtime_pay_1', 0) + daily_calc['breakdown'].get('overtime_pay_2', 0)
                
                if is_sabbath:
                    # Работа в шабат
                    if total_overtime > 0:
                        # Есть сверхурочные в шабат
                        breakdown['sabbath_regular_hours'] += float(regular_hours)
                        breakdown['sabbath_regular_pay'] += float(regular_pay)
                        breakdown['sabbath_overtime_hours'] += float(total_overtime)
                        breakdown['sabbath_overtime_pay'] += float(overtime_pay)
                        
                        # ИСПРАВЛЕНО: Добавляем разбор сверхурочных по коэффициентам для работы в шабат
                        # Сверхурочные в шабат: 175% за первые 2 часа, 200% за дополнительные
                        overtime_175_hours = float(overtime_hours_1)  # Первые 2 часа по 175%
                        overtime_200_hours = float(overtime_hours_2)  # Дополнительные часы по 200%
                        overtime_175_pay = float(daily_calc['breakdown'].get('overtime_pay_1', 0))
                        overtime_200_pay = float(daily_calc['breakdown'].get('overtime_pay_2', 0))
                        
                        # Для шабата отслеживаем как специальные коэффициенты
                        breakdown['overtime_125_hours'] += overtime_175_hours  # Отображается как 175%
                        breakdown['overtime_125_pay'] += overtime_175_pay
                        breakdown['overtime_150_hours'] += overtime_200_hours  # Отображается как 200%
                        breakdown['overtime_150_pay'] += overtime_200_pay
                    else:
                        # Все часы - обычные шабатные часы
                        breakdown['sabbath_regular_hours'] += float(hours)
                        breakdown['sabbath_regular_pay'] += float(daily_calc['total_pay'])
                        
                elif is_holiday:
                    # Работа в праздник
                    if total_overtime > 0:
                        # Есть сверхурочные в праздник
                        breakdown['holiday_regular_hours'] += float(regular_hours)
                        breakdown['holiday_regular_pay'] += float(regular_pay)
                        breakdown['holiday_overtime_hours'] += float(total_overtime)
                        breakdown['holiday_overtime_pay'] += float(overtime_pay)
                        
                        # Разбор сверхурочных по коэффициентам для работы в праздник
                        overtime_175_hours = float(overtime_hours_1)  # Первые 2 часа по 175%
                        overtime_200_hours = float(overtime_hours_2)  # Дополнительные часы по 200%
                        overtime_175_pay = float(daily_calc['breakdown'].get('overtime_pay_1', 0))
                        overtime_200_pay = float(daily_calc['breakdown'].get('overtime_pay_2', 0))
                        
                        breakdown['overtime_125_hours'] += overtime_175_hours
                        breakdown['overtime_125_pay'] += overtime_175_pay
                        breakdown['overtime_150_hours'] += overtime_200_hours
                        breakdown['overtime_150_pay'] += overtime_200_pay
                    else:
                        # Все часы - обычные праздничные часы
                        breakdown['holiday_regular_hours'] += float(hours)
                        breakdown['holiday_regular_pay'] += float(daily_calc['total_pay'])
                        
                else:
                    # Обычный рабочий день
                    breakdown['regular_hours'] += float(regular_hours)
                    breakdown['regular_pay'] += float(regular_pay)
                    
                    if total_overtime > 0:
                        # ИСПРАВЛЕНО: Добавляем разбор сверхурочных по коэффициентам для обычных дней
                        overtime_125_hours = float(overtime_hours_1)  # Первые 2 часа по 125%
                        overtime_150_hours = float(overtime_hours_2)  # Дополнительные часы по 150%
                        overtime_125_pay = float(daily_calc['breakdown'].get('overtime_pay_1', 0))
                        overtime_150_pay = float(daily_calc['breakdown'].get('overtime_pay_2', 0))
                        
                        breakdown['overtime_125_hours'] += overtime_125_hours
                        breakdown['overtime_125_pay'] += overtime_125_pay
                        breakdown['overtime_150_hours'] += overtime_150_hours
                        breakdown['overtime_150_pay'] += overtime_150_pay
                        
                        if is_night:
                            # Ночная смена, сверхурочные
                            breakdown['overtime_night_hours'] += float(total_overtime)
                            breakdown['overtime_night_pay'] += float(overtime_pay)
                        else:
                            # Дневная смена, сверхурочные
                            breakdown['overtime_day_hours'] += float(total_overtime)
                            breakdown['overtime_day_pay'] += float(overtime_pay)
            
            breakdown['total_hours'] += float(hours)
            breakdown['total_pay'] += float(daily_calc['total_pay'])
        
        # Округляем значения для отображения
        for key in breakdown:
            if isinstance(breakdown[key], float):
                breakdown[key] = round(breakdown[key], 2)
        
        return breakdown