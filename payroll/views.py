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
from .models import Salary
from .serializers import SalarySerializer
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
        if total_hours <= 8:
            # Regular hours
            total_earnings = total_hours * salary.hourly_rate
            breakdown['regular_hours'] = float(total_hours)
        else:
            # Regular + overtime
            regular_hours = Decimal('8')
            overtime_hours = total_hours - 8
            
            # Regular 8 hours
            total_earnings += regular_hours * salary.hourly_rate
            breakdown['regular_hours'] = 8
            
            # Overtime calculation
            if overtime_hours <= 2:
                # First 2 hours at 125%
                total_earnings += overtime_hours * (salary.hourly_rate * Decimal('1.25'))
            else:
                # First 2 hours at 125%, remaining at 150%
                total_earnings += Decimal('2') * (salary.hourly_rate * Decimal('1.25'))
                total_earnings += (overtime_hours - 2) * (salary.hourly_rate * Decimal('1.5'))
            
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