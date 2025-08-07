"""
Enhanced payroll calculation service with external API integration

Combines:
1. Current working logic of PayrollCalculationService
2. Integration with SunriseSunsetService for precise Sabbath times
3. Integration with HebcalService for Jewish holidays
4. API integration monitoring and fallback mechanisms
5. FIXED: Proper calculation logic for monthly vs hourly employees
"""

import calendar
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytz

from django.db import models
from django.utils import timezone

from core.logging_utils import safe_log_employee
from integrations.models import Holiday
from integrations.services.hebcal_service import HebcalService
from integrations.services.sunrise_sunset_service import SunriseSunsetService
from payroll.models import (
    CompensatoryDay,
    DailyPayrollCalculation,
    MonthlyPayrollSummary,
    Salary,
)
from worktime.models import WorkLog

from .redis_cache_service import payroll_cache
from .shift_splitter import ShiftSplitter

logger = logging.getLogger(__name__)


class EnhancedPayrollCalculationService:
    """
    ENHANCED payroll calculation service with full external API integration

    FIXED: Proper separation of logic for monthly vs hourly employees:
    - Hourly employees: full daily pay calculation
    - Monthly employees: base salary + bonuses only (no double payment)
    """

    # Israeli labor law constants
    MAX_DAILY_HOURS = Decimal("12")
    MAX_WEEKLY_REGULAR_HOURS = Decimal("42")  # 5-day work week
    MAX_WEEKLY_OVERTIME_HOURS = Decimal("16")
    MINIMUM_WAGE_ILS = Decimal("5300")
    MONTHLY_WORK_HOURS = Decimal("182")  # Standard month for calculations

    # Daily hour norms
    REGULAR_DAILY_HOURS = Decimal("8.6")  # Regular day (4 days per week)
    SHORT_DAILY_HOURS = Decimal("7.6")  # Short day (usually Friday)
    NIGHT_SHIFT_MAX_REGULAR_HOURS = Decimal("7")  # Night shift norm

    # Night shift constants
    NIGHT_SHIFT_START = 22  # 22:00
    NIGHT_SHIFT_END = 6  # 06:00

    # Payment coefficients
    OVERTIME_RATE_125 = Decimal("1.25")  # First 2 overtime hours
    OVERTIME_RATE_150 = Decimal("1.50")  # Additional overtime hours
    HOLIDAY_RATE = Decimal("1.50")  # Holiday work coefficient
    SABBATH_RATE = Decimal("1.50")  # Sabbath work coefficient

    # Bonus rates for monthly employees (percentage above base)
    OVERTIME_BONUS_125 = Decimal("0.25")  # +25% for first 2 overtime hours
    OVERTIME_BONUS_150 = Decimal("0.50")  # +50% for additional overtime
    SPECIAL_DAY_BONUS = Decimal("0.50")  # +50% for holiday/sabbath work

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

        # ✅ НОВОЕ: Инициализируем кэш праздников для месяца
        self.holidays_cache = {}
        self._load_holidays_for_month()

        logger.info(
            f"🚀 EnhancedPayrollCalculationService initialized with fast_mode={self.fast_mode}"
        )

        # Coordinates for Israel (can be made configurable)
        self.default_lat = 31.7683  # Jerusalem
        self.default_lng = 35.2137

        # Timezone for Israel
        self.israel_tz = pytz.timezone("Asia/Jerusalem")

        # API usage tracking
        self.api_usage = {
            "sunrise_sunset_calls": 0,
            "hebcal_calls": 0,
            "precise_sabbath_times": 0,
            "api_holidays_found": 0,
            "fallback_calculations": 0,
            "redis_cache_hits": 0,
            "redis_cache_misses": 0,
        }

    def _load_holidays_for_month(self):
        """
        ✅ НОВОЕ: Загружаем все праздники для месяца одним запросом в кэш
        Это устраняет N+1 query problem для проверки праздников
        """
        import calendar

        start_date = date(self.year, self.month, 1)
        _, last_day = calendar.monthrange(self.year, self.month)
        end_date = date(self.year, self.month, last_day)

        try:
            # Используем Redis cache для быстрого доступа
            self.holidays_cache = payroll_cache.get_holidays_for_date_range(
                start_date, end_date
            )

            if self.holidays_cache:
                self.api_usage["redis_cache_hits"] += 1
                logger.info(
                    f"📋 Loaded {len(self.holidays_cache)} holidays from cache for {self.year}-{self.month:02d}"
                )
            else:
                self.api_usage["redis_cache_misses"] += 1
                logger.info(
                    f"📋 No holidays found in cache for {self.year}-{self.month:02d}"
                )

        except Exception as e:
            logger.warning(f"Error loading holidays cache: {e}")
            self.holidays_cache = {}

    def get_holiday_from_cache(self, work_date: date):
        """
        ✅ НОВОЕ: Получаем праздник из кэша вместо отдельного запроса к БД
        """
        date_str = work_date.isoformat()
        holiday_data = self.holidays_cache.get(date_str)

        if (
            holiday_data
            and holiday_data.get("is_holiday")
            and not holiday_data.get("is_shabbat")
        ):
            # Create temporary Holiday object for compatibility
            temp_holiday = type(
                "Holiday",
                (),
                {
                    "name": holiday_data["name"],
                    "date": work_date,
                    "is_holiday": holiday_data["is_holiday"],
                    "is_shabbat": holiday_data["is_shabbat"],
                    "is_special_shabbat": holiday_data.get("is_special_shabbat", False),
                },
            )()
            return temp_holiday

        return None

    def get_shabbat_from_cache(self, work_date: date):
        """
        ✅ НОВОЕ: Получаем шабат из кэша
        """
        date_str = work_date.isoformat()
        holiday_data = self.holidays_cache.get(date_str)

        if holiday_data and holiday_data.get("is_shabbat"):
            # Create temporary Holiday object for compatibility
            temp_holiday = type(
                "Holiday",
                (),
                {
                    "name": holiday_data["name"],
                    "date": work_date,
                    "is_holiday": holiday_data.get("is_holiday", False),
                    "is_shabbat": holiday_data["is_shabbat"],
                    "is_special_shabbat": holiday_data.get("is_special_shabbat", False),
                    "start_time": holiday_data.get("start_time"),
                    "end_time": holiday_data.get("end_time"),
                },
            )()
            return temp_holiday

        return None

    def get_work_logs_for_month(self):
        """
        Get work logs for the specified month with correct filtering

        Returns:
            QuerySet: Work logs for the specified month
        """
        start_date = date(self.year, self.month, 1)
        _, last_day = calendar.monthrange(self.year, self.month)
        end_date = date(self.year, self.month, last_day)

        work_logs = (
            WorkLog.objects.filter(
                employee=self.employee,
                check_out__isnull=False,  # Only completed sessions
            )
            .filter(
                # Session intersects with the month
                models.Q(check_in__date__lte=end_date)
                & models.Q(check_out__date__gte=start_date)
            )
            .order_by("check_in")
        )

        logger.info(
            "📊 Found work sessions for employee",
            extra={
                **safe_log_employee(self.employee, "payroll_sessions"),
                "session_count": work_logs.count(),
                "period": f"{self.year}-{self.month:02d}",
            },
        )

        return work_logs

    def is_night_shift(self, work_log):
        """
        Determine if work session is night shift according to Israeli law
        Night shift: >= 2 hours between 22:00-06:00
        """
        check_in = work_log.check_in
        check_out = work_log.check_out

        # Use the standardized night hours calculation from WorkLog model
        night_hours_float = work_log.get_night_hours()
        night_hours = Decimal(str(night_hours_float))

        is_night = night_hours >= Decimal("2")
        return is_night, night_hours

    def is_sabbath_work_precise(self, work_datetime, work_end_datetime=None):
        """
        Precise determination of Sabbath work using SunriseSunsetService

        Priority: Database with precise times > API > Simple check

        Args:
            work_datetime (datetime): Work start time
            work_end_datetime (datetime, optional): Work end time - if provided, checks if shift overlaps with Sabbath

        Returns:
            tuple: (is_sabbath, sabbath_type, sabbath_info)
        """
        work_date = work_datetime.date()
        shabbat_times = None

        # 1. Check registered sabbath in database first
        sabbath_holiday = Holiday.objects.filter(
            date=work_date, is_shabbat=True
        ).first()

        if sabbath_holiday:
            if sabbath_holiday.start_time and sabbath_holiday.end_time:
                # Use precise times from database
                start_time_israel = sabbath_holiday.start_time.astimezone(
                    self.israel_tz
                )
                end_time_israel = sabbath_holiday.end_time.astimezone(self.israel_tz)

                if work_datetime.tzinfo is None:
                    work_datetime = timezone.make_aware(work_datetime)
                work_datetime_israel = work_datetime.astimezone(self.israel_tz)

                if start_time_israel <= work_datetime_israel <= end_time_israel:
                    return True, "registered_sabbath_precise", sabbath_holiday
            else:
                return True, "registered_sabbath", sabbath_holiday

        # 2. Use SunriseSunsetService for precise calculation (not in fast mode)
        if not self.fast_mode:
            logger.info(
                f"🚀 Using SunriseSunsetService for precise sabbath calculation (fast_mode={self.fast_mode})"
            )
            try:
                self.api_usage["sunrise_sunset_calls"] += 1

                if work_date.weekday() == 4:  # Friday
                    shabbat_times = SunriseSunsetService.get_shabbat_times(work_date)

                if shabbat_times and not shabbat_times.get("is_estimated", True):
                    # We have precise times from API
                    self.api_usage["precise_sabbath_times"] += 1

                    shabbat_start_str = shabbat_times["start"]

                    try:
                        if shabbat_start_str.endswith("Z"):
                            shabbat_start_str = shabbat_start_str.replace("Z", "+00:00")
                        shabbat_start_utc = datetime.fromisoformat(shabbat_start_str)

                        if shabbat_start_utc.tzinfo is None:
                            shabbat_start_utc = pytz.UTC.localize(shabbat_start_utc)

                        shabbat_start_local = shabbat_start_utc.astimezone(
                            self.israel_tz
                        )

                        if work_datetime.tzinfo is None:
                            work_datetime = timezone.make_aware(work_datetime)
                        work_local = work_datetime.astimezone(self.israel_tz)

                        if work_local >= shabbat_start_local:
                            logger.info(
                                f"✅ Precise Sabbath work detected on {work_date}: "
                                f"work at {work_local.strftime('%H:%M')}, "
                                f"Sabbath starts at {shabbat_start_local.strftime('%H:%M')}"
                            )
                            return True, "friday_evening_precise", shabbat_times

                    except Exception as parse_error:
                        logger.warning(
                            f"Error parsing precise Sabbath time for {work_date}: {parse_error}"
                        )
                        self.api_usage["fallback_calculations"] += 1
                        if work_date.weekday() == 4 and work_datetime.time().hour >= 18:
                            return True, "friday_evening_fallback", None
                else:
                    # Use estimated time (18:00) - but only for Friday!
                    if work_date.weekday() == 4:  # Only for Friday
                        self.api_usage["fallback_calculations"] += 1
                        if work_datetime.time().hour >= 18:
                            return True, "friday_evening_estimated", shabbat_times

                if work_date.weekday() == 5:  # Saturday
                    try:
                        # Get Sabbath times for Friday (which started this Sabbath)
                        friday_date = work_date - timedelta(days=1)
                        shabbat_times = SunriseSunsetService.get_shabbat_times(
                            friday_date
                        )

                        if shabbat_times and not shabbat_times.get(
                            "is_estimated", True
                        ):
                            self.api_usage["precise_sabbath_times"] += 1
                            shabbat_end_str = shabbat_times["end"]

                            try:
                                if shabbat_end_str.endswith("Z"):
                                    shabbat_end_str = shabbat_end_str.replace(
                                        "Z", "+00:00"
                                    )
                                shabbat_end_utc = datetime.fromisoformat(
                                    shabbat_end_str
                                )

                                if shabbat_end_utc.tzinfo is None:
                                    shabbat_end_utc = pytz.UTC.localize(shabbat_end_utc)

                                shabbat_end_local = shabbat_end_utc.astimezone(
                                    self.israel_tz
                                )

                                if work_datetime.tzinfo is None:
                                    work_datetime = timezone.make_aware(work_datetime)
                                work_local = work_datetime.astimezone(self.israel_tz)

                                if work_local <= shabbat_end_local:
                                    logger.info(
                                        f"✅ Precise Sabbath work detected on {work_date}: "
                                        f"work at {work_local.strftime('%H:%M')}, "
                                        f"Sabbath ends at {shabbat_end_local.strftime('%H:%M')}"
                                    )
                                    return True, "saturday_precise", shabbat_times
                                else:
                                    # Work starts AFTER Sabbath ends (Motzei Shabbat)
                                    logger.info(
                                        f"✅ Motzei Shabbat work detected on {work_date}: "
                                        f"work at {work_local.strftime('%H:%M')}, "
                                        f"Sabbath ended at {shabbat_end_local.strftime('%H:%M')}"
                                    )
                                    return False, "motzei_shabbat", shabbat_times
                            except Exception as parse_error:
                                logger.warning(
                                    f"Error parsing Sabbath end time for {work_date}: {parse_error}"
                                )

                        # Fallback: entire Saturday is considered Sabbath
                        self.api_usage["fallback_calculations"] += 1
                        return True, "saturday_all_day", shabbat_times

                    except Exception as api_error:
                        logger.warning(
                            f"SunriseSunsetService error for Saturday {work_date}: {api_error}"
                        )
                        self.api_usage["fallback_calculations"] += 1
                        return True, "saturday_fallback", None

            except Exception as e:
                logger.warning(f"Error using SunriseSunsetService for {work_date}: {e}")
                self.api_usage["fallback_calculations"] += 1

        # Check if shift spans into Sabbath (for Friday shifts that end after Sabbath starts)
        if work_end_datetime and work_date.weekday() == 4:  # Friday shift
            # Use ShiftSplitter with sunrise_sunset_service for precise Sabbath detection
            try:
                split_result = ShiftSplitter.split_shift_for_sabbath(
                    work_datetime,
                    work_end_datetime,
                    use_api=(not self.fast_mode),  # Use API unless in fast mode
                )

                # If any hours are during Sabbath, this is Sabbath work
                if split_result["during_sabbath"] > 0:
                    api_source = (
                        "API" if split_result.get("api_used", False) else "fallback"
                    )
                    sabbath_start_time = split_result["sabbath_start_used"]

                    # Convert to Israel time for logging
                    if work_end_datetime.tzinfo is None:
                        work_end_datetime = timezone.make_aware(work_end_datetime)
                    work_end_israel = work_end_datetime.astimezone(self.israel_tz)

                    logger.info(
                        f"✅ Sabbath work detected: Friday shift ending at {work_end_israel.time().strftime('%H:%M')} "
                        f"Israel time, Sabbath starts at {sabbath_start_time.astimezone(self.israel_tz).time().strftime('%H:%M')} "
                        f"(source: {api_source})"
                    )

                    # Track API usage
                    if split_result.get("api_used", False):
                        self.api_usage["sunrise_sunset_calls"] += 1
                        self.api_usage["precise_sabbath_times"] += 1
                    else:
                        self.api_usage["fallback_calculations"] += 1

                    return True, "friday_shift_spanning_sabbath", split_result

            except Exception as e:
                logger.warning(
                    f"⚠️ Error using ShiftSplitter for Friday shift spanning detection: {e}, using fallback"
                )
                # Fallback to old seasonal logic
                if work_end_datetime.tzinfo is None:
                    work_end_datetime = timezone.make_aware(work_end_datetime)
                work_end_israel = work_end_datetime.astimezone(self.israel_tz)

                # Check based on season
                month = work_date.month
                if 5 <= month <= 9:  # Summer months
                    sabbath_hour = 19  # 19:00 or later in summer
                else:
                    sabbath_hour = 18  # 18:00 or later in winter

                if work_end_israel.time().hour >= sabbath_hour:
                    logger.info(
                        f"✅ Sabbath work detected (fallback): Friday shift ending at {work_end_israel.time().strftime('%H:%M')} Israel time"
                    )
                    self.api_usage["fallback_calculations"] += 1
                    return True, "friday_shift_spanning_sabbath_fallback", None

        # Fallback to simple check (or fast mode)
        if work_date.weekday() == 4 and work_datetime.time().hour >= 18:
            return True, "friday_evening_simple", None
        elif work_date.weekday() == 5:
            return True, "saturday_simple", None

        return False, None, None

    def is_holiday_work_enhanced(self, work_date):
        """
        ✅ ИСПРАВЛЕНО: Holiday work check using Redis cache first, then fallback

        Priority: Redis Cache > Database > API

        Args:
            work_date (date): Work date

        Returns:
            Holiday object or None
        """
        # ✅ 1. Check Redis cache first (eliminates N+1 queries)
        cached_holiday = self.get_holiday_from_cache(work_date)
        if cached_holiday:
            logger.debug(
                f"📅 Found cached holiday: {cached_holiday.name} on {work_date}"
            )
            return cached_holiday

        # 2. Fallback: Check database (only if not in cache)
        holiday = Holiday.objects.filter(
            date=work_date,
            is_holiday=True,
            is_shabbat=False,  # Exclude Sabbaths (handled separately)
        ).first()

        if holiday:
            logger.info(f"📅 Found registered holiday: {holiday.name} on {work_date}")
            return holiday

        # 2. Check via HebcalService (not in fast mode)
        if not self.fast_mode:
            logger.info(
                f"🚀 Using HebcalService for holiday lookup (fast_mode={self.fast_mode})"
            )
            try:
                self.api_usage["hebcal_calls"] += 1

                holidays_data = HebcalService.fetch_holidays(
                    year=work_date.year, month=work_date.month, use_cache=True
                )

                for holiday_data in holidays_data:
                    holiday_date_str = holiday_data.get("date")
                    if holiday_date_str:
                        try:
                            holiday_date = datetime.strptime(
                                holiday_date_str, "%Y-%m-%d"
                            ).date()
                            if holiday_date == work_date:
                                title = holiday_data.get("title", "Unknown Holiday")
                                self.api_usage["api_holidays_found"] += 1
                                logger.info(
                                    f"📅 Found holiday via HebcalService: {title} on {work_date}"
                                )

                                # Create temporary Holiday object
                                temp_holiday = type(
                                    "Holiday",
                                    (),
                                    {
                                        "name": title,
                                        "date": work_date,
                                        "is_holiday": True,
                                        "is_shabbat": holiday_data.get("subcat")
                                        == "shabbat",
                                    },
                                )()

                                return temp_holiday
                        except ValueError:
                            continue

            except Exception as api_error:
                logger.warning(f"HebcalService error for {work_date}: {api_error}")

        return None

    def sync_missing_holidays_for_month(self):
        """
        Synchronize missing holidays for the calculation month
        """
        if self.fast_mode:
            logger.info(
                f"⚡ Fast mode: skipping holiday synchronization for {self.year}-{self.month:02d}"
            )
            return

        try:
            logger.info(f"🔄 Synchronizing holidays for {self.year}-{self.month:02d}")

            existing_holidays = Holiday.objects.filter(
                date__year=self.year, date__month=self.month
            ).count()

            if existing_holidays == 0:
                logger.info(
                    "Holidays not found in database, synchronizing from HebcalService..."
                )
                created_count, updated_count = HebcalService.sync_holidays_to_db(
                    self.year
                )

                if created_count > 0 or updated_count > 0:
                    logger.info(
                        f"✅ Synchronized holidays: {created_count} created, {updated_count} updated"
                    )
                else:
                    logger.warning("Holidays were not synchronized")
            else:
                logger.debug(
                    f"Found {existing_holidays} existing holidays for {self.year}-{self.month:02d}"
                )

        except Exception as sync_error:
            logger.error(f"Holiday synchronization error: {sync_error}")

    def create_compensatory_day(self, work_date, reason, work_hours=None):
        """
        Create compensatory day for holiday or Sabbath work
        """
        try:
            existing = CompensatoryDay.objects.filter(
                employee=self.employee, date_earned=work_date, reason=reason
            ).first()

            if existing:
                logger.debug(
                    "Compensatory day already exists",
                    extra={
                        **safe_log_employee(self.employee, "compensatory_exists"),
                        "date": work_date.isoformat(),
                        "reason": reason,
                    },
                )
                return (
                    True,
                    existing,
                )  # Return True because compensatory day exists for this work

            comp_day = CompensatoryDay.objects.create(
                employee=self.employee, date_earned=work_date, reason=reason
            )

            logger.info(
                "Created compensatory day",
                extra={
                    **safe_log_employee(self.employee, "compensatory_created"),
                    "date": work_date.isoformat(),
                    "reason": reason,
                    "work_hours": work_hours,
                },
            )

            return True, comp_day

        except Exception as e:
            error_msg = f"Error creating compensatory day for {self.employee.get_full_name()}: {e}"
            self.calculation_errors.append(error_msg)
            logger.error(error_msg)
            return False, None

    def calculate_overtime_pay_hourly(
        self, hours_worked, base_rate, is_special_day=False, is_night_shift=False
    ):
        """
        Calculate overtime pay for HOURLY employees (full daily pay)

        Args:
            hours_worked (Decimal): Total hours worked
            base_rate (Decimal): Base hourly rate
            is_special_day (bool): Holiday or Sabbath work
            is_night_shift (bool): Night shift work

        Returns:
            dict: Complete breakdown with full pay amounts
        """
        if base_rate is None:
            base_rate = Decimal("0")

        result = {
            "regular_hours": Decimal("0"),
            "regular_pay": Decimal("0"),
            "overtime_hours_1": Decimal("0"),  # First 2 overtime hours (regular)
            "overtime_pay_1": Decimal("0"),
            "overtime_hours_2": Decimal("0"),  # Additional overtime hours (regular)
            "overtime_pay_2": Decimal("0"),
            # NEW: Sabbath-specific overtime tracking
            "sabbath_overtime_hours_1": Decimal("0"),  # First 2 sabbath overtime hours
            "sabbath_overtime_pay_1": Decimal("0"),
            "sabbath_overtime_hours_2": Decimal(
                "0"
            ),  # Additional sabbath overtime hours
            "sabbath_overtime_pay_2": Decimal("0"),
            "total_pay": Decimal("0"),
            "rate_used": base_rate,
        }

        if hours_worked <= 0:
            return result

        # Check for exceeding maximum work day
        if hours_worked > self.MAX_DAILY_HOURS:
            warning = (
                f"Employee {self.employee.get_full_name()} exceeded maximum "
                f"work day: {hours_worked}h > {self.MAX_DAILY_HOURS}h"
            )
            self.warnings.append(warning)
            logger.warning(warning)

        # Determine regular hours based on shift type
        if is_night_shift:
            max_regular_hours = self.NIGHT_SHIFT_MAX_REGULAR_HOURS
        else:
            max_regular_hours = self.REGULAR_DAILY_HOURS

        regular_hours = min(hours_worked, max_regular_hours)
        result["regular_hours"] = regular_hours

        # Calculate regular pay
        if is_special_day:
            # Holiday/Sabbath work gets 150% for all hours
            result["regular_pay"] = regular_hours * base_rate * self.HOLIDAY_RATE
        else:
            result["regular_pay"] = regular_hours * base_rate

        # Calculate overtime
        if hours_worked > max_regular_hours:
            overtime_total = hours_worked - max_regular_hours

            if is_special_day:
                # Overtime rates for holiday/Sabbath work
                # First 2 overtime hours: 175% (150% base + 25% overtime)
                overtime_rate_1 = base_rate * Decimal("1.75")
                overtime_hours_1 = min(overtime_total, Decimal("2"))

                # Store in sabbath-specific fields for better tracking
                result["sabbath_overtime_hours_1"] = overtime_hours_1
                result["sabbath_overtime_pay_1"] = overtime_hours_1 * overtime_rate_1

                # Additional overtime: 200% (150% base + 50% overtime)
                if overtime_total > 2:
                    overtime_rate_2 = base_rate * Decimal("2.0")
                    overtime_hours_2 = overtime_total - Decimal("2")
                    result["sabbath_overtime_hours_2"] = overtime_hours_2
                    result["sabbath_overtime_pay_2"] = (
                        overtime_hours_2 * overtime_rate_2
                    )

                # Keep legacy fields for backward compatibility
                result["overtime_hours_1"] = overtime_hours_1
                result["overtime_pay_1"] = overtime_hours_1 * overtime_rate_1
                if overtime_total > 2:
                    result["overtime_hours_2"] = overtime_hours_2
                    result["overtime_pay_2"] = overtime_hours_2 * overtime_rate_2
            else:
                # Regular daily overtime rates
                # First 2 overtime hours: 125%
                overtime_rate_1 = base_rate * self.OVERTIME_RATE_125
                overtime_hours_1 = min(overtime_total, Decimal("2"))
                result["overtime_hours_1"] = overtime_hours_1
                result["overtime_pay_1"] = overtime_hours_1 * overtime_rate_1

                # Additional overtime: 150%
                if overtime_total > 2:
                    overtime_rate_2 = base_rate * self.OVERTIME_RATE_150
                    overtime_hours_2 = overtime_total - Decimal("2")
                    result["overtime_hours_2"] = overtime_hours_2
                    result["overtime_pay_2"] = overtime_hours_2 * overtime_rate_2

        # Calculate total pay including sabbath overtime
        result["total_pay"] = (
            result["regular_pay"]
            + result["overtime_pay_1"]
            + result["overtime_pay_2"]
            + result["sabbath_overtime_pay_1"]
            + result["sabbath_overtime_pay_2"]
        )
        return result

    def calculate_daily_bonuses_monthly(self, work_log, save_to_db=True):
        """
        Calculate daily pay for MONTHLY employees using unified base_pay + bonus_pay logic

        NEW UNIFIED LOGIC:
        - base_pay = hours × monthly_hourly_rate (where monthly_hourly_rate = salary / 182)
        - bonus_pay = overtime premiums + sabbath/holiday bonuses
        - total_pay = base_pay + bonus_pay

        Args:
            work_log: WorkLog object
            save_to_db: Whether to save calculation to database

        Returns:
            dict: Daily calculation with unified payment structure
        """
        work_date = work_log.check_in.date()
        hours_worked = work_log.get_total_hours()

        # Monthly hourly rate using official 182 hours standard
        monthly_hourly_rate = (
            self.salary.base_salary / self.MONTHLY_WORK_HOURS
        )  # 182 hours

        # NEW UNIFIED LOGIC: base_pay = hours × monthly_hourly_rate
        base_pay = hours_worked * monthly_hourly_rate

        result = {
            "date": work_date,
            "hours_worked": hours_worked,
            "is_holiday": False,
            "is_sabbath": False,
            "is_night_shift": False,
            "night_hours": Decimal("0"),
            "holiday_name": None,
            "sabbath_type": None,
            "sabbath_info": None,
            "compensatory_day_created": False,
            # NEW UNIFIED PAYMENT STRUCTURE
            "base_pay": base_pay,  # hours × monthly_hourly_rate
            "bonus_pay": Decimal("0"),  # will be calculated below
            "total_pay": base_pay,  # will be updated with bonuses
            # Legacy fields for backward compatibility
            "regular_pay": Decimal("0"),
            "overtime_pay": Decimal("0"),
            "special_day_bonus": Decimal("0"),
            "total_gross_pay": base_pay,  # will be updated with bonuses
            "breakdown": {},
            "api_sources": [],
        }

        # Determine if this is a night shift (>= 2 hours rule)
        is_night_shift, night_hours = self.is_night_shift(work_log)
        result["is_night_shift"] = is_night_shift
        result["night_hours"] = night_hours

        # Check for holiday work
        holiday = self.is_holiday_work_enhanced(work_date)
        if holiday:
            result["is_holiday"] = True
            result["holiday_name"] = holiday.name
            result["api_sources"].append(
                "hebcal_api" if not hasattr(holiday, "id") else "database"
            )

            # Create compensatory day
            created, _ = self.create_compensatory_day(
                work_date, "holiday", hours_worked
            )
            result["compensatory_day_created"] = created

            # NEW UNIFIED LOGIC: Holiday work gets +50% bonus on top of base pay
            # base_pay = hours × monthly_hourly_rate (already calculated above)
            # bonus_pay = hours × monthly_hourly_rate × 50%
            holiday_bonus = (
                hours_worked * monthly_hourly_rate * self.SPECIAL_DAY_BONUS
            )  # 50% bonus

            result["bonus_pay"] = holiday_bonus
            result["total_pay"] = result["base_pay"] + holiday_bonus  # base + bonus
            result["total_gross_pay"] = result["total_pay"]  # same as total_pay
            result["special_day_bonus"] = holiday_bonus

            result["breakdown"] = {
                "regular_hours": hours_worked,
                "base_pay": result["base_pay"],  # hours × monthly_hourly_rate
                "holiday_bonus_hours": hours_worked,
                "holiday_bonus_pay": holiday_bonus,  # 50% bonus
                "total_pay": result["total_pay"],  # base + bonus = 150%
                "rate_used": monthly_hourly_rate,
            }

            logger.info(
                f"💰 Holiday work (monthly): {work_date} - {hours_worked}h: base ₪{result['base_pay']:.2f} + bonus ₪{holiday_bonus:.2f} = ₪{result['total_pay']:.2f} (150%)"
            )

            if save_to_db:
                self._save_daily_calculation(work_log, result)

            return result

        # Check for Sabbath work
        is_sabbath, sabbath_type, sabbath_info = self.is_sabbath_work_precise(
            work_log.check_in, work_log.check_out
        )
        if is_sabbath:
            result["is_sabbath"] = True
            result["sabbath_type"] = sabbath_type
            result["sabbath_info"] = sabbath_info

            # Track Sabbath data source
            if "precise" in sabbath_type:
                result["api_sources"].append("sunrise_sunset_api")
            elif "registered" in sabbath_type:
                result["api_sources"].append("database")
            else:
                result["api_sources"].append("fallback_calculation")

            # Create compensatory day
            created, _ = self.create_compensatory_day(
                work_date, "shabbat", hours_worked
            )
            result["compensatory_day_created"] = created

            # Check if shift spans into Sabbath and needs splitting
            if sabbath_type == "friday_shift_spanning_sabbath":
                # Use ShiftSplitter for precise calculation with sunrise_sunset_service
                split_result = ShiftSplitter.split_shift_for_sabbath(
                    work_log.check_in,
                    work_log.check_out,
                    use_api=(not self.fast_mode),  # Use API unless in fast mode
                )

                # Track API usage if split_result contains API info
                if split_result.get("api_used", False):
                    result["api_sources"].append("sunrise_sunset_api_split")
                else:
                    result["api_sources"].append("fallback_calculation_split")

                overtime_breakdown = ShiftSplitter.calculate_split_overtime(
                    split_result["total_hours"], split_result["during_sabbath"]
                )
                payment = ShiftSplitter.calculate_payment_for_split_shift(
                    overtime_breakdown, monthly_hourly_rate
                )

                # Convert to monthly employee format
                # Base pay is already calculated above
                result["bonus_pay"] = payment["total_pay"] - result["base_pay"]
                result["total_pay"] = payment["total_pay"]
                result["total_gross_pay"] = payment["total_pay"]
                result["special_day_bonus"] = (
                    payment["sabbath_pay"] + payment["sabbath_overtime_pay"]
                )

                result["split_shift"] = True
                result["before_sabbath_hours"] = split_result["before_sabbath"]
                result["during_sabbath_hours"] = split_result["during_sabbath"]

                logger.info(
                    f"💰 Split Sabbath shift (monthly): {work_date} - "
                    f"Before: {split_result['before_sabbath']}h, "
                    f"During: {split_result['during_sabbath']}h = ₪{result['total_pay']:.2f}"
                )
            else:
                # Regular Sabbath day (Saturday) or shift starting after Sabbath
                # NEW UNIFIED LOGIC: Sabbath work gets +50% bonus on top of base pay
                # base_pay = hours × monthly_hourly_rate (already calculated above)
                # bonus_pay = hours × monthly_hourly_rate × 50%
                sabbath_bonus = (
                    hours_worked * monthly_hourly_rate * self.SPECIAL_DAY_BONUS
                )  # 50% bonus

                result["bonus_pay"] = sabbath_bonus
                result["total_pay"] = result["base_pay"] + sabbath_bonus  # base + bonus
                result["total_gross_pay"] = result["total_pay"]  # same as total_pay
                result["special_day_bonus"] = sabbath_bonus

            result["breakdown"] = {
                "regular_hours": hours_worked,
                "base_pay": result["base_pay"],  # hours × monthly_hourly_rate
                "sabbath_bonus_hours": result.get("during_sabbath_hours", hours_worked),
                "sabbath_bonus_pay": result.get(
                    "special_day_bonus", result["bonus_pay"]
                ),  # Use special_day_bonus if available
                "total_pay": result["total_pay"],  # base + bonus
                "rate_used": monthly_hourly_rate,
            }

            if "split_shift" in result:
                logger.info(
                    f"🕯️ Sabbath work (monthly): {work_date} ({sabbath_type}) - split shift calculated"
                )
            else:
                logger.info(
                    f"🕯️ Sabbath work (monthly): {work_date} ({sabbath_type}) - {hours_worked}h: base ₪{result['base_pay']:.2f} + bonus ₪{result['bonus_pay']:.2f} = ₪{result['total_pay']:.2f} (150%)"
                )

            if save_to_db:
                self._save_daily_calculation(work_log, result)

            return result

        # Regular work day - calculate overtime bonuses only
        # Check if this is a night shift
        is_night_shift = result["is_night_shift"]  # Already calculated above
        max_regular_hours = (
            self.NIGHT_SHIFT_MAX_REGULAR_HOURS
            if is_night_shift
            else self.REGULAR_DAILY_HOURS
        )

        if hours_worked <= max_regular_hours:
            # No overtime - only base pay (already calculated above)
            # bonus_pay remains 0, total_pay = base_pay
            result["breakdown"] = {
                "regular_hours": hours_worked,
                "base_pay": result["base_pay"],  # hours × monthly_hourly_rate
                "bonus_pay": Decimal("0"),  # no bonuses
                "total_pay": result["total_pay"],  # = base_pay
                "rate_used": monthly_hourly_rate,
            }

            logger.debug(
                f"💼 Regular day (monthly): {work_date} - {hours_worked}h: base ₪{result['base_pay']:.2f}, no overtime"
            )
        else:
            # Calculate overtime bonuses
            regular_hours = max_regular_hours
            overtime_hours = hours_worked - max_regular_hours

            overtime_bonus = Decimal("0")
            overtime_breakdown = {}

            # NEW UNIFIED LOGIC: overtime bonuses are ONLY the additional percentages (25%/50%)
            # base_pay already covers 100% for ALL hours worked

            # First 2 overtime hours: +25% bonus
            overtime_1 = min(overtime_hours, Decimal("2"))
            if overtime_1 > 0:
                bonus_1 = (
                    overtime_1 * monthly_hourly_rate * self.OVERTIME_BONUS_125
                )  # 25% bonus
                overtime_bonus += bonus_1
                overtime_breakdown["overtime_125_hours"] = overtime_1
                overtime_breakdown["overtime_125_bonus"] = bonus_1

            # Additional overtime hours: +50% bonus
            if overtime_hours > Decimal("2"):
                overtime_2 = overtime_hours - Decimal("2")
                bonus_2 = (
                    overtime_2 * monthly_hourly_rate * self.OVERTIME_BONUS_150
                )  # 50% bonus
                overtime_bonus += bonus_2
                overtime_breakdown["overtime_150_hours"] = overtime_2
                overtime_breakdown["overtime_150_bonus"] = bonus_2

            # Update NEW UNIFIED PAYMENT STRUCTURE
            result["bonus_pay"] = overtime_bonus
            result["total_pay"] = result["base_pay"] + overtime_bonus
            result["total_gross_pay"] = result["total_pay"]  # same as total_pay

            # Legacy fields for backward compatibility
            result["overtime_pay"] = overtime_bonus

            result["breakdown"] = {
                "regular_hours": regular_hours,
                "base_pay": result["base_pay"],  # hours × monthly_hourly_rate
                "bonus_pay": overtime_bonus,  # only overtime bonuses
                "overtime_hours_1": overtime_breakdown.get(
                    "overtime_125_hours", Decimal("0")
                ),
                "overtime_pay_1": overtime_breakdown.get(
                    "overtime_125_bonus", Decimal("0")
                ),
                "overtime_hours_2": overtime_breakdown.get(
                    "overtime_150_hours", Decimal("0")
                ),
                "overtime_pay_2": overtime_breakdown.get(
                    "overtime_150_bonus", Decimal("0")
                ),
                "total_pay": result["total_pay"],  # base + bonus
                "rate_used": monthly_hourly_rate,
            }

            logger.debug(
                f"💼 Regular day with overtime (monthly): {work_date} - "
                f"{hours_worked}h: base ₪{result['base_pay']:.2f} + overtime bonus ₪{overtime_bonus:.2f} = ₪{result['total_pay']:.2f}"
            )

        if save_to_db:
            self._save_daily_calculation(work_log, result)

        return result

    def calculate_daily_pay_hourly(self, work_log, save_to_db=True):
        """
        Calculate full daily pay for HOURLY employees
        FIXED: Collect all shift attributes first, then calculate

        Args:
            work_log: WorkLog object
            save_to_db: Whether to save calculation to database

        Returns:
            dict: Daily calculation with full pay
        """
        work_date = work_log.check_in.date()
        hours_worked = work_log.get_total_hours()
        base_rate = self.salary.hourly_rate or Decimal("0")

        # STEP 1: Collect ALL shift attributes first
        is_night_shift, night_hours = self.is_night_shift(work_log)
        holiday = self.is_holiday_work_enhanced(work_date)
        is_sabbath, sabbath_type, sabbath_info = self.is_sabbath_work_precise(
            work_log.check_in, work_log.check_out
        )

        # Initialize is_special_day to avoid UnboundLocalError
        is_special_day = bool(holiday or is_sabbath)

        result = {
            "date": work_date,
            "hours_worked": hours_worked,
            "is_holiday": bool(holiday),
            "is_sabbath": is_sabbath,
            "is_night_shift": is_night_shift,
            "night_hours": night_hours,
            "night_pay": Decimal("0"),  # ADDED: separate night overtime pay
            "sabbath_night_hours": Decimal("0"),  # ADDED: combined sabbath+night hours
            "sabbath_night_pay": Decimal(
                "0"
            ),  # ADDED: pay for sabbath+night combination
            "holiday_name": holiday.name if holiday else None,
            "sabbath_type": sabbath_type if is_sabbath else None,
            "sabbath_info": sabbath_info if is_sabbath else None,
            "compensatory_day_created": False,
            "regular_pay": Decimal("0"),
            "overtime_pay": Decimal("0"),
            "special_day_bonus": Decimal("0"),
            "total_pay": Decimal("0"),
            "breakdown": {},
            "api_sources": [],
        }

        # STEP 2: Track API sources
        if holiday:
            result["api_sources"].append(
                "hebcal_api" if not hasattr(holiday, "id") else "database"
            )

        if is_sabbath:
            if "precise" in sabbath_type:
                result["api_sources"].append("sunrise_sunset_api")
            elif "registered" in sabbath_type:
                result["api_sources"].append("database")
            else:
                result["api_sources"].append("fallback_calculation")

        # STEP 3: Handle combined scenarios
        if is_sabbath and is_night_shift:
            result["sabbath_night_hours"] = night_hours

        # STEP 4: Create compensatory days
        if holiday:
            created, _ = self.create_compensatory_day(
                work_date, "holiday", hours_worked
            )
            result["compensatory_day_created"] = created
        elif is_sabbath:
            created, _ = self.create_compensatory_day(
                work_date, "shabbat", hours_worked
            )
            result["compensatory_day_created"] = created

        # STEP 5: Calculate pay based on shift type
        # Check if shift spans into Sabbath and needs splitting
        if is_sabbath and sabbath_type == "friday_shift_spanning_sabbath":
            # Use ShiftSplitter for precise calculation with sunrise_sunset_service
            split_result = ShiftSplitter.split_shift_for_sabbath(
                work_log.check_in,
                work_log.check_out,
                use_api=(not self.fast_mode),  # Use API unless in fast mode
            )

            # Track API usage if split_result contains API info
            if split_result.get("api_used", False):
                result["api_sources"].append("sunrise_sunset_api_split")
                self.api_usage["sunrise_sunset_calls"] += 1
                self.api_usage["precise_sabbath_times"] += 1
            else:
                result["api_sources"].append("fallback_calculation_split")
                self.api_usage["fallback_calculations"] += 1

            overtime_breakdown = ShiftSplitter.calculate_split_overtime(
                split_result["total_hours"], split_result["during_sabbath"]
            )
            payment = ShiftSplitter.calculate_payment_for_split_shift(
                overtime_breakdown, base_rate
            )

            # Convert to expected format
            result["total_pay"] = payment["total_pay"]
            result["total_gross_pay"] = payment["total_pay"]

            # Calculate base_pay and bonus_pay for unified structure
            # Base pay = regular hours × rate
            result["base_pay"] = hours_worked * base_rate
            # Bonus pay = total - base
            result["bonus_pay"] = payment["total_pay"] - result["base_pay"]

            # Extract sabbath overtime payments from details breakdown
            payment_details = payment.get("details", {})
            sabbath_ot_175_info = payment_details.get("sabbath_overtime_175", {})
            sabbath_ot_200_info = payment_details.get("sabbath_overtime_200", {})

            result["breakdown"] = {
                "split_shift": True,
                "before_sabbath_hours": split_result["before_sabbath"],
                "during_sabbath_hours": split_result["during_sabbath"],
                "payment_details": payment["details"],
                "regular_hours": overtime_breakdown.get("regular_hours", Decimal("0")),
                "regular_pay": payment["regular_pay"],
                "overtime_pay_1": payment.get(
                    "overtime_before_sabbath_pay_1", Decimal("0")
                ),
                "overtime_pay_2": payment.get(
                    "overtime_before_sabbath_pay_2", Decimal("0")
                ),
                "sabbath_pay": payment["sabbath_pay"],
                "sabbath_overtime_pay_1": sabbath_ot_175_info.get("pay", Decimal("0")),
                "sabbath_overtime_pay_2": sabbath_ot_200_info.get("pay", Decimal("0")),
            }

            # Update overtime hours for database - separate regular and sabbath overtime
            result["overtime_hours_1"] = overtime_breakdown.get(
                "overtime_before_sabbath_1", Decimal("0")
            )
            result["overtime_hours_2"] = overtime_breakdown.get(
                "overtime_before_sabbath_2", Decimal("0")
            )
            result["sabbath_regular_hours"] = overtime_breakdown.get(
                "sabbath_regular", Decimal("0")
            )
            result["sabbath_overtime_hours_1"] = overtime_breakdown.get(
                "sabbath_overtime_1", Decimal("0")
            )
            result["sabbath_overtime_hours_2"] = overtime_breakdown.get(
                "sabbath_overtime_2", Decimal("0")
            )

            # Also add to breakdown so they get saved to database
            result["breakdown"]["overtime_hours_1"] = result["overtime_hours_1"]
            result["breakdown"]["overtime_hours_2"] = result["overtime_hours_2"]
            result["breakdown"]["sabbath_regular_hours"] = result[
                "sabbath_regular_hours"
            ]
            result["breakdown"]["sabbath_overtime_hours_1"] = result[
                "sabbath_overtime_hours_1"
            ]
            result["breakdown"]["sabbath_overtime_hours_2"] = result[
                "sabbath_overtime_hours_2"
            ]

            logger.info(
                f"💰 Split Sabbath shift (hourly): {work_date} - "
                f"Before: {split_result['before_sabbath']}h, "
                f"During: {split_result['during_sabbath']}h = ₪{result['total_pay']}"
            )
        else:
            # Use existing logic for non-split shifts
            pay_breakdown = self.calculate_overtime_pay_hourly(
                hours_worked,
                base_rate,
                is_special_day=is_special_day,
                is_night_shift=is_night_shift,
            )
            result["breakdown"] = pay_breakdown
            result["total_pay"] = pay_breakdown["total_pay"]
            result["total_gross_pay"] = pay_breakdown[
                "total_pay"
            ]  # For hourly employees, total_gross_pay = total_pay

            # Calculate base_pay and bonus_pay for unified structure
            result["base_pay"] = hours_worked * base_rate
            result["bonus_pay"] = pay_breakdown["total_pay"] - result["base_pay"]

        # STEP 6: Calculate separate night_pay and sabbath_night_pay
        if is_night_shift:
            night_overtime_hours = max(
                Decimal("0"), hours_worked - self.NIGHT_SHIFT_MAX_REGULAR_HOURS
            )
            if night_overtime_hours > 0:
                # First 2 hours at 125%, rest at 150%
                overtime_1 = min(night_overtime_hours, Decimal("2"))
                overtime_2 = max(Decimal("0"), night_overtime_hours - Decimal("2"))

                if is_special_day:
                    # Sabbath night pay (higher rates: 175%/200%)
                    result["sabbath_night_pay"] = (
                        (overtime_1 * base_rate * Decimal("1.75"))
                        + (overtime_2 * base_rate * Decimal("2.00"))
                        - (night_overtime_hours * base_rate)
                    )  # Subtract base pay
                else:
                    # Regular night pay (125%/150%)
                    result["night_pay"] = (
                        (overtime_1 * base_rate * self.OVERTIME_RATE_125)
                        + (overtime_2 * base_rate * self.OVERTIME_RATE_150)
                        - (night_overtime_hours * base_rate)
                    )  # Subtract base pay

        logger.info(
            f"💰 {'Holiday' if holiday else 'Sabbath' if is_sabbath else 'Regular'} work (hourly): "
            f"{work_date} - {hours_worked}h = ₪{result['total_pay']}"
        )

        if save_to_db:
            self._save_daily_calculation(work_log, result)

        return result

    def _save_daily_calculation(self, work_log, calculation_result):
        """
        Save daily payroll calculation to database

        Args:
            work_log: WorkLog object
            calculation_result: Result dictionary from daily calculation
        """
        try:
            # Extract breakdown data
            breakdown = calculation_result.get("breakdown", {})

            # Create or update daily calculation record
            daily_calc, created = DailyPayrollCalculation.objects.update_or_create(
                employee=self.employee,
                work_date=calculation_result["date"],
                defaults={
                    "regular_hours": breakdown.get("regular_hours", Decimal("0")),
                    "overtime_hours_1": breakdown.get("overtime_hours_1", Decimal("0")),
                    "overtime_hours_2": breakdown.get("overtime_hours_2", Decimal("0")),
                    # Sabbath-specific hours
                    "sabbath_regular_hours": breakdown.get(
                        "sabbath_regular_hours", Decimal("0")
                    ),
                    "sabbath_overtime_hours_1": breakdown.get(
                        "sabbath_overtime_hours_1", Decimal("0")
                    ),
                    "sabbath_overtime_hours_2": breakdown.get(
                        "sabbath_overtime_hours_2", Decimal("0")
                    ),
                    "night_hours": calculation_result["night_hours"],
                    "regular_pay": breakdown.get("regular_pay", Decimal("0")),
                    "overtime_pay_1": breakdown.get("overtime_pay_1", Decimal("0")),
                    "overtime_pay_2": breakdown.get("overtime_pay_2", Decimal("0")),
                    # NEW: Sabbath-specific overtime payments
                    "sabbath_overtime_pay_1": breakdown.get(
                        "sabbath_overtime_pay_1", Decimal("0")
                    ),
                    "sabbath_overtime_pay_2": breakdown.get(
                        "sabbath_overtime_pay_2", Decimal("0")
                    ),
                    "total_pay": calculation_result["total_pay"],
                    "total_gross_pay": calculation_result.get(
                        "total_gross_pay", calculation_result["total_pay"]
                    ),
                    # NEW UNIFIED PAYMENT STRUCTURE
                    "base_pay": calculation_result.get("base_pay", Decimal("0")),
                    "bonus_pay": calculation_result.get("bonus_pay", Decimal("0")),
                    "is_holiday": calculation_result["is_holiday"],
                    "is_sabbath": calculation_result["is_sabbath"],
                    "is_night_shift": calculation_result["is_night_shift"],
                    "holiday_name": calculation_result.get("holiday_name", ""),
                    "calculated_by_service": "EnhancedPayrollCalculationService",
                    "calculation_details": {
                        "sabbath_info": str(calculation_result.get("sabbath_info", "")),
                        "sabbath_type": calculation_result.get("sabbath_type", ""),
                        "api_sources": calculation_result.get("api_sources", []),
                        "api_usage": self.api_usage.copy(),
                        "fast_mode": self.fast_mode,
                        "compensatory_day_created": calculation_result[
                            "compensatory_day_created"
                        ],
                        "calculation_type": self.salary.calculation_type,
                        "is_bonus_only": self.salary.calculation_type
                        == "monthly",  # Important flag
                    },
                },
            )

            action = "Updated" if not created else "Saved new"
            logger.debug(
                f"💾 {action} daily calculation for {self.employee.get_full_name()} on {calculation_result['date']}"
            )

        except Exception as e:
            error_msg = f"Error saving daily calculation: {e}"
            self.calculation_errors.append(error_msg)
            logger.error(error_msg)

    def _save_monthly_summary(self, monthly_result):
        """
        Save monthly payroll summary to database

        Args:
            monthly_result: Result dictionary from monthly calculation
        """
        try:
            # Create or update monthly summary record
            monthly_summary, created = MonthlyPayrollSummary.objects.update_or_create(
                employee=self.employee,
                year=self.year,
                month=self.month,
                defaults={
                    "total_hours": monthly_result["total_hours"],
                    "regular_hours": monthly_result["regular_hours"],
                    "overtime_hours": monthly_result["overtime_hours"],
                    "holiday_hours": monthly_result["holiday_hours"],
                    "sabbath_hours": monthly_result["sabbath_hours"],
                    "base_pay": (
                        monthly_result.get("base_salary", 0)
                        if self.salary.calculation_type == "monthly"
                        else 0
                    ),
                    "overtime_pay": 0,  # Will be calculated from daily records
                    "holiday_pay": 0,  # Will be calculated from daily records
                    "sabbath_pay": 0,  # Will be calculated from daily records
                    "total_gross_pay": monthly_result["total_gross_pay"],
                    "worked_days": monthly_result["worked_days"],
                    "compensatory_days_earned": monthly_result[
                        "compensatory_days_earned"
                    ],
                    "calculation_date": timezone.now(),
                    "last_updated": timezone.now(),
                    "calculation_details": {
                        "legal_violations": [
                            str(v) for v in monthly_result["legal_violations"]
                        ],
                        "warnings": [str(w) for w in monthly_result["warnings"]],
                        "errors": [str(e) for e in monthly_result["errors"]],
                        "api_integrations": monthly_result.get("api_integrations", {}),
                        "api_usage": self.api_usage.copy(),
                        "fast_mode": self.fast_mode,
                        "calculation_type": monthly_result["calculation_type"],
                        "currency": monthly_result["currency"],
                        "work_sessions_count": monthly_result["work_sessions_count"],
                        "base_hourly_rate": (
                            float(monthly_result.get("base_hourly_rate", 0))
                            if monthly_result.get("base_hourly_rate")
                            else None
                        ),
                    },
                },
            )

            action = "Updated" if not created else "Saved new"
            logger.info(
                f"💾 {action} monthly summary for {self.employee.get_full_name()} {self.year}-{self.month:02d}"
            )

        except Exception as e:
            error_msg = f"Error saving monthly summary: {e}"
            self.calculation_errors.append(error_msg)
            logger.error(error_msg)

    def calculate_monthly_salary_enhanced(self):
        """
        FIXED: Monthly salary calculation with proper logic separation

        - Hourly employees: sum of daily pay calculations
        - Monthly employees: base salary + bonuses only (NO double payment)
        """
        # Synchronize holidays before calculation
        self.sync_missing_holidays_for_month()

        # Get work logs
        work_logs = self.get_work_logs_for_month()

        result = {
            "employee": self.employee.get_full_name(),
            "period": f"{self.year}-{self.month:02d}",
            "calculation_type": self.salary.calculation_type,
            "currency": self.salary.currency,
            "base_hourly_rate": self.salary.hourly_rate,
            "daily_calculations": [],
            "total_hours": Decimal("0"),
            "regular_hours": Decimal("0"),
            "overtime_hours": Decimal("0"),
            "holiday_hours": Decimal("0"),
            "sabbath_hours": Decimal("0"),
            "night_hours": Decimal("0"),
            "night_pay": Decimal("0"),
            "sabbath_night_pay": Decimal("0"),
            "total_gross_pay": Decimal("0"),
            "compensatory_days_earned": 0,
            "legal_violations": [],
            "warnings": [],
            "errors": self.calculation_errors,
            "minimum_wage_applied": False,
            "work_sessions_count": work_logs.count(),
            "worked_days": 0,
            "api_integrations": {
                "sunrise_sunset_used": self.api_usage["sunrise_sunset_calls"] > 0,
                "hebcal_used": self.api_usage["hebcal_calls"] > 0,
                "precise_sabbath_times": self.api_usage["precise_sabbath_times"],
                "api_holidays_found": self.api_usage["api_holidays_found"],
                "fallback_calculations": self.api_usage["fallback_calculations"],
            },
        }

        if not work_logs.exists():
            result["note"] = "No work logs for this period"
            logger.info(
                f"No work logs for {self.employee.get_full_name()} in {self.year}-{self.month:02d}"
            )

            # Save empty summary
            self._save_monthly_summary(result)
            return result

        # FIXED: Use different calculation methods for different employee types
        if self.salary.calculation_type == "monthly":
            # Monthly employees: calculate bonuses only
            logger.info(
                f"Calculating bonuses for monthly employee {self.employee.get_full_name()}"
            )

            total_bonuses = Decimal("0")

            for log in work_logs:
                daily_calc = self.calculate_daily_bonuses_monthly(log, save_to_db=True)
                result["daily_calculations"].append(daily_calc)

                # Accumulate totals
                result["total_hours"] += daily_calc["hours_worked"]
                total_bonuses += daily_calc["bonus_pay"]  # Only bonuses, not base pay!

                # Accumulate night hours
                result["night_hours"] += daily_calc.get("night_hours", Decimal("0"))

                # Accumulate hours by type (ALWAYS accumulate breakdown data)
                if daily_calc["breakdown"]:
                    result["regular_hours"] += daily_calc["breakdown"].get(
                        "regular_hours", Decimal("0")
                    )
                    result["overtime_hours"] += daily_calc["breakdown"].get(
                        "overtime_hours_1", Decimal("0")
                    ) + daily_calc["breakdown"].get("overtime_hours_2", Decimal("0"))

                if daily_calc["is_holiday"]:
                    result["holiday_hours"] += daily_calc["hours_worked"]
                elif daily_calc["is_sabbath"]:
                    result["sabbath_hours"] += daily_calc["hours_worked"]

                if daily_calc["compensatory_day_created"]:
                    result["compensatory_days_earned"] += 1

            # Calculate proportional base salary BY HOURS (not days)
            # Monthly salary is based on 182 hours per month standard
            worked_days = len(set(log.check_in.date() for log in work_logs))
            result["worked_days"] = worked_days

            # NEW LOGIC: Proportional salary by hours worked
            total_hours_worked = result["total_hours"]
            proportional_base_salary = (
                self.salary.base_salary / self.MONTHLY_WORK_HOURS
            ) * total_hours_worked

            # CORRECT calculation for monthly employees
            result["total_gross_pay"] = proportional_base_salary + total_bonuses
            result["base_salary"] = float(proportional_base_salary)
            result["overtime_bonus"] = float(total_bonuses)

            logger.info(
                f"Monthly employee {self.employee.get_full_name()}: "
                f"Proportional base ₪{proportional_base_salary} ({total_hours_worked}/{self.MONTHLY_WORK_HOURS} hours) + "
                f"Bonuses ₪{total_bonuses} = Total ₪{result['total_gross_pay']}"
            )

        else:
            # Hourly employees: full daily pay calculation
            logger.info(
                f"Calculating full daily pay for hourly employee {self.employee.get_full_name()}"
            )

            for log in work_logs:
                daily_calc = self.calculate_daily_pay_hourly(log, save_to_db=True)
                result["daily_calculations"].append(daily_calc)

                # Accumulate totals
                result["total_hours"] += daily_calc["hours_worked"]
                result["total_gross_pay"] += daily_calc[
                    "total_pay"
                ]  # This is full daily pay

                # Accumulate night hours and pay
                result["night_hours"] += daily_calc.get("night_hours", Decimal("0"))
                result["night_pay"] += daily_calc.get("night_pay", Decimal("0"))
                result["sabbath_night_pay"] += daily_calc.get(
                    "sabbath_night_pay", Decimal("0")
                )

                # Accumulate sabbath night hours
                if daily_calc.get("sabbath_night_hours", Decimal("0")) > 0:
                    if "sabbath_night_hours" not in result:
                        result["sabbath_night_hours"] = Decimal("0")
                    result["sabbath_night_hours"] += daily_calc["sabbath_night_hours"]

                # Accumulate hours by type (ALWAYS accumulate breakdown data)
                if daily_calc["breakdown"]:
                    result["regular_hours"] += daily_calc["breakdown"].get(
                        "regular_hours", Decimal("0")
                    )
                    result["overtime_hours"] += daily_calc["breakdown"].get(
                        "overtime_hours_1", Decimal("0")
                    ) + daily_calc["breakdown"].get("overtime_hours_2", Decimal("0"))

                if daily_calc["is_holiday"]:
                    result["holiday_hours"] += daily_calc["hours_worked"]
                elif daily_calc["is_sabbath"]:
                    result["sabbath_hours"] += daily_calc["hours_worked"]

                if daily_calc["compensatory_day_created"]:
                    result["compensatory_days_earned"] += 1

            # Count worked days
            worked_days = len(set(log.check_in.date() for log in work_logs))
            result["worked_days"] = worked_days

            logger.info(
                f"Hourly employee {self.employee.get_full_name()}: "
                f"Total ₪{result['total_gross_pay']} for {result['total_hours']}h"
            )

        # Check legal compliance
        violations = self.validate_weekly_limits(work_logs)
        result["legal_violations"] = violations
        result["warnings"] = self.warnings

        # Apply minimum wage (if applicable)
        if (
            self.salary.currency == "ILS"
            and result["total_gross_pay"] < self.MINIMUM_WAGE_ILS
            and result["total_hours"] >= 186
        ):

            result["original_gross_pay"] = result["total_gross_pay"]
            result["total_gross_pay"] = self.MINIMUM_WAGE_ILS
            result["minimum_wage_applied"] = True
            result["minimum_wage_supplement"] = (
                self.MINIMUM_WAGE_ILS - result["original_gross_pay"]
            )

        # Round final amounts
        result["total_gross_pay"] = round(result["total_gross_pay"], 2)
        result["total_hours"] = round(result["total_hours"], 2)
        result["regular_hours"] = round(result["regular_hours"], 2)
        result["overtime_hours"] = round(result["overtime_hours"], 2)
        result["holiday_hours"] = round(result["holiday_hours"], 2)
        result["sabbath_hours"] = round(result["sabbath_hours"], 2)
        result["night_hours"] = round(result["night_hours"], 2)
        result["night_pay"] = round(result["night_pay"], 2)

        # Log API usage
        api_info = result["api_integrations"]
        logger.info(
            f"✅ Enhanced salary calculation completed for {self.employee.get_full_name()}: "
            f"₪{result['total_gross_pay']} for {result['total_hours']}h | "
            f"APIs used: SunriseSunset={api_info['sunrise_sunset_used']}, "
            f"Hebcal={api_info['hebcal_used']}, "
            f"Precise times={api_info['precise_sabbath_times']}"
        )

        # Save monthly summary to database
        self._save_monthly_summary(result)

        return result

    def validate_weekly_limits(self, work_logs):
        """
        Check compliance with weekly limits according to Israeli labor law
        """
        violations = []

        # Group work logs by week (Monday-Sunday)
        weeks = {}
        for log in work_logs:
            monday = log.check_in.date() - timedelta(days=log.check_in.weekday())
            if monday not in weeks:
                weeks[monday] = []
            weeks[monday].append(log)

        # Check each week
        for week_start, week_logs in weeks.items():
            week_end = week_start + timedelta(days=6)
            total_hours = sum(log.get_total_hours() for log in week_logs)

            regular_hours = min(total_hours, self.MAX_WEEKLY_REGULAR_HOURS)
            overtime_hours = max(
                Decimal("0"), total_hours - self.MAX_WEEKLY_REGULAR_HOURS
            )

            max_total = self.MAX_WEEKLY_REGULAR_HOURS + self.MAX_WEEKLY_OVERTIME_HOURS

            if total_hours > max_total:
                violation = {
                    "type": "weekly_hours_exceeded",
                    "week_start": week_start,
                    "week_end": week_end,
                    "total_hours": total_hours,
                    "max_allowed": max_total,
                    "excess_hours": total_hours - max_total,
                }
                violations.append(violation)

            elif overtime_hours > self.MAX_WEEKLY_OVERTIME_HOURS:
                violation = {
                    "type": "overtime_exceeded",
                    "week_start": week_start,
                    "week_end": week_end,
                    "overtime_hours": overtime_hours,
                    "max_overtime": self.MAX_WEEKLY_OVERTIME_HOURS,
                    "excess_overtime": overtime_hours - self.MAX_WEEKLY_OVERTIME_HOURS,
                }
                violations.append(violation)

        return violations

    def get_detailed_breakdown(self):
        """
        Get detailed breakdown with API integrations
        """
        # Get standard monthly calculation
        standard_result = self.calculate_monthly_salary_enhanced()

        # Initialize detailed breakdown
        breakdown = {
            "employee": self.employee.get_full_name(),
            "period": f"{self.year}-{self.month:02d}",
            "calculation_type": self.salary.calculation_type,
            "hourly_rate": (
                float(self.salary.hourly_rate) if self.salary.hourly_rate else 0
            ),
            "monthly_salary": (
                float(self.salary.base_salary) if self.salary.base_salary else 0
            ),
            "currency": self.salary.currency,
            # Detailed categories
            "regular_hours": 0.0,
            "regular_pay": 0.0,
            "overtime_day_hours": 0.0,
            "overtime_day_pay": 0.0,
            "overtime_night_hours": 0.0,
            "overtime_night_pay": 0.0,
            "overtime_125_hours": 0.0,
            "overtime_125_pay": 0.0,
            "overtime_150_hours": 0.0,
            "overtime_150_pay": 0.0,
            "sabbath_regular_hours": 0.0,
            "sabbath_regular_pay": 0.0,
            "sabbath_overtime_hours": 0.0,
            "sabbath_overtime_pay": 0.0,
            "holiday_regular_hours": 0.0,
            "holiday_regular_pay": 0.0,
            "holiday_overtime_hours": 0.0,
            "holiday_overtime_pay": 0.0,
            "total_hours": 0.0,
            "total_pay": 0.0,
            "compensatory_days": standard_result.get("compensatory_days_earned", 0),
            "legal_violations": standard_result.get("legal_violations", []),
            "warnings": standard_result.get("warnings", []),
            # API integration information
            "api_integrations": standard_result.get("api_integrations", {}),
        }

        # Process each daily calculation
        for daily_calc in standard_result.get("daily_calculations", []):
            hours = daily_calc["hours_worked"]
            is_night = daily_calc["is_night_shift"]
            is_sabbath = daily_calc["is_sabbath"]
            is_holiday = daily_calc["is_holiday"]

            if daily_calc["breakdown"]:
                regular_hours = daily_calc["breakdown"].get("regular_hours", 0)
                overtime_hours_1 = daily_calc["breakdown"].get("overtime_hours_1", 0)
                overtime_hours_2 = daily_calc["breakdown"].get("overtime_hours_2", 0)
                total_overtime = overtime_hours_1 + overtime_hours_2

                regular_pay = daily_calc["breakdown"].get("regular_pay", 0)
                overtime_pay = daily_calc["breakdown"].get(
                    "overtime_pay_1", 0
                ) + daily_calc["breakdown"].get("overtime_pay_2", 0)

                if is_sabbath:
                    # Sabbath work
                    if total_overtime > 0:
                        breakdown["sabbath_regular_hours"] += float(regular_hours)
                        breakdown["sabbath_regular_pay"] += float(regular_pay)
                        breakdown["sabbath_overtime_hours"] += float(total_overtime)
                        breakdown["sabbath_overtime_pay"] += float(overtime_pay)

                        # Overtime breakdown by rates for Sabbath work
                        overtime_175_hours = float(
                            overtime_hours_1
                        )  # First 2 hours at 175%
                        overtime_200_hours = float(
                            overtime_hours_2
                        )  # Additional hours at 200%
                        overtime_175_pay = float(
                            daily_calc["breakdown"].get("overtime_pay_1", 0)
                        )
                        overtime_200_pay = float(
                            daily_calc["breakdown"].get("overtime_pay_2", 0)
                        )

                        breakdown[
                            "overtime_125_hours"
                        ] += overtime_175_hours  # Displayed as 175%
                        breakdown["overtime_125_pay"] += overtime_175_pay
                        breakdown[
                            "overtime_150_hours"
                        ] += overtime_200_hours  # Displayed as 200%
                        breakdown["overtime_150_pay"] += overtime_200_pay
                    else:
                        breakdown["sabbath_regular_hours"] += float(hours)
                        breakdown["sabbath_regular_pay"] += float(
                            daily_calc["total_pay"]
                        )

                elif is_holiday:
                    # Holiday work
                    if total_overtime > 0:
                        breakdown["holiday_regular_hours"] += float(regular_hours)
                        breakdown["holiday_regular_pay"] += float(regular_pay)
                        breakdown["holiday_overtime_hours"] += float(total_overtime)
                        breakdown["holiday_overtime_pay"] += float(overtime_pay)

                        # Overtime breakdown by rates for holiday work
                        overtime_175_hours = float(overtime_hours_1)
                        overtime_200_hours = float(overtime_hours_2)
                        overtime_175_pay = float(
                            daily_calc["breakdown"].get("overtime_pay_1", 0)
                        )
                        overtime_200_pay = float(
                            daily_calc["breakdown"].get("overtime_pay_2", 0)
                        )

                        breakdown["overtime_125_hours"] += overtime_175_hours
                        breakdown["overtime_125_pay"] += overtime_175_pay
                        breakdown["overtime_150_hours"] += overtime_200_hours
                        breakdown["overtime_150_pay"] += overtime_200_pay
                    else:
                        breakdown["holiday_regular_hours"] += float(hours)
                        breakdown["holiday_regular_pay"] += float(
                            daily_calc["total_pay"]
                        )

                else:
                    # Regular work day
                    breakdown["regular_hours"] += float(regular_hours)
                    breakdown["regular_pay"] += float(regular_pay)

                    if total_overtime > 0:
                        # Overtime breakdown by rates for regular days
                        overtime_125_hours = float(
                            overtime_hours_1
                        )  # First 2 hours at 125%
                        overtime_150_hours = float(
                            overtime_hours_2
                        )  # Additional hours at 150%
                        overtime_125_pay = float(
                            daily_calc["breakdown"].get("overtime_pay_1", 0)
                        )
                        overtime_150_pay = float(
                            daily_calc["breakdown"].get("overtime_pay_2", 0)
                        )

                        breakdown["overtime_125_hours"] += overtime_125_hours
                        breakdown["overtime_125_pay"] += overtime_125_pay
                        breakdown["overtime_150_hours"] += overtime_150_hours
                        breakdown["overtime_150_pay"] += overtime_150_pay

                        if is_night:
                            breakdown["overtime_night_hours"] += float(total_overtime)
                            breakdown["overtime_night_pay"] += float(overtime_pay)
                        else:
                            breakdown["overtime_day_hours"] += float(total_overtime)
                            breakdown["overtime_day_pay"] += float(overtime_pay)

            breakdown["total_hours"] += float(hours)
            breakdown["total_pay"] += float(daily_calc["total_pay"])

        # Round values for display
        for key in breakdown:
            if isinstance(breakdown[key], float):
                breakdown[key] = round(breakdown[key], 2)

        return breakdown

    def calculate_monthly_salary(self):
        """
        BACKWARD COMPATIBILITY: Calls enhanced calculation method
        """
        return self.calculate_monthly_salary_enhanced()

    def calculate_daily_pay(self, work_log):
        """
        BACKWARD COMPATIBILITY: Calculate daily pay for a single WorkLog

        This method maintains compatibility with existing signal handlers
        and other parts of the codebase that expect this interface.

        Args:
            work_log: WorkLog instance

        Returns:
            dict: Daily calculation result
        """
        try:
            if self.salary.calculation_type == "monthly":
                # Monthly employees: calculate bonuses only
                return self.calculate_daily_bonuses_monthly(work_log, save_to_db=True)
            else:
                # Hourly employees: calculate full daily pay
                return self.calculate_daily_pay_hourly(work_log, save_to_db=True)
        except Exception as e:
            logger.error(f"Error in calculate_daily_pay for WorkLog {work_log.id}: {e}")
            # Return minimal result to prevent crashes
            return {
                "date": work_log.check_in.date(),
                "hours_worked": work_log.get_total_hours(),
                "total_pay": Decimal("0"),
                "error": str(e),
            }


# Create alias for backward compatibility, but with enhanced capabilities
PayrollCalculationService = EnhancedPayrollCalculationService
