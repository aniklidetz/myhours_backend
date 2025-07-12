# payroll/views.py - ИСПРАВЛЕНИЯ для корректного расчёта зарплаты

from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db.models import Q
from decimal import Decimal
import logging
from datetime import datetime, date, timedelta

from users.models import Employee
from users.permissions import IsEmployeeOrAbove
from .models import Salary, CompensatoryDay
from .serializers import SalarySerializer
from .enhanced_serializers import EnhancedEarningsSerializer, CompensatoryDayDetailSerializer
from worktime.models import WorkLog

logger = logging.getLogger(__name__)


# ИСПРАВЛЕНО: Используем исправленный PayrollCalculationService
from .services import PayrollCalculationService


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def backward_compatible_earnings(request):
    """
    ИСПРАВЛЕНО: Обратно совместимый endpoint для earnings с корректными расчётами
    """
    # Получение данных сотрудника
    employee_id = request.GET.get('employee_id')
    
    if employee_id:
        # Админ/бухгалтер запрашивает конкретного сотрудника
        if not (hasattr(request.user, 'employee_profile') and 
                request.user.employee_profile.role in ['accountant', 'admin']):
            return Response({
                'error': 'Permission denied'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            from users.models import Employee
            target_employee = Employee.objects.get(id=employee_id)
        except Employee.DoesNotExist:
            return Response({
                'error': 'Employee not found'
            }, status=status.HTTP_404_NOT_FOUND)
    else:
        # Пользователь запрашивает свои данные
        if not hasattr(request.user, 'employee_profile'):
            return Response({
                'error': 'User does not have an employee profile'
            }, status=status.HTTP_404_NOT_FOUND)
        target_employee = request.user.employee_profile
    
    # Получение расчётов по месяцам на основе параметров запроса
    try:
        from datetime import date
        
        # Парсим год и месяц из параметров запроса
        year = request.GET.get('year')
        month = request.GET.get('month')
        
        if year and month:
            try:
                year = int(year)
                month = int(month)
                current_date = date(year, month, 1)  # Первый день запрашиваемого месяца
            except (ValueError, TypeError):
                # Неверный год/месяц, возвращаемся к текущей дате
                current_date = date.today()
        else:
            # Нет параметров, используем текущую дату
            current_date = date.today()
        
        try:
            salary = target_employee.salary_info
        except Salary.DoesNotExist:
            # Нет конфигурации зарплаты - возвращаем данные с нулевой зарплатой, но показываем часы
            from worktime.models import WorkLog
            import calendar
            
            start_date = date(current_date.year, current_date.month, 1)
            _, last_day = calendar.monthrange(current_date.year, current_date.month)
            end_date = date(current_date.year, current_date.month, last_day)
            
            # ИСПРАВЛЕНО: Правильная фильтрация рабочих логов
            work_logs = WorkLog.objects.filter(
                employee=target_employee,
                check_out__isnull=False
            ).filter(
                Q(check_in__date__lte=end_date) & 
                Q(check_out__date__gte=start_date)
            )
            
            total_hours = sum(log.get_total_hours() for log in work_logs)
            worked_days = work_logs.values('check_in__date').distinct().count()
            
            return Response({
                "employee": {
                    "id": target_employee.id,
                    "name": target_employee.get_full_name(),
                    "email": target_employee.email,
                    "role": target_employee.role
                },
                "calculation_type": "not_configured",
                "currency": "ILS",
                "date": current_date.isoformat(),
                "month": current_date.month,
                "year": current_date.year,
                "period": "monthly",
                "total_hours": float(total_hours),
                "total_salary": 0,
                "regular_hours": float(total_hours),
                "overtime_hours": 0,
                "holiday_hours": 0,
                "shabbat_hours": 0,
                "worked_days": worked_days,
                "compensatory_days": 0,
                "bonus": 0,
                "error": "No salary configuration",
                "message": "Employee has no salary configuration. Please contact HR."
            })
        
        if salary.calculation_type == 'hourly':
            # Проверяем часовую ставку
            if not salary.hourly_rate or salary.hourly_rate <= 0:
                return Response({
                    'error': 'Invalid hourly rate configuration',
                    'details': f'Employee {target_employee.get_full_name()} has no valid hourly rate'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # ИСПРАВЛЕНО: Используем исправленный PayrollCalculationService
            try:
                service = PayrollCalculationService(target_employee, current_date.year, current_date.month)
                service_result = service.calculate_monthly_salary()
                
                # Получаем детализированный разбор для большей прозрачности
                detailed_breakdown = service.get_detailed_breakdown()
                
            except Exception as calc_error:
                logger.error(f"Error in backward_compatible_earnings for employee {target_employee.id}: {calc_error}")
                # Возвращаем безопасный fallback
                return Response({
                    "employee": {
                        "id": target_employee.id,
                        "name": target_employee.get_full_name(),
                        "email": target_employee.email,
                        "role": target_employee.role
                    },
                    "calculation_type": salary.calculation_type,
                    "currency": salary.currency,
                    "date": current_date.isoformat(),
                    "month": current_date.month,
                    "year": current_date.year,
                    "period": "monthly",
                    "total_hours": 0,
                    "total_salary": 0,
                    "regular_hours": 0,
                    "overtime_hours": 0,
                    "holiday_hours": 0,
                    "shabbat_hours": 0,
                    "worked_days": 0,
                    "compensatory_days": 0,
                    "bonus": 0,
                    "error": "Calculation failed",
                    "message": f"Salary calculation failed: {str(calc_error)}"
                })
            
            # ИСПРАВЛЕНО: Улучшенный breakdown с корректными данными
            hourly_rate = salary.hourly_rate or Decimal('0')
            
            # Извлекаем данные из service_result
            regular_hours = Decimal(str(service_result.get('regular_hours', 0)))
            regular_pay = regular_hours * hourly_rate
            
            overtime_hours = Decimal(str(service_result.get('overtime_hours', 0)))
            sabbath_hours = Decimal(str(service_result.get('sabbath_hours', 0)))
            holiday_hours = Decimal(str(service_result.get('holiday_hours', 0)))
            worked_days = service_result.get('worked_days', 0)
            
            # ИСПРАВЛЕНО: Правильный расчёт breakdown сверхурочных (125% и 150%)
            overtime_125_hours = detailed_breakdown.get('overtime_125_hours', 0)
            overtime_150_hours = detailed_breakdown.get('overtime_150_hours', 0)
            overtime_125_pay = detailed_breakdown.get('overtime_125_pay', 0)
            overtime_150_pay = detailed_breakdown.get('overtime_150_pay', 0)
            
            sabbath_pay = detailed_breakdown.get('sabbath_regular_pay', 0) + detailed_breakdown.get('sabbath_overtime_pay', 0)
            holiday_pay = detailed_breakdown.get('holiday_regular_pay', 0) + detailed_breakdown.get('holiday_overtime_pay', 0)
            
            # Структура, соответствующая ожиданиям React Native
            enhanced_response = {
                "calculation_type": salary.calculation_type,
                "compensatory_days": service_result.get('compensatory_days_earned', 0),
                "currency": salary.currency,
                "date": current_date.isoformat(),
                "employee": {
                    "email": target_employee.email,
                    "id": target_employee.id,
                    "name": target_employee.get_full_name(),
                    "role": target_employee.role
                },
                "holiday_hours": float(holiday_hours),
                "legal_violations": service_result.get('legal_violations', []),
                "minimum_wage_applied": service_result.get('minimum_wage_applied', False),
                "month": current_date.month,
                "overtime_hours": float(overtime_hours),
                "period": "monthly",
                "regular_hours": float(regular_hours),
                "shabbat_hours": float(sabbath_hours),
                "total_hours": float(service_result.get('total_hours', 0)),
                "total_salary": float(service_result.get('total_gross_pay', 0)),
                "warnings": service_result.get('warnings', []),
                "worked_days": worked_days,
                "year": current_date.year,
                
                # ИСПРАВЛЕНО: Улучшенный breakdown с детализированным разбором по шабату
                "enhanced_breakdown": {
                    "regular_pay": float(regular_pay),
                    "work_sessions": service_result.get('work_sessions_count', 0),
                    "overtime_breakdown": {
                        "overtime_125_hours": float(overtime_125_hours),
                        "overtime_125_pay": float(overtime_125_pay),
                        "overtime_150_hours": float(overtime_150_hours), 
                        "overtime_150_pay": float(overtime_150_pay)
                    },
                    "special_days": {
                        "sabbath_regular_hours": detailed_breakdown.get('sabbath_regular_hours', 0),
                        "sabbath_regular_pay": detailed_breakdown.get('sabbath_regular_pay', 0),
                        "sabbath_overtime_hours": detailed_breakdown.get('sabbath_overtime_hours', 0),
                        "sabbath_overtime_pay": detailed_breakdown.get('sabbath_overtime_pay', 0),
                        "sabbath_pay": float(sabbath_pay),
                        "holiday_pay": float(holiday_pay)
                    },
                    "rates": {
                        "base_hourly": float(salary.hourly_rate),
                        "overtime_125": float(salary.hourly_rate * Decimal('1.25')),
                        "overtime_150": float(salary.hourly_rate * Decimal('1.5')),
                        "sabbath_rate": float(salary.hourly_rate * Decimal('1.5')),
                        "holiday_rate": float(salary.hourly_rate * Decimal('1.5'))
                    }
                },
                
                # Детализированный breakdown для прозрачности
                "detailed_breakdown": detailed_breakdown,
                
                # Bonus информация (legacy поле, которое ожидает UI)
                "bonus": float(overtime_125_pay + overtime_150_pay + sabbath_pay + holiday_pay),
                
                # Дополнительные поля для UI
                "hourly_rate": float(salary.hourly_rate),
                "regular_pay_amount": float(regular_pay),
                "work_sessions_count": service_result.get('work_sessions_count', 0)
            }
            
        else:
            # Сотрудник на месячном окладе - упрощённая структура
            try:
                service = PayrollCalculationService(target_employee, current_date.year, current_date.month)
                service_result = service.calculate_monthly_salary()
            except Exception as calc_error:
                logger.error(f"Error in backward_compatible_earnings for monthly employee {target_employee.id}: {calc_error}")
                # Возвращаем безопасный fallback для месячных сотрудников
                return Response({
                    "employee": {
                        "id": target_employee.id,
                        "name": target_employee.get_full_name(),
                        "email": target_employee.email,
                        "role": target_employee.role
                    },
                    "base_salary": float(salary.base_salary or 0),
                    "calculation_type": salary.calculation_type,
                    "currency": salary.currency,
                    "date": current_date.isoformat(),
                    "month": current_date.month,
                    "year": current_date.year,
                    "period": "monthly",
                    "total_hours": 0,
                    "total_salary": 0,
                    "worked_days": 0,
                    "compensatory_days": 0,
                    "bonus": 0,
                    "error": "Calculation failed",
                    "message": f"Monthly salary calculation failed: {str(calc_error)}"
                })
            
            # ИСПРАВЛЕНО: Вычисляем реальные отработанные часы для месячных сотрудников
            from worktime.models import WorkLog
            import calendar
            
            # Вычисляем точные границы месяца
            start_date = date(current_date.year, current_date.month, 1)
            _, last_day = calendar.monthrange(current_date.year, current_date.month)
            end_date = date(current_date.year, current_date.month, last_day)
            
            # ИСПРАВЛЕНО: Получаем рабочие логи для месяца с правильной фильтрацией
            work_logs = WorkLog.objects.filter(
                employee=target_employee,
                check_out__isnull=False
            ).filter(
                Q(check_in__date__lte=end_date) & 
                Q(check_out__date__gte=start_date)
            )
            
            # Вычисляем общее количество отработанных часов
            total_hours = sum(log.get_total_hours() for log in work_logs)
            
            enhanced_response = {
                "base_salary": float(service_result.get('base_salary', salary.base_salary or 0)),
                "calculation_type": salary.calculation_type,
                "compensatory_days": service_result.get('compensatory_days_earned', 0),
                "currency": salary.currency,
                "date": current_date.isoformat(),
                "employee": {
                    "email": target_employee.email,
                    "id": target_employee.id,
                    "name": target_employee.get_full_name(),
                    "role": target_employee.role
                },
                "holiday_hours": float(service_result.get('holiday_hours', 0)),
                "month": current_date.month,
                "overtime_hours": float(service_result.get('overtime_hours', 0)),
                "period": "monthly",
                "shabbat_hours": float(service_result.get('sabbath_hours', 0)),
                "total_extra": float(service_result.get('total_extra', 0)),
                "total_hours": float(total_hours),  # ← ИСПРАВЛЕНО: теперь считаем реальные часы
                "total_salary": float(service_result.get('total_gross_pay', 0)),
                "total_working_days": service_result.get('total_working_days', 0),
                "work_proportion": float(service_result.get('work_proportion', 0)),
                "worked_days": work_logs.filter(check_out__isnull=False).values('check_in__date').distinct().count() or work_logs.values('check_in__date').distinct().count(),
                "year": current_date.year,
                
                # Bonus информация (extras для месячных сотрудников)
                "bonus": float(service_result.get('total_extra', 0)),
                
                # Дополнительные поля для UI
                "work_sessions_count": work_logs.count(),
                "attendance_percentage": ((work_logs.filter(check_out__isnull=False).values('check_in__date').distinct().count() or work_logs.values('check_in__date').distinct().count()) / service_result.get('total_working_days', 1)) * 100 if service_result.get('total_working_days', 0) > 0 else 0
            }
        
        return Response(enhanced_response)
        
    except Exception as e:
        logger.exception("Error in backward_compatible_earnings")
        return Response({
            'error': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def enhanced_earnings(request):
    """
    ИСПРАВЛЕНО: Получение улучшенных earnings с детализированным breakdown
    """
    logger.info(f"🔍 ENHANCED_EARNINGS FUNCTION CALLED with params: {request.GET}")
    logger.info(f"🔍 ENHANCED_EARNINGS USER: {request.user}")
    
    try:
        # Используем логику разрешений и параметров из current_earnings
        employee_id = request.GET.get('employee_id')
        period = request.GET.get('period', 'monthly')
        date_str = request.GET.get('date')
        year_str = request.GET.get('year')
        month_str = request.GET.get('month')
        
        # Парсим дату - поддерживаем параметры date и year/month
        if year_str and month_str:
            try:
                year = int(year_str)
                month = int(month_str)
                target_date = date(year, month, 1)
            except (ValueError, TypeError):
                return Response({
                    'error': 'Invalid year or month parameter'
                }, status=status.HTTP_400_BAD_REQUEST)
        elif date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    'error': 'Invalid date format. Use YYYY-MM-DD'
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            target_date = timezone.now().date()
        
        # Определяем целевого сотрудника (та же логика, что в current_earnings)
        if employee_id:
            if not (hasattr(request.user, 'employee_profile') and 
                    request.user.employee_profile.role in ['accountant', 'admin']):
                return Response({
                    'error': 'Permission denied. You can only view your own earnings.'
                }, status=status.HTTP_403_FORBIDDEN)
            
            try:
                target_employee = Employee.objects.get(id=employee_id)
            except Employee.DoesNotExist:
                return Response({
                    'error': 'Employee not found'
                }, status=status.HTTP_404_NOT_FOUND)
        else:
            if not hasattr(request.user, 'employee_profile'):
                return Response({
                    'error': 'User does not have an employee profile'
                }, status=status.HTTP_404_NOT_FOUND)
            target_employee = request.user.employee_profile
        
        try:
            # Пытаемся получить информацию о зарплате, но обрабатываем случай, если её нет
            try:
                salary = target_employee.salary_info
            except Salary.DoesNotExist:
                # Нет конфигурации зарплаты - возвращаем нулевые earnings, но всё равно показываем данные сотрудника
                logger.warning(f"No salary configuration for employee {target_employee.id} ({target_employee.get_full_name()})")
                
                # Вычисляем отработанные часы даже без конфигурации зарплаты
                from worktime.models import WorkLog
                import calendar
                
                start_date = date(target_date.year, target_date.month, 1)
                _, last_day = calendar.monthrange(target_date.year, target_date.month)
                end_date = date(target_date.year, target_date.month, last_day)
                
                # ИСПРАВЛЕНО: Правильная фильтрация рабочих логов
                work_logs = WorkLog.objects.filter(
                    employee=target_employee,
                    check_out__isnull=False
                ).filter(
                    Q(check_in__date__lte=end_date) & 
                    Q(check_out__date__gte=start_date)
                )
                
                total_hours = sum(log.get_total_hours() for log in work_logs)
                worked_days = work_logs.values('check_in__date').distinct().count()
                
                # Возвращаем данные с нулевой зарплатой, но показываем отработанные часы
                return Response({
                    "employee": {
                        "id": target_employee.id,
                        "name": target_employee.get_full_name(),
                        "email": target_employee.email,
                        "role": target_employee.role
                    },
                    "period": f"{target_date.year}-{target_date.month:02d}",
                    "calculation_type": "not_configured",
                    "currency": "ILS",
                    "month": target_date.month,
                    "year": target_date.year,
                    "total_hours": float(total_hours),
                    "total_salary": 0,
                    "regular_hours": float(total_hours),
                    "overtime_hours": 0,
                    "holiday_hours": 0,
                    "shabbat_hours": 0,
                    "worked_days": worked_days,
                    "base_salary": 0,
                    "hourly_rate": 0,
                    "total_working_days": 0,
                    "work_proportion": 0,
                    "compensatory_days": 0,
                    "bonus": 0,
                    "error": "No salary configuration",
                    "message": "Employee has no salary configuration. Please contact HR to set up salary details."
                })
            
            # Поддерживаем только месячный период для enhanced view изначально
            if period != 'monthly':
                return Response({
                    'error': 'Enhanced earnings currently only supports monthly period'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # ИСПРАВЛЕНО: Используем исправленный PayrollCalculationService
            logger.info(f"🔍 ENHANCED_EARNINGS: About to calculate salary for {target_employee.get_full_name()}")
            try:
                service = PayrollCalculationService(target_employee, target_date.year, target_date.month)
                calc_result = service.calculate_monthly_salary()
                logger.info(f"🔍 ENHANCED_EARNINGS: Salary calculation successful for {target_employee.get_full_name()}")
            except Exception as calc_error:
                logger.error(f"Error calculating salary for employee {target_employee.id}: {calc_error}")
                # Возвращаем fallback данные с нулевыми расчётами
                calc_result = {
                    'total_gross_pay': 0,
                    'base_salary': 0,
                    'overtime_hours': 0,
                    'holiday_hours': 0,
                    'sabbath_hours': 0,
                    'worked_days': 0,
                    'total_working_days': 0,
                    'work_proportion': 0,
                    'compensatory_days_earned': 0,
                    'total_extra': 0
                }
            
            # Получаем детализированный breakdown
            try:
                detailed_breakdown = service.get_detailed_breakdown()
            except Exception as breakdown_error:
                logger.error(f"Error getting detailed breakdown for employee {target_employee.id}: {breakdown_error}")
                detailed_breakdown = {}
            
            # ИСПРАВЛЕНО: Вычисляем реальные отработанные часы из WorkLog
            from worktime.models import WorkLog
            import calendar
            
            # Вычисляем точные границы месяца
            start_date = date(target_date.year, target_date.month, 1)
            _, last_day = calendar.monthrange(target_date.year, target_date.month)
            end_date = date(target_date.year, target_date.month, last_day)
            
            # ИСПРАВЛЕНО: Получаем рабочие логи для месяца с правильной фильтрацией
            work_logs = WorkLog.objects.filter(
                employee=target_employee,
                check_out__isnull=False
            ).filter(
                Q(check_in__date__lte=end_date) & 
                Q(check_out__date__gte=start_date)
            )
            
            # Вычисляем общее количество отработанных часов
            total_hours = sum(log.get_total_hours() for log in work_logs)
            
            # Debug log для проверки расчёта общих часов
            logger.info(f"🔍 Total hours calculated: {total_hours} for {work_logs.count()} work logs")
            
            # Строим ответ на основе типа расчёта
            if salary.calculation_type == 'hourly':
                # Для почасовых сотрудников извлекаем часы из calc_result
                regular_hours = float(calc_result.get('regular_hours', total_hours))
                overtime_hours = float(calc_result.get('overtime_hours', 0))
                holiday_hours = float(calc_result.get('holiday_hours', 0))
                shabbat_hours = float(calc_result.get('sabbath_hours', 0))
                
                # Если calc_result не имеет разбивки по часам, используем total_hours
                if regular_hours == 0 and total_hours > 0:
                    regular_hours = float(total_hours)
            else:
                # Для месячных сотрудников
                regular_hours = float(total_hours)
                overtime_hours = float(calc_result.get('overtime_hours', 0))
                holiday_hours = float(calc_result.get('holiday_hours', 0))
                shabbat_hours = float(calc_result.get('sabbath_hours', 0))
            
            # ИСПРАВЛЕНО: Вычисляем детализированный breakdown с помощью улучшенной функции
            logger.info(f"🔍 ENHANCED_EARNINGS: Starting breakdown calculation for {target_employee.get_full_name()}")
            combined_breakdown = {
                'overtime_125_hours': 0,
                'overtime_150_hours': 0,
                'overtime_125_pay': 0,
                'overtime_150_pay': 0,
                'sabbath_150_hours': 0,
                'sabbath_175_hours': 0,
                'sabbath_150_pay': 0,
                'sabbath_175_pay': 0,
            }
            
            # ИСПРАВЛЕНО: Обрабатываем каждый рабочий лог для получения детализированного breakdown
            logger.info(f"🔍 ENHANCED_EARNINGS: Processing {work_logs.count()} work logs")
            for log in work_logs:
                if log.check_out and log.check_in:
                    # Вычисляем отработанные часы
                    hours_worked = (log.check_out - log.check_in).total_seconds() / 3600
                    work_date = log.check_in.date()
                    
                    logger.info(f"🔍 ENHANCED_EARNINGS: Processing log {work_date} - {hours_worked:.2f}h")
                    
                    # ИСПРАВЛЕНО: Используем исправленный метод расчёта дневной оплаты
                    try:
                        daily_result = service.calculate_daily_pay(log)
                        daily_breakdown = daily_result.get('breakdown', {})
                        logger.info(f"🔍 ENHANCED_EARNINGS: Daily breakdown keys: {list(daily_breakdown.keys())}")
                        
                        # Добавляем overtime breakdown
                        if 'overtime_hours_1' in daily_breakdown:
                            combined_breakdown['overtime_125_hours'] += daily_breakdown.get('overtime_hours_1', 0)
                            combined_breakdown['overtime_125_pay'] += daily_breakdown.get('overtime_pay_1', 0)
                        
                        if 'overtime_hours_2' in daily_breakdown:
                            combined_breakdown['overtime_150_hours'] += daily_breakdown.get('overtime_hours_2', 0)
                            combined_breakdown['overtime_150_pay'] += daily_breakdown.get('overtime_pay_2', 0)
                        
                        # Добавляем sabbath breakdown для специальных дней
                        if daily_result.get('is_sabbath'):
                            regular_sabbath_hours = min(hours_worked, 7)  # Первые 7 часов шабата
                            overtime_sabbath_hours = max(0, hours_worked - 7)  # Сверхурочные шабата
                            
                            combined_breakdown['sabbath_150_hours'] += regular_sabbath_hours
                            combined_breakdown['sabbath_150_pay'] += daily_breakdown.get('regular_pay', 0)
                            
                            if overtime_sabbath_hours > 0:
                                combined_breakdown['sabbath_175_hours'] += overtime_sabbath_hours
                                combined_breakdown['sabbath_175_pay'] += (
                                    daily_breakdown.get('overtime_pay_1', 0) + 
                                    daily_breakdown.get('overtime_pay_2', 0)
                                )
                                
                    except Exception as daily_error:
                        logger.error(f"Error processing daily calculation for {work_date}: {daily_error}")
                        continue

            # Возвращаем данные в enhanced формате, совместимом с frontend
            enhanced_data = {
                "employee": {
                    "id": target_employee.id,
                    "name": target_employee.get_full_name(),
                    "email": target_employee.email,
                    "role": target_employee.role
                },
                "period": f"{target_date.year}-{target_date.month:02d}",
                "calculation_type": salary.calculation_type,
                "currency": salary.currency,
                "month": target_date.month,
                "year": target_date.year,
                "total_hours": float(total_hours),
                "total_salary": float(calc_result.get('total_gross_pay', 0)),
                "regular_hours": regular_hours,
                "overtime_hours": overtime_hours,
                "holiday_hours": holiday_hours,
                "shabbat_hours": shabbat_hours,
                "worked_days": calc_result.get('worked_days', 0),
                "base_salary": float(calc_result.get('base_salary', 0)) if salary.calculation_type == 'monthly' else 0,
                "hourly_rate": float(salary.hourly_rate) if salary.calculation_type == 'hourly' else 0,
                "total_working_days": calc_result.get('total_working_days', 0),
                "work_proportion": float(calc_result.get('work_proportion', 0)),
                "compensatory_days": calc_result.get('compensatory_days_earned', 0),
                "bonus": float(calc_result.get('total_extra', 0)) if 'total_extra' in calc_result else 0,
                # Добавляем детализированный breakdown с правильным разбором overtime коэффициентов
                "detailed_breakdown": {
                    **detailed_breakdown,
                    **combined_breakdown
                },
                "_debug_info": {
                    "detailed_breakdown_keys": list(detailed_breakdown.keys()),
                    "combined_breakdown_keys": list(combined_breakdown.keys()),
                    "function_reached": "enhanced_earnings"
                }
            }
            
            return Response(enhanced_data)
        except Exception as e:
            logger.exception("Error calculating enhanced earnings")
            return Response({
                'error': 'Internal server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        logger.exception("Error in enhanced_earnings")
        return Response({
            'error': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ИСПРАВЛЕНО: Улучшенная функция расчёта дневных earnings с исправленным PayrollCalculationService
def _calculate_hourly_daily_earnings(salary, work_logs, target_date, total_hours):
    """
    ИСПРАВЛЕНО: Расчёт дневных earnings для почасовых сотрудников с правильными коэффициентами
    """
    
    from integrations.models import Holiday
    
    # Конвертируем total_hours в Decimal для точных вычислений
    total_hours = Decimal(str(total_hours))
    
    # Проверяем, является ли это праздником или шабатом
    holiday = Holiday.objects.filter(date=target_date).first()
    
    breakdown = {
        'regular_hours': 0,
        'overtime_hours': 0,
        'holiday_hours': 0,
        'shabbat_hours': 0
    }
    
    total_earnings = Decimal('0.00')
    
    if holiday and holiday.is_shabbat:
        # ИСПРАВЛЕНО: Работа в шабат - 150% для обычных часов, 175% для сверхурочных
        # Проверяем, является ли какой-либо рабочий лог для этого дня ночной сменой
        is_night_shift = False
        for work_log in work_logs:
            if work_log.check_in.date() == target_date:
                # Проверяем, является ли это ночной сменой (простая проверка на основе времени начала)
                check_in_hour = work_log.check_in.hour
                # Ночная смена: начинается между 18:00-06:00 следующего дня
                if check_in_hour >= 18 or check_in_hour <= 6:
                    is_night_shift = True
                    break
        
        # Получаем дневную норму на основе типа смены
        if is_night_shift:
            daily_norm = Decimal('7')  # Ночная смена: макс. 7 обычных часов
        else:
            daily_norm = Decimal('8.6')  # Обычная дневная норма
        
        sabbath_breakdown = {}
        if total_hours <= daily_norm:
            # Все шабатные часы по 150%
            sabbath_150_pay = total_hours * (salary.hourly_rate * Decimal('1.5'))
            total_earnings = sabbath_150_pay
            sabbath_breakdown['sabbath_150_hours'] = float(total_hours)
            sabbath_breakdown['sabbath_150_pay'] = float(sabbath_150_pay)
            sabbath_breakdown['rate_150'] = float(salary.hourly_rate * Decimal('1.5'))
        else:
            # ИСПРАВЛЕНО: Обычные шабатные часы (150%) + Сверхурочные шабатные часы (175%)
            regular_sabbath = daily_norm
            overtime_sabbath = total_hours - daily_norm
            
            sabbath_150_pay = regular_sabbath * (salary.hourly_rate * Decimal('1.5'))
            sabbath_175_pay = overtime_sabbath * (salary.hourly_rate * Decimal('1.75'))
            total_earnings += sabbath_150_pay + sabbath_175_pay
            
            sabbath_breakdown['sabbath_150_hours'] = float(regular_sabbath)
            sabbath_breakdown['sabbath_150_pay'] = float(sabbath_150_pay)
            sabbath_breakdown['rate_150'] = float(salary.hourly_rate * Decimal('1.5'))
            sabbath_breakdown['sabbath_175_hours'] = float(overtime_sabbath)
            sabbath_breakdown['sabbath_175_pay'] = float(sabbath_175_pay)
            sabbath_breakdown['rate_175'] = float(salary.hourly_rate * Decimal('1.75'))
        
        breakdown['shabbat_hours'] = float(total_hours)
        breakdown['shabbat_breakdown'] = sabbath_breakdown
    elif holiday and holiday.is_holiday:
        # Работа в праздник - 150%
        total_earnings = total_hours * (salary.hourly_rate * Decimal('1.5'))
        breakdown['holiday_hours'] = float(total_hours)
    else:
        # ИСПРАВЛЕНО: Обычный день - используем правильную дневную норму на основе дня недели и типа смены
        # Проверяем, является ли какой-либо рабочий лог для этого дня ночной сменой
        is_night_shift = False
        for work_log in work_logs:
            if work_log.check_in.date() == target_date:
                # Проверяем, является ли это ночной сменой (простая проверка на основе времени начала)
                check_in_hour = work_log.check_in.hour
                # Ночная смена: начинается между 18:00-06:00 следующего дня
                if check_in_hour >= 18 or check_in_hour <= 6:
                    is_night_shift = True
                    break
        
        # ИСПРАВЛЕНО: Получаем дневную норму на основе типа смены
        if is_night_shift:
            daily_norm = Decimal('7')  # Ночная смена: макс. 7 обычных часов
        else:
            # Пятница имеет сокращённые часы
            if target_date.weekday() == 4:
                daily_norm = Decimal('7.6')
            else:
                daily_norm = Decimal('8.6')
        
        if total_hours <= daily_norm:
            # Обычные часы
            total_earnings = total_hours * salary.hourly_rate
            breakdown['regular_hours'] = float(total_hours)
        else:
            # ИСПРАВЛЕНО: Обычные + сверхурочные часы
            regular_hours = daily_norm
            overtime_hours = total_hours - daily_norm
            
            # Обычные часы по базовой ставке
            total_earnings += regular_hours * salary.hourly_rate
            breakdown['regular_hours'] = float(regular_hours)
            
            # ИСПРАВЛЕНО: Расчёт сверхурочных с детализированным breakdown
            overtime_earnings = Decimal('0')
            overtime_breakdown = {}
            
            if overtime_hours <= Decimal('2'):
                # Первые 2 часа по 125%
                overtime_125 = overtime_hours
                overtime_125_pay = overtime_125 * (salary.hourly_rate * Decimal('1.25'))
                overtime_earnings += overtime_125_pay
                overtime_breakdown['overtime_125_hours'] = float(overtime_125)
                overtime_breakdown['overtime_125_pay'] = float(overtime_125_pay)
                overtime_breakdown['rate_125'] = float(salary.hourly_rate * Decimal('1.25'))
            else:
                # Первые 2 часа по 125%, остальные по 150%
                overtime_125 = Decimal('2')
                overtime_150 = overtime_hours - Decimal('2')
                overtime_125_pay = overtime_125 * (salary.hourly_rate * Decimal('1.25'))
                overtime_150_pay = overtime_150 * (salary.hourly_rate * Decimal('1.5'))
                overtime_earnings += overtime_125_pay + overtime_150_pay
                overtime_breakdown['overtime_125_hours'] = float(overtime_125)
                overtime_breakdown['overtime_125_pay'] = float(overtime_125_pay)
                overtime_breakdown['rate_125'] = float(salary.hourly_rate * Decimal('1.25'))
                overtime_breakdown['overtime_150_hours'] = float(overtime_150)
                overtime_breakdown['overtime_150_pay'] = float(overtime_150_pay)
                overtime_breakdown['rate_150'] = float(salary.hourly_rate * Decimal('1.5'))
            
            total_earnings += overtime_earnings
            breakdown['overtime_hours'] = float(overtime_hours)
            breakdown['overtime_breakdown'] = overtime_breakdown
    
    return {
        'total_earnings': round(total_earnings, 2),
        'hours_worked': float(total_hours),
        'breakdown': breakdown,
        'base_rate': salary.hourly_rate,
        'rates_applied': {
            'regular': salary.hourly_rate,
            'overtime_125': salary.hourly_rate * Decimal('1.25'),
            'overtime_150': salary.hourly_rate * Decimal('1.5'),
            'holiday': salary.hourly_rate * Decimal('1.5'),
            'sabbath_150': salary.hourly_rate * Decimal('1.5'),
            'sabbath_175': salary.hourly_rate * Decimal('1.75')
        }
    }