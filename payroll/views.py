from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
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


class SalaryViewSet(viewsets.ModelViewSet):
    """Endpoints for employee salaries"""
    queryset = Salary.objects.all().order_by('id')
    serializer_class = SalarySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['employee', 'currency']

    @action(detail=True, methods=['post'])
    def calculate(self, request, pk=None):
        """Endpoint for salary recalculation"""
        salary = self.get_object()
        now = timezone.now()
        result = salary.calculate_monthly_salary(now.month, now.year)
        
        # If the result is a dictionary and contains total_salary
        if isinstance(result, dict) and 'total_salary' in result:
            calculated_salary = result['total_salary']
        else:
            calculated_salary = result
            
        return Response({
            "message": "Salary recalculated", 
            "salary": calculated_salary,
            "details": result if isinstance(result, dict) else {}
        })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_earnings(request):
    """
    Get current earnings for the authenticated user or specified employee.
    
    Permissions:
    - Employee: Can only see their own earnings
    - Accountant: Can see all employees' earnings
    - Admin: Can see all employees' earnings
    
    Query Parameters:
    - employee_id (optional): ID of employee to check (accountant/admin only)
    - period (optional): 'daily', 'weekly', 'monthly' (default: 'monthly')
    - date (optional): Specific date in YYYY-MM-DD format (default: today)
    """
    
    # Get query parameters
    employee_id = request.GET.get('employee_id')
    period = request.GET.get('period', 'monthly')
    date_str = request.GET.get('date')
    
    # Parse date
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({
                'error': 'Invalid date format. Use YYYY-MM-DD'
            }, status=status.HTTP_400_BAD_REQUEST)
    else:
        target_date = timezone.now().date()
    
    # Determine target employee
    if employee_id:
        # Check if user has permission to view other employees' data
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
        # User wants to see their own earnings
        if not hasattr(request.user, 'employee_profile'):
            return Response({
                'error': 'User does not have an employee profile'
            }, status=status.HTTP_404_NOT_FOUND)
        target_employee = request.user.employee_profile
    
    try:
        # Get salary information
        salary = target_employee.salary_info
        
        # Calculate earnings based on period
        if period == 'daily':
            earnings = calculate_daily_earnings(salary, target_date)
        elif period == 'weekly':
            earnings = calculate_weekly_earnings(salary, target_date)
        elif period == 'monthly':
            earnings = calculate_monthly_earnings(salary, target_date)
        else:
            return Response({
                'error': 'Invalid period. Use daily, weekly, or monthly'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Add employee information
        earnings.update({
            'employee': {
                'id': target_employee.id,
                'name': target_employee.get_full_name(),
                'email': target_employee.email,
                'role': target_employee.role
            },
            'period': period,
            'date': target_date.isoformat(),
            'calculation_type': salary.calculation_type,
            'currency': salary.currency
        })
        
        return Response(earnings)
        
    except Salary.DoesNotExist:
        return Response({
            'error': 'Salary information not found for this employee'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error calculating earnings: {e}")
        return Response({
            'error': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def calculate_daily_earnings(salary, target_date):
    """Calculate earnings for a specific day"""
    
    # Get work logs for the specific day
    work_logs = WorkLog.objects.filter(
        employee=salary.employee,
        check_in__date=target_date,
        check_out__isnull=False  # Only completed work sessions
    )
    
    if not work_logs.exists():
        return {
            'total_earnings': Decimal('0.00'),
            'hours_worked': 0,
            'breakdown': {
                'regular_hours': 0,
                'overtime_hours': 0,
                'holiday_hours': 0,
                'shabbat_hours': 0
            },
            'message': 'No completed work sessions for this date'
        }
    
    # Calculate total hours for the day
    total_hours = sum(log.get_total_hours() for log in work_logs)
    
    if salary.calculation_type == 'hourly':
        return _calculate_hourly_daily_earnings(salary, work_logs, target_date, total_hours)
    elif salary.calculation_type == 'monthly':
        return _calculate_monthly_daily_earnings(salary, work_logs, target_date, total_hours)
    elif salary.calculation_type == 'project':
        return _calculate_project_daily_earnings(salary, target_date, total_hours)
    
    return {'total_earnings': Decimal('0.00'), 'hours_worked': float(total_hours)}


def _calculate_hourly_daily_earnings(salary, work_logs, target_date, total_hours):
    """Calculate daily earnings for hourly employees"""
    
    from integrations.models import Holiday
    
    # Convert total_hours to Decimal for precise calculations
    total_hours = Decimal(str(total_hours))
    
    # Check if it's a holiday or Shabbat
    holiday = Holiday.objects.filter(date=target_date).first()
    
    breakdown = {
        'regular_hours': 0,
        'overtime_hours': 0,
        'holiday_hours': 0,
        'shabbat_hours': 0
    }
    
    total_earnings = Decimal('0.00')
    
    if holiday and holiday.is_shabbat:
        # Shabbat work - 150%
        total_earnings = total_hours * (salary.hourly_rate * Decimal('1.5'))
        breakdown['shabbat_hours'] = float(total_hours)
    elif holiday and holiday.is_holiday:
        # Holiday work - 150%
        total_earnings = total_hours * (salary.hourly_rate * Decimal('1.5'))
        breakdown['holiday_hours'] = float(total_hours)
    else:
        # Regular day
        if total_hours <= Decimal('8'):
            # Regular hours
            total_earnings = total_hours * salary.hourly_rate
            breakdown['regular_hours'] = float(total_hours)
        else:
            # Regular + overtime
            regular_hours = Decimal('8')
            overtime_hours = total_hours - Decimal('8')
            
            # Regular 8 hours
            total_earnings += regular_hours * salary.hourly_rate
            breakdown['regular_hours'] = 8
            
            # Overtime calculation
            if overtime_hours <= Decimal('2'):
                # First 2 hours at 125%
                total_earnings += overtime_hours * (salary.hourly_rate * Decimal('1.25'))
            else:
                # First 2 hours at 125%, remaining at 150%
                total_earnings += Decimal('2') * (salary.hourly_rate * Decimal('1.25'))
                total_earnings += (overtime_hours - Decimal('2')) * (salary.hourly_rate * Decimal('1.5'))
            
            breakdown['overtime_hours'] = float(overtime_hours)
    
    return {
        'total_earnings': round(total_earnings, 2),
        'hours_worked': float(total_hours),
        'breakdown': breakdown,
        'base_rate': salary.hourly_rate,
        'rates_applied': {
            'regular': salary.hourly_rate,
            'overtime_1_2h': salary.hourly_rate * Decimal('1.25'),
            'overtime_3plus': salary.hourly_rate * Decimal('1.5'),
            'holiday_shabbat': salary.hourly_rate * Decimal('1.5')
        }
    }


def _calculate_monthly_daily_earnings(salary, work_logs, target_date, total_hours):
    """Calculate daily earnings for monthly salary employees"""
    
    # For monthly salary, calculate proportional daily rate
    working_days_in_month = salary.get_working_days_in_month(target_date.year, target_date.month)
    
    if working_days_in_month == 0:
        daily_base_rate = Decimal('0')
    else:
        daily_base_rate = salary.base_salary / working_days_in_month
    
    # Calculate extra payments for overtime/holidays
    from integrations.models import Holiday
    holiday = Holiday.objects.filter(date=target_date).first()
    
    extra_earnings = Decimal('0.00')
    breakdown = {
        'base_daily_salary': float(daily_base_rate),
        'overtime_bonus': 0,
        'holiday_bonus': 0,
        'shabbat_bonus': 0
    }
    
    if holiday:
        if holiday.is_shabbat:
            # Shabbat bonus - 50% extra
            extra_earnings = total_hours * (salary.hourly_rate * Decimal('0.5'))
            breakdown['shabbat_bonus'] = float(extra_earnings)
        elif holiday.is_holiday:
            # Holiday bonus - 50% extra
            extra_earnings = total_hours * (salary.hourly_rate * Decimal('0.5'))
            breakdown['holiday_bonus'] = float(extra_earnings)
    
    # Overtime bonus for monthly employees
    if total_hours > 8:
        overtime_hours = total_hours - 8
        overtime_1 = min(overtime_hours, 2)
        overtime_2 = max(0, overtime_hours - 2)
        
        overtime_bonus = (overtime_1 * salary.hourly_rate * Decimal('0.25') + 
                         overtime_2 * salary.hourly_rate * Decimal('0.5'))
        extra_earnings += overtime_bonus
        breakdown['overtime_bonus'] = float(overtime_bonus)
    
    total_earnings = daily_base_rate + extra_earnings
    
    return {
        'total_earnings': round(total_earnings, 2),
        'hours_worked': float(total_hours),
        'breakdown': breakdown,
        'working_days_in_month': working_days_in_month
    }


def _calculate_project_daily_earnings(salary, target_date, total_hours):
    """Calculate daily earnings for project-based employees"""
    
    if not salary.project_start_date or not salary.project_end_date:
        return {
            'total_earnings': Decimal('0.00'),
            'hours_worked': float(total_hours),
            'breakdown': {'error': 'Project dates not configured'}
        }
    
    # Check if date is within project period
    if target_date < salary.project_start_date or target_date > salary.project_end_date:
        return {
            'total_earnings': Decimal('0.00'),
            'hours_worked': float(total_hours),
            'breakdown': {'error': 'Date outside project period'}
        }
    
    # Calculate daily rate based on project duration
    total_project_days = (salary.project_end_date - salary.project_start_date).days + 1
    daily_rate = salary.base_salary / total_project_days if total_project_days > 0 else Decimal('0')
    
    return {
        'total_earnings': round(daily_rate, 2),
        'hours_worked': float(total_hours),
        'breakdown': {
            'daily_project_rate': float(daily_rate),
            'project_total': float(salary.base_salary),
            'project_days': total_project_days
        }
    }


def calculate_weekly_earnings(salary, target_date):
    """Calculate earnings for the week containing target_date"""
    
    # Find start of week (Monday)
    week_start = target_date - timedelta(days=target_date.weekday())
    week_end = week_start + timedelta(days=6)
    
    # Get work logs for the week
    work_logs = WorkLog.objects.filter(
        employee=salary.employee,
        check_in__date__gte=week_start,
        check_in__date__lte=week_end,
        check_out__isnull=False
    )
    
    if not work_logs.exists():
        return {
            'total_earnings': Decimal('0.00'),
            'hours_worked': 0,
            'week_start': week_start.isoformat(),
            'week_end': week_end.isoformat(),
            'message': 'No completed work sessions for this week'
        }
    
    # Group by day and calculate daily earnings
    daily_earnings = {}
    total_weekly_earnings = Decimal('0.00')
    total_weekly_hours = 0
    
    for day_offset in range(7):
        current_day = week_start + timedelta(days=day_offset)
        day_logs = work_logs.filter(check_in__date=current_day)
        
        if day_logs.exists():
            day_earnings = calculate_daily_earnings(salary, current_day)
            daily_earnings[current_day.isoformat()] = day_earnings
            total_weekly_earnings += Decimal(str(day_earnings['total_earnings']))
            total_weekly_hours += day_earnings['hours_worked']
    
    return {
        'total_earnings': round(total_weekly_earnings, 2),
        'hours_worked': total_weekly_hours,
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
        'daily_breakdown': daily_earnings
    }


def calculate_monthly_earnings(salary, target_date):
    """Calculate earnings for the month containing target_date"""
    
    month = target_date.month
    year = target_date.year
    
    # Use existing monthly calculation method
    result = salary.calculate_monthly_salary(month, year)
    
    # Get additional details
    work_logs = WorkLog.objects.filter(
        employee=salary.employee,
        check_in__year=year,
        check_in__month=month,
        check_out__isnull=False
    )
    
    total_hours = sum(log.get_total_hours() for log in work_logs)
    worked_days = work_logs.values('check_in__date').distinct().count()
    
    if isinstance(result, dict):
        return {
            **result,
            'total_hours': total_hours,
            'worked_days': worked_days,
            'month': month,
            'year': year
        }
    else:
        return {
            'total_earnings': result,
            'total_hours': total_hours,
            'worked_days': worked_days,
            'month': month,
            'year': year
        }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def employee_earnings_summary(request):
    """
    Get earnings summary for employees.
    
    Permissions:
    - Employee: Can only see their own summary
    - Accountant/Admin: Can see all employees
    """
    
    # Check permissions
    if hasattr(request.user, 'employee_profile'):
        user_role = request.user.employee_profile.role
        if user_role in ['accountant', 'admin']:
            # Can see all employees
            employees = Employee.objects.filter(is_active=True)
        else:
            # Can only see self
            employees = Employee.objects.filter(id=request.user.employee_profile.id)
    else:
        return Response({
            'error': 'User does not have an employee profile'
        }, status=status.HTTP_404_NOT_FOUND)
    
    target_date = timezone.now().date()
    summaries = []
    
    for employee in employees:
        try:
            salary = employee.salary_info
            
            # Get current month earnings
            monthly_earnings = calculate_monthly_earnings(salary, target_date)
            
            # Get today's earnings if they worked today
            daily_earnings = calculate_daily_earnings(salary, target_date)
            
            summary = {
                'employee': {
                    'id': employee.id,
                    'name': employee.get_full_name(),
                    'email': employee.email,
                    'role': employee.role
                },
                'current_month': monthly_earnings,
                'today': daily_earnings,
                'calculation_type': salary.calculation_type,
                'currency': salary.currency
            }
            
            summaries.append(summary)
            
        except Salary.DoesNotExist:
            summaries.append({
                'employee': {
                    'id': employee.id,
                    'name': employee.get_full_name(),
                    'email': employee.email,
                    'role': employee.role
                },
                'error': 'No salary information configured'
            })
    
    return Response({
        'summaries': summaries,
        'date': target_date.isoformat(),
        'user_role': user_role if hasattr(request.user, 'employee_profile') else 'unknown'
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def attendance_report(request):
    """
    Get detailed attendance report showing absences and deductions.
    
    Permissions:
    - Employee: Can only see their own report
    - Accountant/Admin: Can see all employees' reports
    
    Query Parameters:
    - employee_id (optional): ID of employee (accountant/admin only)
    - month (optional): Month (1-12, default: current month)
    - year (optional): Year (default: current year)
    """
    
    # Get query parameters
    employee_id = request.GET.get('employee_id')
    month = request.GET.get('month')
    year = request.GET.get('year')
    
    # Parse month and year
    current_date = timezone.now().date()
    if month:
        try:
            month = int(month)
            if month < 1 or month > 12:
                raise ValueError("Month must be between 1 and 12")
        except ValueError:
            return Response({
                'error': 'Invalid month. Must be between 1 and 12'
            }, status=status.HTTP_400_BAD_REQUEST)
    else:
        month = current_date.month
    
    if year:
        try:
            year = int(year)
            if year < 2020 or year > 2030:
                raise ValueError("Year must be between 2020 and 2030")
        except ValueError:
            return Response({
                'error': 'Invalid year. Must be between 2020 and 2030'
            }, status=status.HTTP_400_BAD_REQUEST)
    else:
        year = current_date.year
    
    # Determine target employee
    if employee_id:
        # Check if user has permission to view other employees' data
        if not (hasattr(request.user, 'employee_profile') and 
                request.user.employee_profile.role in ['accountant', 'admin']):
            return Response({
                'error': 'Permission denied. You can only view your own attendance.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            target_employee = Employee.objects.get(id=employee_id)
        except Employee.DoesNotExist:
            return Response({
                'error': 'Employee not found'
            }, status=status.HTTP_404_NOT_FOUND)
    else:
        # User wants to see their own attendance
        if not hasattr(request.user, 'employee_profile'):
            return Response({
                'error': 'User does not have an employee profile'
            }, status=status.HTTP_404_NOT_FOUND)
        target_employee = request.user.employee_profile
    
    try:
        salary = target_employee.salary_info
        
        # Calculate attendance details
        attendance_data = calculate_attendance_details(salary, month, year)
        
        # Add employee information
        attendance_data.update({
            'employee': {
                'id': target_employee.id,
                'name': target_employee.get_full_name(),
                'email': target_employee.email,
                'role': target_employee.role
            },
            'month': month,
            'year': year,
            'calculation_type': salary.calculation_type,
            'currency': salary.currency
        })
        
        return Response(attendance_data)
        
    except Salary.DoesNotExist:
        return Response({
            'error': 'Salary information not found for this employee'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error calculating attendance: {e}")
        return Response({
            'error': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def calculate_attendance_details(salary, month, year):
    """Calculate detailed attendance information including absences and deductions"""
    
    # Get basic salary calculation
    result = salary.calculate_monthly_salary(month, year)
    
    if not isinstance(result, dict):
        result = {'total_salary': result}
    
    # Get work logs for the month
    work_logs = WorkLog.objects.filter(
        employee=salary.employee,
        check_in__year=year,
        check_in__month=month,
        check_out__isnull=False
    )
    
    # Get all working days in the month
    working_days = get_working_days_in_month(year, month)
    worked_days = set(log.check_in.date() for log in work_logs)
    missed_days = working_days - worked_days
    
    # Calculate deductions for monthly employees
    if salary.calculation_type == 'monthly':
        total_working_days = len(working_days)
        actual_worked_days = len(worked_days)
        
        if total_working_days > 0:
            attendance_rate = actual_worked_days / total_working_days
            base_salary_proportion = salary.base_salary * Decimal(str(attendance_rate))
            deduction_amount = salary.base_salary - base_salary_proportion
        else:
            attendance_rate = 0
            base_salary_proportion = Decimal('0')
            deduction_amount = salary.base_salary
        
        deduction_details = {
            'base_salary': salary.base_salary,
            'proportional_salary': base_salary_proportion,
            'deduction_amount': deduction_amount,
            'deduction_percentage': round((1 - attendance_rate) * 100, 2),
            'attendance_rate': round(attendance_rate * 100, 2)
        }
    else:
        # For hourly/project employees, no base deductions
        deduction_details = {
            'note': 'Deductions not applicable for this employment type'
        }
    
    # Detailed day-by-day breakdown
    daily_breakdown = []
    for work_date in sorted(working_days):
        day_info = {
            'date': work_date.isoformat(),
            'day_name': work_date.strftime('%A'),
            'worked': work_date in worked_days,
            'is_weekend': work_date.weekday() >= 5,
            'is_holiday': False
        }
        
        # Check if it's a holiday
        from integrations.models import Holiday
        holiday = Holiday.objects.filter(date=work_date).first()
        if holiday and holiday.is_holiday:
            day_info['is_holiday'] = True
            day_info['holiday_name'] = holiday.name
        
        # Get work details if worked
        if work_date in worked_days:
            day_logs = work_logs.filter(check_in__date=work_date)
            total_hours = sum(log.get_total_hours() for log in day_logs)
            day_info['hours_worked'] = round(total_hours, 2)
            day_info['sessions'] = len(day_logs)
        
        daily_breakdown.append(day_info)
    
    return {
        **result,
        'attendance_summary': {
            'total_working_days': len(working_days),
            'days_worked': len(worked_days),
            'days_missed': len(missed_days),
            'attendance_rate': round((len(worked_days) / len(working_days)) * 100, 2) if working_days else 0,
            'missed_days_list': [day.isoformat() for day in sorted(missed_days)]
        },
        'deduction_details': deduction_details,
        'daily_breakdown': daily_breakdown
    }


def get_working_days_in_month(year, month):
    """Get set of working days in a month (excluding weekends and holidays)"""
    
    working_days = set()
    
    # Get all days in the month
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)
    
    current_date = start_date
    while current_date <= end_date:
        # Skip weekends (Saturday = 5, Sunday = 6)
        if current_date.weekday() < 5:  # Monday = 0, Friday = 4
            # Check if it's not a holiday
            from integrations.models import Holiday
            holiday = Holiday.objects.filter(date=current_date, is_holiday=True).first()
            if not holiday:
                working_days.add(current_date)
        current_date += timedelta(days=1)
    
    return working_days


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def enhanced_earnings(request):
    """
    Get enhanced earnings with detailed breakdown for UI display.
    
    This endpoint provides comprehensive payroll information including:
    - Detailed hours breakdown by overtime rates
    - Pay breakdown with special day calculations
    - Compensatory days information
    - Legal compliance status
    - Daily breakdown with work types
    
    Permissions: Same as current_earnings
    Query Parameters: Same as current_earnings
    """
    
    # Reuse permission and parameter logic from current_earnings
    employee_id = request.GET.get('employee_id')
    period = request.GET.get('period', 'monthly')
    date_str = request.GET.get('date')
    year_str = request.GET.get('year')
    month_str = request.GET.get('month')
    
    # Parse date - support both date parameter and year/month parameters
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
    
    # Determine target employee (same logic as current_earnings)
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
        # Get salary information
        salary = target_employee.salary_info
        
        # Only support monthly period for enhanced view initially
        if period != 'monthly':
            return Response({
                'error': 'Enhanced earnings currently only supports monthly period'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create a mock object with required attributes for serializer
        class EarningsContext:
            def __init__(self, employee, year, month, salary):
                self.employee = employee
                self.year = year
                self.month = month
                self.calculation_type = salary.calculation_type
                self.currency = salary.currency
        
        context = EarningsContext(
            target_employee, 
            target_date.year, 
            target_date.month,
            salary
        )
        
        # Use enhanced serializer
        serializer = EnhancedEarningsSerializer()
        enhanced_data = serializer.to_representation(context)
        
        return Response(enhanced_data)
        
    except Salary.DoesNotExist:
        return Response({
            'error': 'Salary information not found for this employee'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception("Error calculating enhanced earnings")
        return Response({
            'error': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def compensatory_days_detail(request):
    """
    Get detailed compensatory days information for an employee.
    
    Query Parameters:
    - employee_id (optional): ID of employee (accountant/admin only)
    - year (optional): Year filter
    - month (optional): Month filter
    - status (optional): 'used', 'unused', 'all' (default: 'all')
    """
    
    employee_id = request.GET.get('employee_id')
    year = request.GET.get('year')
    month = request.GET.get('month')
    status_filter = request.GET.get('status', 'all')
    
    # Determine target employee (same permission logic)
    if employee_id:
        if not (hasattr(request.user, 'employee_profile') and 
                request.user.employee_profile.role in ['accountant', 'admin']):
            return Response({
                'error': 'Permission denied. You can only view your own compensatory days.'
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
        # Get compensatory days with filters
        queryset = CompensatoryDay.objects.filter(employee=target_employee)
        
        if year:
            try:
                year = int(year)
                queryset = queryset.filter(date_earned__year=year)
            except ValueError:
                return Response({
                    'error': 'Invalid year format'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        if month:
            try:
                month = int(month)
                if month < 1 or month > 12:
                    raise ValueError("Month must be between 1 and 12")
                queryset = queryset.filter(date_earned__month=month)
            except ValueError:
                return Response({
                    'error': 'Invalid month. Must be between 1 and 12'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        if status_filter == 'used':
            queryset = queryset.filter(date_used__isnull=False)
        elif status_filter == 'unused':
            queryset = queryset.filter(date_used__isnull=True)
        # 'all' - no additional filter
        
        queryset = queryset.order_by('-date_earned')
        
        # Get balance summary
        from .services import CompensatoryDayService
        balance = CompensatoryDayService.get_compensatory_day_balance(target_employee)
        
        # Serialize compensatory days
        serializer = CompensatoryDayDetailSerializer(queryset, many=True)
        
        return Response({
            'employee': {
                'id': target_employee.id,
                'name': target_employee.get_full_name(),
                'email': target_employee.email,
                'role': target_employee.role
            },
            'balance_summary': balance,
            'compensatory_days': serializer.data,
            'filters_applied': {
                'year': year,
                'month': month,
                'status': status_filter
            }
        })
        
    except Exception as e:
        logger.error(f"Error fetching compensatory days: {e}")
        return Response({
            'error': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def backward_compatible_earnings(request):
    """
    Backward compatible earnings endpoint that returns enhanced data
    in the old structure format that React Native expects.
    """
    
    # Get employee data
    employee_id = request.GET.get('employee_id')
    
    if employee_id:
        # Admin/accountant requesting specific employee
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
        # User requesting their own data
        if not hasattr(request.user, 'employee_profile'):
            return Response({
                'error': 'User does not have an employee profile'
            }, status=status.HTTP_404_NOT_FOUND)
        target_employee = request.user.employee_profile
    
    # Get current month calculations
    try:
        from datetime import date
        current_date = date.today()
        salary = target_employee.salary_info
        
        if salary.calculation_type == 'hourly':
            calc_result = calculate_monthly_earnings(salary, current_date)
            
            # Calculate enhanced breakdown - ensure all values are Decimal
            regular_hours = Decimal(str(calc_result.get('regular_hours', 0)))
            regular_pay = regular_hours * (salary.hourly_rate or Decimal('0'))
            
            overtime_hours = Decimal(str(calc_result.get('overtime_hours', 0)))
            sabbath_hours = Decimal(str(calc_result.get('shabbat_hours', 0)))
            holiday_hours = Decimal(str(calc_result.get('holiday_hours', 0)))
            worked_days = Decimal(str(calc_result.get('worked_days', 0)))
            
            # Calculate overtime breakdown (125% and 150%)
            overtime_125_hours = min(overtime_hours, Decimal('2') * worked_days)  # Max 2h per day
            overtime_150_hours = max(Decimal('0'), overtime_hours - overtime_125_hours)
            
            overtime_125_pay = overtime_125_hours * (salary.hourly_rate * Decimal('1.25'))
            overtime_150_pay = overtime_150_hours * (salary.hourly_rate * Decimal('1.5'))
            
            sabbath_pay = sabbath_hours * (salary.hourly_rate * Decimal('1.5'))
            holiday_pay = holiday_hours * (salary.hourly_rate * Decimal('1.5'))
            
            # Structure that matches what React Native expects
            enhanced_response = {
                "calculation_type": salary.calculation_type,
                "compensatory_days": calc_result.get('compensatory_days', 0),
                "currency": salary.currency,
                "date": current_date.isoformat(),
                "employee": {
                    "email": target_employee.email,
                    "id": target_employee.id,
                    "name": target_employee.get_full_name(),
                    "role": target_employee.role
                },
                "holiday_hours": float(holiday_hours),
                "legal_violations": calc_result.get('legal_violations', []),
                "minimum_wage_applied": calc_result.get('minimum_wage_applied', False),
                "month": current_date.month,
                "overtime_hours": float(overtime_hours),
                "period": "monthly",
                "regular_hours": float(calc_result.get('regular_hours', 0)),
                "shabbat_hours": float(sabbath_hours),
                "total_hours": float(calc_result.get('total_hours', 0)),
                "total_salary": float(calc_result.get('total_salary', 0)),
                "warnings": calc_result.get('warnings', []),
                "worked_days": calc_result.get('worked_days', 0),
                "year": current_date.year,
                
                # Enhanced breakdown data
                "enhanced_breakdown": {
                    "regular_pay": float(regular_pay),
                    "overtime_breakdown": {
                        "overtime_125_hours": float(overtime_125_hours),
                        "overtime_125_pay": float(overtime_125_pay),
                        "overtime_150_hours": float(overtime_150_hours), 
                        "overtime_150_pay": float(overtime_150_pay)
                    },
                    "special_days": {
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
                
                # Bonus information (legacy field that UI expects)
                "bonus": float(overtime_125_pay + overtime_150_pay + sabbath_pay + holiday_pay)
            }
            
        else:
            # Monthly employee - simpler structure
            calc_result = salary.calculate_monthly_salary(current_date.month, current_date.year)
            
            enhanced_response = {
                "base_salary": float(calc_result.get('base_salary', 0)),
                "calculation_type": salary.calculation_type,
                "compensatory_days": calc_result.get('compensatory_days', 0),
                "currency": salary.currency,
                "date": current_date.isoformat(),
                "employee": {
                    "email": target_employee.email,
                    "id": target_employee.id,
                    "name": target_employee.get_full_name(),
                    "role": target_employee.role
                },
                "holiday_hours": float(calc_result.get('holiday_hours', 0)),
                "month": current_date.month,
                "overtime_hours": float(calc_result.get('overtime_hours', 0)),
                "period": "monthly",
                "shabbat_hours": float(calc_result.get('shabbat_hours', 0)),
                "total_extra": float(calc_result.get('total_extra', 0)),
                "total_hours": float(calc_result.get('total_hours', 0)),
                "total_salary": float(calc_result.get('total_salary', 0)),
                "total_working_days": calc_result.get('total_working_days', 0),
                "work_proportion": float(calc_result.get('work_proportion', 0)),
                "worked_days": calc_result.get('worked_days', 0),
                "year": current_date.year,
                
                # Bonus information (extras for monthly employees)
                "bonus": float(calc_result.get('total_extra', 0))
            }
        
        return Response(enhanced_response)
        
    except Exception as e:
        logger.exception("Error in backward_compatible_earnings")
        return Response({
            'error': 'Internal server error'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def demo_enhanced_data(request):
    """
    Demo endpoint showing enhanced payroll data structure.
    Returns realistic demo data for UI development.
    """
    
    # Get actual employee data if available
    if hasattr(request.user, 'employee_profile'):
        employee = request.user.employee_profile
        employee_data = {
            "id": employee.id,
            "name": employee.get_full_name(),
            "email": employee.email,
            "role": employee.role
        }
    else:
        employee_data = {
            "id": 55,
            "name": "Yosef Abramov",
            "email": "yosef.abramov@test.com",
            "role": "employee"
        }
    
    # Return enhanced demo data structure
    demo_data = {
        "employee": employee_data,
        "period": "2025-06",
        "calculation_type": "hourly",
        "currency": "ILS",
        
        "summary": {
            "total_gross_pay": 6240.00,
            "total_hours": 51.0,
            "worked_days": 6,
            "compensatory_days_earned": 1
        },
        
        "hours_breakdown": {
            "regular_hours": 47.0,
            "overtime": {
                "first_2h_per_day": 2.0,     # 125% rate
                "additional_hours": 2.0,      # 150% rate
                "holiday_overtime": 0.0,      # 175% rate
                "sabbath_overtime": 0.0       # 175% rate
            },
            "special_days": {
                "holiday_hours": 0.0,         # 150% rate
                "sabbath_hours": 4.0,         # 150% rate (from previous month)
                "regular_friday_evening": 0.0
            }
        },
        
        "pay_breakdown": {
            "regular_pay": 5640.00,           # 47h * ₪120
            "overtime_pay": {
                "first_2h": 300.00,           # 2h * ₪150 (125%)
                "additional": 360.00,         # 2h * ₪180 (150%)
                "holiday_overtime": 0.00,
                "sabbath_overtime": 0.00
            },
            "special_day_pay": {
                "holiday_base": 0.00,
                "sabbath_base": 720.00,       # 4h * ₪180 (150%) from prev month
                "friday_evening": 0.00
            },
            "bonuses": {
                "attendance_bonus": 0,
                "performance_bonus": 0,
                "other_bonuses": 0
            },
            "minimum_wage_supplement": 0
        },
        
        "compensatory_days": {
            "earned_this_period": 1,
            "total_balance": {
                "unused_holiday": 0,
                "unused_sabbath": 1,
                "total_unused": 1
            },
            "details": [
                {
                    "date_earned": "2024-12-27",
                    "reason": "shabbat",
                    "sabbath_start": "2024-12-27T16:26:22+02:00",
                    "sabbath_end": "2024-12-28T17:30:15+02:00",
                    "is_used": False
                }
            ]
        },
        
        "legal_compliance": {
            "violations": [],
            "warnings": ["Exceeded 10 hours on 2025-06-21"],
            "weekly_overtime_status": {
                "current_week_overtime": 4.0,
                "max_allowed": 16.0,
                "remaining": 12.0
            }
        },
        
        "rates_applied": {
            "base_hourly": 120.0,
            "overtime_125": 150.0,
            "overtime_150": 180.0,
            "overtime_175": 210.0,
            "overtime_200": 240.0,
            "holiday_base": 180.0,
            "sabbath_base": 180.0
        },
        
        "daily_breakdown": [
            {
                "date": "2025-06-20",
                "hours_worked": 9.0,
                "type": "regular",
                "gross_pay": 1080.00,
                "breakdown": {
                    "regular": 8.0,
                    "overtime_125": 1.0
                }
            },
            {
                "date": "2025-06-21", 
                "hours_worked": 10.0,
                "type": "regular",
                "gross_pay": 1260.00,
                "breakdown": {
                    "regular": 8.0,
                    "overtime_125": 2.0
                }
            },
            {
                "date": "2025-06-22",
                "hours_worked": 8.0,
                "type": "regular", 
                "gross_pay": 960.00,
                "breakdown": {
                    "regular": 8.0
                }
            },
            {
                "date": "2024-12-27",
                "hours_worked": 4.0,
                "type": "sabbath",
                "sabbath_times": {
                    "start": "2024-12-27T16:26:22+02:00",
                    "end": "2024-12-28T17:30:15+02:00"
                },
                "gross_pay": 720.00,
                "breakdown": {
                    "sabbath_base": 4.0
                },
                "compensatory_day": True
            }
        ],
        
        "attendance": {
            "working_days_in_period": 22,
            "days_worked": 6,
            "days_missed": 16,
            "attendance_rate": 27.27
        }
    }
    
    return Response(demo_data)