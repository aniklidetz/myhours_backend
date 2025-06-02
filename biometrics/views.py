# biometrics/views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from users.models import Employee
import logging

logger = logging.getLogger(__name__)

# Попробуем импортировать WorkLog, если не получится - создадим временную модель
try:
    from worktime.models import WorkLog
except ImportError:
    logger.warning("WorkLog model not found, using temporary solution")
    # Временное решение - используем словарь для хранения данных
    class WorkLog:
        _data = {}
        _counter = 0
        
        @classmethod
        def create(cls, **kwargs):
            cls._counter += 1
            obj = type('WorkLog', (), {
                'id': cls._counter,
                'employee': kwargs.get('employee'),
                'check_in': kwargs.get('check_in'),
                'check_out': kwargs.get('check_out'),
                'location': kwargs.get('location_check_in', ''),
                'save': lambda: None,
                'strftime': lambda fmt: kwargs.get('check_in').strftime(fmt)
            })()
            cls._data[cls._counter] = obj
            return obj
        
        @classmethod
        def objects(cls):
            class Manager:
                @staticmethod
                def filter(**kwargs):
                    class QuerySet:
                        def __init__(self, data):
                            self.data = data
                        
                        def first(self):
                            for item in WorkLog._data.values():
                                if kwargs.get('employee') and item.employee.id == kwargs['employee'].id:
                                    if kwargs.get('check_out__isnull') and not hasattr(item, 'check_out'):
                                        return item
                            return None
                        
                        def count(self):
                            return len(self.data)
                    
                    return QuerySet(cls._data)
            
            return Manager()

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def register_face(request):
    """
    Register face for an employee (mock implementation)
    """
    employee_id = request.data.get('employee_id')
    image = request.data.get('image')
    
    if not employee_id or not image:
        return Response(
            {'error': 'Employee ID and image are required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        employee = Employee.objects.get(id=employee_id)
        
        # Mock: В реальности здесь будет сохранение биометрических данных
        logger.info(f"Face registered for employee: {employee.get_full_name()}")
        
        return Response({
            'success': True,
            'message': f'Face registered successfully for {employee.get_full_name()}'
        })
    except Employee.DoesNotExist:
        return Response(
            {'error': 'Employee not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def check_in(request):
    """
    Biometric check-in (mock implementation)
    """
    image = request.data.get('image')
    location = request.data.get('location', 'Unknown location')
    
    if not image:
        return Response(
            {'error': 'Image is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Mock: В реальности здесь будет распознавание лица
    # Для тестирования используем текущего пользователя
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        # Если нет профиля Employee, создаем его
        employee = Employee.objects.create(
            user=request.user,
            first_name=request.user.first_name or 'Test',
            last_name=request.user.last_name or 'User',
            email=request.user.email,
            role='employee'
        )
    
    # Проверяем, нет ли открытой смены
    open_worklog = WorkLog.objects.filter(
        employee=employee,
        check_out__isnull=True
    ).first()
    
    if open_worklog:
        return Response(
            {'error': 'You already have an open shift. Please check out first.'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Создаем новую запись
    worklog = WorkLog.objects.create(
        employee=employee,
        check_in=timezone.now(),
        location=location
    )
    
    logger.info(f"Check-in successful for {employee.get_full_name()} at {location}")
    
    return Response({
        'success': True,
        'employee_name': employee.get_full_name(),
        'check_in_time': worklog.check_in.strftime('%H:%M'),
        'location': location
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def check_out(request):
    """
    Biometric check-out (mock implementation)
    """
    image = request.data.get('image')
    location = request.data.get('location', 'Unknown location')
    
    if not image:
        return Response(
            {'error': 'Image is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Mock: В реальности здесь будет распознавание лица
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        return Response(
            {'error': 'Employee profile not found'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Находим открытую смену
    open_worklog = WorkLog.objects.filter(
        employee=employee,
        check_out__isnull=True
    ).first()
    
    if not open_worklog:
        return Response(
            {'error': 'No open shift found. Please check in first.'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Закрываем смену
    open_worklog.check_out = timezone.now()
    open_worklog.save()
    
    # Вычисляем отработанные часы
    duration = open_worklog.check_out - open_worklog.check_in
    hours_worked = round(duration.total_seconds() / 3600, 2)
    
    logger.info(f"Check-out successful for {employee.get_full_name()}, worked {hours_worked}h")
    
    return Response({
        'success': True,
        'employee_name': employee.get_full_name(),
        'check_out_time': open_worklog.check_out.strftime('%H:%M'),
        'hours_worked': hours_worked,
        'location': location
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def biometric_stats(request):
    """
    Get biometric statistics
    """
    # Mock statistics
    return Response({
        'registered_faces': Employee.objects.filter(is_active=True).count(),
        'active_sessions': WorkLog.objects.filter(check_out__isnull=True).count(),
        'today_checkins': WorkLog.objects.filter(
            check_in__date=timezone.now().date()
        ).count()
    })