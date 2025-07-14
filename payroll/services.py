"""
Enhanced payroll calculation service with external API integration

Combines:
1. Current working logic of PayrollCalculationService
2. Integration with SunriseSunsetService for precise Sabbath times  
3. Integration with HebcalService for Jewish holidays
4. API integration monitoring and fallback mechanisms
"""

from django.utils import timezone
from django.db import models
from datetime import datetime, date, timedelta
from decimal import Decimal
import logging
import calendar
import pytz

from worktime.models import WorkLog
from payroll.models import Salary, CompensatoryDay
from integrations.models import Holiday
from integrations.services.sunrise_sunset_service import SunriseSunsetService
from integrations.services.hebcal_service import HebcalService
from core.logging_utils import safe_log_employee

logger = logging.getLogger(__name__)


class EnhancedPayrollCalculationService:
    """
    ENHANCED payroll calculation service with full external API integration
    
    Preserves all current working logic and adds:
    - Precise Sabbath times via SunriseSunsetService
    - Automatic holiday synchronization via HebcalService
    - API integration monitoring
    - Fallback to existing logic when APIs are unavailable
    """
    
    # Israeli labor law constants for 5-day work week
    MAX_DAILY_HOURS = Decimal('12')
    MAX_WEEKLY_REGULAR_HOURS = Decimal('42')  # 5-day week
    MAX_WEEKLY_OVERTIME_HOURS = Decimal('16')
    MINIMUM_WAGE_ILS = Decimal('5300')
    MONTHLY_WORK_HOURS = Decimal('182')
    
    # Daily hour norms for 5-day week
    REGULAR_DAILY_HOURS = Decimal('8.6')  # 4 days per week
    SHORT_DAILY_HOURS = Decimal('7.6')    # 1 day per week (usually Friday)
    
    # Constants for night shifts
    NIGHT_SHIFT_START = 22  # 22:00
    NIGHT_SHIFT_END = 6     # 06:00
    NIGHT_SHIFT_MAX_REGULAR_HOURS = Decimal('7')  # Max regular hours for night shift
    
    # Payment coefficients
    OVERTIME_RATE_1 = Decimal('1.25')  # First 2 overtime hours
    OVERTIME_RATE_2 = Decimal('1.50')  # Additional overtime hours
    HOLIDAY_RATE = Decimal('1.50')     # Holiday work coefficient
    SABBATH_RATE = Decimal('1.50')     # Sabbath work coefficient
    
    def __init__(self, employee, year, month, fast_mode=False):
        """
        Initialize enhanced payroll calculation
        
        Args:
            employee (Employee): Employee object
            year (int): Year for calculation
            month (int): Month for calculation
            fast_mode (bool): Fast mode without external APIs for list views
        """
        self.employee = employee
        self.year = year
        self.month = month
        self.salary = employee.salary_info
        self.calculation_errors = []
        self.warnings = []
        self.fast_mode = fast_mode
        
        # Debug logging for fast mode
        logger.info(f"🚀 EnhancedPayrollCalculationService initialized with fast_mode={self.fast_mode}")
        
        # Coordinates for Israel (can be made configurable)
        self.default_lat = 31.7683  # Jerusalem
        self.default_lng = 35.2137
        
        # Timezone for Israel
        self.israel_tz = pytz.timezone('Asia/Jerusalem')
        
        # API usage tracking
        self.api_usage = {
            'sunrise_sunset_calls': 0,
            'hebcal_calls': 0,
            'precise_sabbath_times': 0,
            'api_holidays_found': 0,
            'fallback_calculations': 0
        }
        
    def get_work_logs_for_month(self):
        """
        ИСПРАВЛЕНО: Корректная фильтрация рабочих логов для месяца
        
        Returns:
            QuerySet: Рабочие логи для указанного месяца
        """
        # Вычисляем точные границы месяца
        start_date = date(self.year, self.month, 1)
        _, last_day = calendar.monthrange(self.year, self.month)
        end_date = date(self.year, self.month, last_day)
        
        # ИСПРАВЛЕНО: более точная фильтрация
        work_logs = WorkLog.objects.filter(
            employee=self.employee,
            check_out__isnull=False  # Только завершённые сессии
        ).filter(
            # Сессия пересекается с месяцем
            models.Q(check_in__date__lte=end_date) & 
            models.Q(check_out__date__gte=start_date)
        ).order_by('check_in')
        
        logger.info("📊 Найдено рабочих сессий для сотрудника", extra={
            **safe_log_employee(self.employee, "payroll_sessions"),
            "session_count": work_logs.count(),
            "period": f"{self.year}-{self.month:02d}"
        })
                   f"в {self.year}-{self.month:02d}")
        
        return work_logs
    
    def is_sabbath_work_precise(self, work_datetime):
        """
        УЛУЧШЕНО: Точное определение работы в шабат с использованием SunriseSunsetService
        
        Args:
            work_datetime (datetime): Время начала работы
            
        Returns:
            tuple: (is_sabbath, sabbath_type, sabbath_info)
        """
        work_date = work_datetime.date()
        work_time = work_datetime.time()
        shabbat_times = None  # Initialize to prevent errors
        
        # 1. Check registered sabbath in database first
        sabbath_holiday = Holiday.objects.filter(
            date=work_date,
            is_shabbat=True
        ).first()
        
        if sabbath_holiday:
            # Используем точные времена из базы данных если они есть
            if sabbath_holiday.start_time and sabbath_holiday.end_time:
                # Конвертируем в израильский timezone
                start_time_israel = sabbath_holiday.start_time.astimezone(self.israel_tz)
                end_time_israel = sabbath_holiday.end_time.astimezone(self.israel_tz)
                
                # Проверяем, попадает ли работа в период шабата
                if work_datetime.tzinfo is None:
                    work_datetime = timezone.make_aware(work_datetime)
                work_datetime_israel = work_datetime.astimezone(self.israel_tz)
                
                if start_time_israel <= work_datetime_israel <= end_time_israel:
                    return True, 'registered_sabbath_precise', sabbath_holiday
            else:
                # Нет точных времён, используем дату
                return True, 'registered_sabbath', sabbath_holiday
        
        # 2. Use SunriseSunsetService for precise calculation (only if not in fast mode)
        if not self.fast_mode:
            logger.info(f"🚀 Using SunriseSunsetService for precise sabbath calculation (fast_mode={self.fast_mode})")
            try:
                self.api_usage['sunrise_sunset_calls'] += 1
                
                if work_date.weekday() == 4:  # Пятница
                    shabbat_times = SunriseSunsetService.get_shabbat_times(work_date)
                
                if not shabbat_times.get('is_estimated', True):
                    # У нас есть точные времена от API
                    self.api_usage['precise_sabbath_times'] += 1
                    
                    shabbat_start_str = shabbat_times['start']
                    
                    # Парсим UTC время от API
                    try:
                        if shabbat_start_str.endswith('Z'):
                            shabbat_start_str = shabbat_start_str.replace('Z', '+00:00')
                        shabbat_start_utc = datetime.fromisoformat(shabbat_start_str)
                        
                        # Конвертируем в израильский timezone
                        if shabbat_start_utc.tzinfo is None:
                            shabbat_start_utc = pytz.UTC.localize(shabbat_start_utc)
                        
                        shabbat_start_local = shabbat_start_utc.astimezone(self.israel_tz)
                        
                        # Обеспечиваем timezone-aware для work_datetime
                        if work_datetime.tzinfo is None:
                            work_datetime = timezone.make_aware(work_datetime)
                        work_local = work_datetime.astimezone(self.israel_tz)
                        
                        if work_local >= shabbat_start_local:
                            logger.info(f"✅ Точная работа в шабат обнаружена на {work_date}: "
                                      f"работа в {work_local.strftime('%H:%M')}, "
                                      f"шабат начинается в {shabbat_start_local.strftime('%H:%M')}")
                            return True, 'friday_evening_precise', shabbat_times
                            
                    except Exception as parse_error:
                        logger.warning(f"Ошибка парсинга точного времени шабата для {work_date}: {parse_error}")
                        self.api_usage['fallback_calculations'] += 1
                        # Fallback к простой проверке времени
                        if work_datetime.time().hour >= 18:
                            return True, 'friday_evening_fallback', None
                else:
                    # Используем примерное время (18:00)
                    self.api_usage['fallback_calculations'] += 1
                    if work_datetime.time().hour >= 18:
                        return True, 'friday_evening_estimated', shabbat_times
                        
                
                if work_date.weekday() == 5:  # Суббота
                    # Для субботы проверяем окончание шабата
                    try:
                        # Получаем времена шабата для пятницы (которая началась в этот шабат)
                        friday_date = work_date - timedelta(days=1)
                        shabbat_times = SunriseSunsetService.get_shabbat_times(friday_date)
                        
                        if not shabbat_times.get('is_estimated', True):
                            self.api_usage['precise_sabbath_times'] += 1
                            shabbat_end_str = shabbat_times['end']
                            
                            try:
                                if shabbat_end_str.endswith('Z'):
                                    shabbat_end_str = shabbat_end_str.replace('Z', '+00:00')
                                shabbat_end_utc = datetime.fromisoformat(shabbat_end_str)
                                
                                if shabbat_end_utc.tzinfo is None:
                                    shabbat_end_utc = pytz.UTC.localize(shabbat_end_utc)
                                
                                shabbat_end_local = shabbat_end_utc.astimezone(self.israel_tz)
                                
                                if work_datetime.tzinfo is None:
                                    work_datetime = timezone.make_aware(work_datetime)
                                work_local = work_datetime.astimezone(self.israel_tz)
                                
                                if work_local <= shabbat_end_local:
                                    logger.info(f"✅ Точная работа в шабат обнаружена на {work_date}: "
                                              f"работа в {work_local.strftime('%H:%M')}, "
                                              f"шабат заканчивается в {shabbat_end_local.strftime('%H:%M')}")
                                    return True, 'saturday_precise', shabbat_times
                            except Exception as parse_error:
                                logger.warning(f"Ошибка парсинга времени окончания шабата для {work_date}: {parse_error}")
                        
                        # Fallback: вся суббота считается шабатом
                        self.api_usage['fallback_calculations'] += 1
                        return True, 'saturday_all_day', shabbat_times
                        
                    except Exception as api_error:
                        logger.warning(f"Ошибка SunriseSunsetService для субботы {work_date}: {api_error}")
                        self.api_usage['fallback_calculations'] += 1
                        # Fallback: вся суббота считается шабатом
                        return True, 'saturday_fallback', None
                    
            except Exception as e:
                logger.warning(f"Ошибка использования SunriseSunsetService для {work_date}: {e}")
                self.api_usage['fallback_calculations'] += 1
        
        # Fallback к простой проверке (или быстрый режим)
        if work_date.weekday() == 4 and work_datetime.time().hour >= 18:
            return True, 'friday_evening_simple', None
        elif work_date.weekday() == 5:
            return True, 'saturday_simple', None
                
        return False, None, None
    
    def is_holiday_work_enhanced(self, work_date):
        """
        УЛУЧШЕНО: Проверка работы в праздник с использованием HebcalService
        
        Args:
            work_date (date): Дата работы
            
        Returns:
            Holiday object или None
        """
        # 1. Проверяем базу данных
        holiday = Holiday.objects.filter(
            date=work_date,
            is_holiday=True,
            is_shabbat=False  # Исключаем шабаты (обрабатываются отдельно)
        ).first()
        
        if holiday:
            logger.info(f"📅 Найден зарегистрированный праздник: {holiday.name} на {work_date}")
            return holiday
        
        # 2. If not in database, check via HebcalService (only if not in fast mode)
        if not self.fast_mode:
            logger.info(f"🚀 Using HebcalService for holiday lookup (fast_mode={self.fast_mode})")
            try:
                self.api_usage['hebcal_calls'] += 1
                
                # Получаем праздники для года (с кэшированием)
                holidays_data = HebcalService.fetch_holidays(
                    year=work_date.year, 
                    month=work_date.month,
                    use_cache=True
                )
                
                # Ищем праздник на эту дату
                for holiday_data in holidays_data:
                    holiday_date_str = holiday_data.get("date")
                    if holiday_date_str:
                        try:
                            holiday_date = datetime.strptime(holiday_date_str, "%Y-%m-%d").date()
                            if holiday_date == work_date:
                                title = holiday_data.get("title", "Unknown Holiday")
                                self.api_usage['api_holidays_found'] += 1
                                logger.info(f"📅 Найден праздник через HebcalService: {title} на {work_date}")
                                
                                # Создаём временный объект Holiday для возврата
                                temp_holiday = type('Holiday', (), {
                                    'name': title,
                                    'date': work_date,
                                    'is_holiday': True,
                                    'is_shabbat': holiday_data.get('subcat') == 'shabbat'
                                })()
                                
                                return temp_holiday
                        except ValueError:
                            continue
                        
            except Exception as api_error:
                logger.warning(f"Ошибка HebcalService для {work_date}: {api_error}")
        
        return None
    
    def sync_missing_holidays_for_month(self):
        """
        НОВОЕ: Синхронизирует отсутствующие праздники для расчётного месяца
        """
        # В быстром режиме пропускаем синхронизацию
        if self.fast_mode:
            logger.info(f"⚡ Быстрый режим: пропускаем синхронизацию праздников для {self.year}-{self.month:02d}")
            return
            
        try:
            logger.info(f"🔄 Синхронизация праздников для {self.year}-{self.month:02d}")
            
            # Проверяем, есть ли праздники в базе для этого месяца
            existing_holidays = Holiday.objects.filter(
                date__year=self.year,
                date__month=self.month
            ).count()
            
            if existing_holidays == 0:
                logger.info("Праздники не найдены в базе, синхронизируем из HebcalService...")
                
                # Синхронизируем праздники для года
                created_count, updated_count = HebcalService.sync_holidays_to_db(self.year)
                
                if created_count > 0 or updated_count > 0:
                    logger.info(f"✅ Синхронизированы праздники: {created_count} создано, {updated_count} обновлено")
                else:
                    logger.warning("Праздники не были синхронизированы")
            else:
                logger.debug(f"Найдено {existing_holidays} существующих праздников для {self.year}-{self.month:02d}")
                
        except Exception as sync_error:
            logger.error(f"Ошибка синхронизации праздников: {sync_error}")
            # Не останавливаем расчёт зарплаты из-за ошибки синхронизации
    
    def is_night_shift(self, work_log):
        """
        Проверка ночной смены согласно израильскому праву
        """
        check_in = work_log.check_in
        check_out = work_log.check_out
        
        night_hours = Decimal('0')
        night_start = check_in.replace(hour=self.NIGHT_SHIFT_START, minute=0, second=0)
        night_end = check_in.replace(hour=self.NIGHT_SHIFT_END, minute=0, second=0)
        
        if night_end <= night_start:
            night_end += timedelta(days=1)
        
        if check_out > night_start and check_in < night_end:
            overlap_start = max(check_in, night_start)
            overlap_end = min(check_out, night_end)
            
            if overlap_end > overlap_start:
                night_hours = Decimal((overlap_end - overlap_start).total_seconds() / 3600)
        
        is_night = night_hours >= Decimal('2')
        return is_night, night_hours
    
    def calculate_overtime_pay(self, hours_worked, base_rate, is_special_day=False, is_night_shift=False):
        """
        ИСПРАВЛЕНО: Расчёт сверхурочной оплаты согласно израильскому трудовому праву
        """
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
        
        # Определение обычных часов в зависимости от типа смены
        if is_night_shift:
            max_regular_hours = self.NIGHT_SHIFT_MAX_REGULAR_HOURS
        else:
            max_regular_hours = Decimal('8.6')
        
        regular_hours = min(hours_worked, max_regular_hours)
        result['regular_hours'] = regular_hours
        
        # Расчёт обычной оплаты
        if is_special_day:
            # Работа в праздник/шабат получает 150% за все часы
            result['regular_pay'] = regular_hours * base_rate * self.HOLIDAY_RATE
        else:
            result['regular_pay'] = regular_hours * base_rate
        
        # Сверхурочные часы
        if hours_worked > max_regular_hours:
            overtime_total = hours_worked - max_regular_hours
            
            if is_special_day:
                # Коэффициенты для сверхурочных в праздник/шабат
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
                # Обычные дневные коэффициенты сверхурочных
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
    
    def calculate_daily_pay_enhanced(self, work_log):
        """
        УЛУЧШЕНО: Расчёт оплаты за день с полной интеграцией внешних сервисов
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
            'sabbath_type': None,
            'sabbath_info': None,
            'compensatory_day_created': False,
            'regular_pay': Decimal('0'),
            'overtime_pay': Decimal('0'),
            'special_day_bonus': Decimal('0'),
            'total_pay': Decimal('0'),
            'breakdown': {},
            'api_sources': []  # Отслеживание источников данных
        }
        
        # Проверка ночной смены
        is_night, night_hours = self.is_night_shift(work_log)
        result['is_night_shift'] = is_night
        result['night_hours'] = night_hours
        
        # УЛУЧШЕНО: Проверка работы в праздник с HebcalService
        holiday = self.is_holiday_work_enhanced(work_date)
        if holiday:
            result['is_holiday'] = True
            result['holiday_name'] = holiday.name
            result['api_sources'].append('hebcal_api' if not hasattr(holiday, 'id') else 'database')
            
            # Создание компенсационного дня
            created, _ = self.create_compensatory_day(work_date, 'holiday', hours_worked)
            result['compensatory_day_created'] = created
            
            # Расчёт оплаты по праздничным коэффициентам
            pay_breakdown = self.calculate_overtime_pay(
                hours_worked, base_rate, is_special_day=True, is_night_shift=is_night
            )
            result['breakdown'] = pay_breakdown
            result['total_pay'] = pay_breakdown['total_pay']
            
            logger.info(f"💰 Расчёт работы в праздник: {work_date} - {hours_worked}ч = ₪{result['total_pay']}")
            return result
        
        # УЛУЧШЕНО: Проверка работы в шабат с SunriseSunsetService
        is_sabbath, sabbath_type, sabbath_info = self.is_sabbath_work_precise(work_log.check_in)
        if is_sabbath:
            result['is_sabbath'] = True
            result['sabbath_type'] = sabbath_type
            result['sabbath_info'] = sabbath_info
            
            # Отслеживание источника данных о шабате
            if 'precise' in sabbath_type:
                result['api_sources'].append('sunrise_sunset_api')
            elif 'registered' in sabbath_type:
                result['api_sources'].append('database')
            else:
                result['api_sources'].append('fallback_calculation')
            
            # Создание компенсационного дня
            created, _ = self.create_compensatory_day(work_date, 'shabbat', hours_worked)
            result['compensatory_day_created'] = created
            
            # Расчёт оплаты по шабатным коэффициентам
            pay_breakdown = self.calculate_overtime_pay(
                hours_worked, base_rate, is_special_day=True, is_night_shift=is_night
            )
            result['breakdown'] = pay_breakdown
            result['total_pay'] = pay_breakdown['total_pay']
            
            logger.info(f"🕯️ Расчёт работы в шабат: {work_date} ({sabbath_type}) - {hours_worked}ч = ₪{result['total_pay']}")
            return result
        
        # Расчёт обычного рабочего дня
        pay_breakdown = self.calculate_overtime_pay(
            hours_worked, base_rate, is_special_day=False, is_night_shift=is_night
        )
        result['breakdown'] = pay_breakdown
        result['total_pay'] = pay_breakdown['total_pay']
        
        logger.debug(f"💼 Расчёт обычного дня: {work_date} - {hours_worked}ч = ₪{result['total_pay']}")
        return result
    
    def create_compensatory_day(self, work_date, reason, work_hours=None):
        """
        Создание компенсационного дня за работу в праздник или шабат
        """
        try:
            existing = CompensatoryDay.objects.filter(
                employee=self.employee,
                date_earned=work_date,
                reason=reason
            ).first()
            
            if existing:
                logger.debug("Компенсационный день уже существует", extra={
                    **safe_log_employee(self.employee, "compensatory_exists"),
                    "date": compensatory_date.isoformat()
                })
                           f"на {work_date} (причина: {reason})")
                return False, existing
            
            comp_day = CompensatoryDay.objects.create(
                employee=self.employee,
                date_earned=work_date,
                reason=reason
            )
            
            logger.info("Создан компенсационный день", extra={
                **safe_log_employee(self.employee, "compensatory_created"),
                "date": compensatory_date.isoformat(),
                "reason": reason
            })
                       f"на {work_date} (причина: {reason})"
                       + (f" - {work_hours}ч отработано" if work_hours else ""))
            
            return True, comp_day
            
        except Exception as e:
            error_msg = f"Ошибка создания компенсационного дня для {self.employee.get_full_name()}: {e}"
            self.calculation_errors.append(error_msg)
            logger.error(error_msg)
            return False, None
    
    def calculate_monthly_salary_enhanced(self):
        """
        УЛУЧШЕНО: Расчёт месячной зарплаты с полной интеграцией внешних API
        """
        # Синхронизируем праздники перед расчётом
        self.sync_missing_holidays_for_month()
        
        # Получаем рабочие логи
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
            'worked_days': 0,
            'api_integrations': {  # НОВОЕ: отслеживание использования API
                'sunrise_sunset_used': self.api_usage['sunrise_sunset_calls'] > 0,
                'hebcal_used': self.api_usage['hebcal_calls'] > 0,
                'precise_sabbath_times': self.api_usage['precise_sabbath_times'],
                'api_holidays_found': self.api_usage['api_holidays_found'],
                'fallback_calculations': self.api_usage['fallback_calculations']
            }
        }
        
        if not work_logs.exists():
            result['note'] = 'Нет рабочих логов для этого периода'
            logger.info(f"Нет рабочих логов для {self.employee.get_full_name()} в {self.year}-{self.month:02d}")
            return result
        
        # Расчёт оплаты для каждого рабочего дня с улучшенной интеграцией
        for log in work_logs:
            daily_calc = self.calculate_daily_pay_enhanced(log)
            result['daily_calculations'].append(daily_calc)
            
            # Накопление итогов
            result['total_hours'] += daily_calc['hours_worked']
            result['total_gross_pay'] += daily_calc['total_pay']
            
            # Накопление часов по типам
            if daily_calc['breakdown']:
                if not daily_calc['is_holiday'] and not daily_calc['is_sabbath']:
                    result['regular_hours'] += daily_calc['breakdown'].get('regular_hours', Decimal('0'))
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
        
        # Подсчёт отработанных дней
        worked_days = len(set(log.check_in.date() for log in work_logs))
        result['worked_days'] = worked_days
        
        # Проверка соответствия законодательству
        violations = self.validate_weekly_limits(work_logs)
        result['legal_violations'] = violations
        result['warnings'] = self.warnings
        
        # Special handling for monthly employees
        if self.salary.calculation_type == 'monthly':
            # For monthly employees, use base salary as total gross pay
            # Daily calculations are only for overtime and special day bonuses
            if self.salary.base_salary:
                base_monthly_pay = Decimal(str(self.salary.base_salary))
                overtime_and_bonuses = result['total_gross_pay']  # This is from daily calculations
                result['total_gross_pay'] = base_monthly_pay + overtime_and_bonuses
                result['base_salary'] = float(base_monthly_pay)
                result['overtime_bonus'] = float(overtime_and_bonuses)
                logger.info(f"Monthly employee {self.employee.get_full_name()}: "
                           f"Base ₪{base_monthly_pay} + Overtime/Bonuses ₪{overtime_and_bonuses} = "
                           f"Total ₪{result['total_gross_pay']}")
        
        # Apply minimum wage
        if (self.salary.currency == 'ILS' and 
            result['total_gross_pay'] < self.MINIMUM_WAGE_ILS and
            result['total_hours'] >= 186):
            
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
        
        # Логирование использования API
        api_info = result['api_integrations']
        logger.info(f"✅ Улучшенный расчёт зарплаты завершён для {self.employee.get_full_name()}: "
                   f"₪{result['total_gross_pay']} за {result['total_hours']}ч | "
                   f"APIs использованы: SunriseSunset={api_info['sunrise_sunset_used']}, "
                   f"Hebcal={api_info['hebcal_used']}, "
                   f"Точные времена={api_info['precise_sabbath_times']}")
        
        return result
    
    def validate_weekly_limits(self, work_logs):
        """
        Проверка соблюдения недельных ограничений по израильскому трудовому праву
        """
        violations = []
        
        weeks = {}
        for log in work_logs:
            monday = log.check_in.date() - timedelta(days=log.check_in.weekday())
            if monday not in weeks:
                weeks[monday] = []
            weeks[monday].append(log)
        
        for week_start, week_logs in weeks.items():
            week_end = week_start + timedelta(days=6)
            total_hours = sum(log.get_total_hours() for log in week_logs)
            
            regular_hours = min(total_hours, self.MAX_WEEKLY_REGULAR_HOURS)
            overtime_hours = max(Decimal('0'), total_hours - self.MAX_WEEKLY_REGULAR_HOURS)
            
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
        УЛУЧШЕНО: Получение детализированного разбора с API интеграциями
        """
        # Сначала получаем стандартный месячный расчёт
        standard_result = self.calculate_monthly_salary_enhanced()
        
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
            'warnings': standard_result.get('warnings', []),
            
            # НОВОЕ: информация об API интеграциях
            'api_integrations': standard_result.get('api_integrations', {})
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
                        breakdown['sabbath_regular_hours'] += float(regular_hours)
                        breakdown['sabbath_regular_pay'] += float(regular_pay)
                        breakdown['sabbath_overtime_hours'] += float(total_overtime)
                        breakdown['sabbath_overtime_pay'] += float(overtime_pay)
                        
                        # Разбор сверхурочных по коэффициентам для работы в шабат
                        overtime_175_hours = float(overtime_hours_1)  # Первые 2 часа по 175%
                        overtime_200_hours = float(overtime_hours_2)  # Дополнительные часы по 200%
                        overtime_175_pay = float(daily_calc['breakdown'].get('overtime_pay_1', 0))
                        overtime_200_pay = float(daily_calc['breakdown'].get('overtime_pay_2', 0))
                        
                        breakdown['overtime_125_hours'] += overtime_175_hours  # Отображается как 175%
                        breakdown['overtime_125_pay'] += overtime_175_pay
                        breakdown['overtime_150_hours'] += overtime_200_hours  # Отображается как 200%
                        breakdown['overtime_150_pay'] += overtime_200_pay
                    else:
                        breakdown['sabbath_regular_hours'] += float(hours)
                        breakdown['sabbath_regular_pay'] += float(daily_calc['total_pay'])
                        
                elif is_holiday:
                    # Работа в праздник
                    if total_overtime > 0:
                        breakdown['holiday_regular_hours'] += float(regular_hours)
                        breakdown['holiday_regular_pay'] += float(regular_pay)
                        breakdown['holiday_overtime_hours'] += float(total_overtime)
                        breakdown['holiday_overtime_pay'] += float(overtime_pay)
                        
                        # Разбор сверхурочных по коэффициентам для работы в праздник
                        overtime_175_hours = float(overtime_hours_1)
                        overtime_200_hours = float(overtime_hours_2)
                        overtime_175_pay = float(daily_calc['breakdown'].get('overtime_pay_1', 0))
                        overtime_200_pay = float(daily_calc['breakdown'].get('overtime_pay_2', 0))
                        
                        breakdown['overtime_125_hours'] += overtime_175_hours
                        breakdown['overtime_125_pay'] += overtime_175_pay
                        breakdown['overtime_150_hours'] += overtime_200_hours
                        breakdown['overtime_150_pay'] += overtime_200_pay
                    else:
                        breakdown['holiday_regular_hours'] += float(hours)
                        breakdown['holiday_regular_pay'] += float(daily_calc['total_pay'])
                        
                else:
                    # Обычный рабочий день
                    breakdown['regular_hours'] += float(regular_hours)
                    breakdown['regular_pay'] += float(regular_pay)
                    
                    if total_overtime > 0:
                        # Разбор сверхурочных по коэффициентам для обычных дней
                        overtime_125_hours = float(overtime_hours_1)  # Первые 2 часа по 125%
                        overtime_150_hours = float(overtime_hours_2)  # Дополнительные часы по 150%
                        overtime_125_pay = float(daily_calc['breakdown'].get('overtime_pay_1', 0))
                        overtime_150_pay = float(daily_calc['breakdown'].get('overtime_pay_2', 0))
                        
                        breakdown['overtime_125_hours'] += overtime_125_hours
                        breakdown['overtime_125_pay'] += overtime_125_pay
                        breakdown['overtime_150_hours'] += overtime_150_hours
                        breakdown['overtime_150_pay'] += overtime_150_pay
                        
                        if is_night:
                            breakdown['overtime_night_hours'] += float(total_overtime)
                            breakdown['overtime_night_pay'] += float(overtime_pay)
                        else:
                            breakdown['overtime_day_hours'] += float(total_overtime)
                            breakdown['overtime_day_pay'] += float(overtime_pay)
            
            breakdown['total_hours'] += float(hours)
            breakdown['total_pay'] += float(daily_calc['total_pay'])
        
        # Округляем значения для отображения
        for key in breakdown:
            if isinstance(breakdown[key], float):
                breakdown[key] = round(breakdown[key], 2)
        
        return breakdown


    def calculate_monthly_salary(self):
        """
        ОБРАТНАЯ СОВМЕСТИМОСТЬ: Вызывает улучшенный метод расчёта
        """
        return self.calculate_monthly_salary_enhanced()


# Создаём алиас для обратной совместимости, но с улучшенными возможностями
PayrollCalculationService = EnhancedPayrollCalculationService