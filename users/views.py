from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from .models import Employee, EmployeeInvitation
from .serializers import (
    EmployeeSerializer, 
    EmployeeUpdateSerializer,
    EmployeeInvitationSerializer,
    SendInvitationSerializer,
    AcceptInvitationSerializer
)
import logging
from core.logging_utils import safe_log_employee, get_safe_logger

logger = logging.getLogger(__name__)

class EmployeeViewSet(viewsets.ModelViewSet):
    """Endpoints for employee management with proper security"""
    queryset = Employee.objects.select_related('salary_info').all().order_by('last_name', 'first_name')
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]  # Requires authentication
    
    def get_permissions(self):
        """Override permissions for specific actions"""
        # All operations require authentication only
        # Later we can add role-based restrictions if needed
        self.permission_classes = [IsAuthenticated]
        return super().get_permissions()
    filter_backends = [SearchFilter, DjangoFilterBackend, OrderingFilter]
    search_fields = ['first_name', 'last_name', 'email']
    filterset_fields = ['employment_type', 'is_active', 'role']
    ordering_fields = ['first_name', 'last_name', 'email', 'created_at', 'updated_at']
    ordering = ['last_name', 'first_name']
    
    def get_serializer_class(self):
        """Use different serializers for create vs update operations"""
        if self.action in ['update', 'partial_update']:
            return EmployeeUpdateSerializer
        return self.serializer_class
    
    def create(self, request, *args, **kwargs):
        """Override to catch and log validation errors"""
        logger.info(f"Employee creation POST data: {request.data}")
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            logger.error(f"Employee creation validation error: {str(e)}")
            logger.error(f"Serializer errors: {serializer.errors}")
            raise
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        """Log employee creation and create default salary configuration"""
        # Debug log the incoming data
        logger.info(f"Employee creation request data: {self.request.data}")
        employee = serializer.save()
        logger.info("New employee created", extra={
            **safe_log_employee(employee, "employee_created"),
            "created_by": safe_log_employee(self.request.user, "creator") if hasattr(self.request.user, 'employee') else str(self.request.user.id)[:8]
        })
        
        # Create default salary configuration based on role
        from payroll.models import Salary
        from decimal import Decimal
        
        # Determine calculation type based on employment_type first, then role
        if employee.employment_type in ['full_time', 'part_time']:
            calculation_type = 'monthly'
            # Default monthly salaries based on role
            monthly_defaults = {
                'admin': Decimal('25000'),
                'accountant': Decimal('22000'),
                'project_manager': Decimal('28000'),
                'employee': Decimal('20000')
            }
            base_salary = monthly_defaults.get(employee.role, Decimal('20000'))
            hourly_rate = None
        elif employee.employment_type == 'hourly':
            calculation_type = 'hourly'
            # Default hourly rates based on role
            hourly_defaults = {
                'admin': Decimal('120'),
                'accountant': Decimal('100'),
                'project_manager': Decimal('130'),
                'employee': Decimal('85')
            }
            hourly_rate = hourly_defaults.get(employee.role, Decimal('85'))
            base_salary = None
        elif employee.employment_type == 'contract':
            # For contract employees, use monthly calculation instead of project to avoid date requirements
            calculation_type = 'monthly' 
            # Default monthly salary for contract employees
            contract_defaults = {
                'admin': Decimal('30000'),
                'accountant': Decimal('25000'),
                'project_manager': Decimal('35000'),
                'employee': Decimal('20000')
            }
            base_salary = contract_defaults.get(employee.role, Decimal('20000'))
            hourly_rate = None
        else:
            # Fallback to hourly for unknown employment types
            calculation_type = 'hourly'
            hourly_rate = Decimal('85')
            base_salary = None
        
        salary_data = {
            'employee': employee,
            'calculation_type': calculation_type,
            'currency': 'ILS',
            'base_salary': base_salary,
            'hourly_rate': hourly_rate
        }
        
        # Create salary configuration
        salary = Salary.objects.create(**salary_data)
        logger.info("Created default salary configuration", extra={
            **safe_log_employee(employee, "salary_config_created"),
            "calculation_type": salary.calculation_type,
            "currency": salary.currency
        })

    def perform_update(self, serializer):
        """Log employee updates and handle salary information"""
        # Get the current data before saving
        employee = self.get_object()
        request_data = self.request.data
        
        # Save the basic employee information (excluding salary fields)
        employee = serializer.save()
        
        # Handle salary updates if they are provided
        from payroll.models import Salary
        from decimal import Decimal
        
        # Check if salary data was provided in the request
        hourly_rate = request_data.get('hourly_rate')
        monthly_salary = request_data.get('monthly_salary')
        
        if hourly_rate is not None or monthly_salary is not None:
            # Get or create salary record
            if employee.employment_type in ['full_time', 'part_time']:
                default_calculation_type = 'monthly'
            elif employee.employment_type == 'hourly':
                default_calculation_type = 'hourly'
            elif employee.employment_type == 'contract':
                default_calculation_type = 'monthly'  # Use monthly for contracts to avoid project date requirements
            else:
                default_calculation_type = 'hourly'  # fallback
                
            salary, created = Salary.objects.get_or_create(
                employee=employee,
                defaults={
                    'calculation_type': default_calculation_type,
                    'currency': 'ILS'
                }
            )
            
            # Update salary fields based on employment type
            if employee.employment_type in ['full_time', 'part_time'] and monthly_salary is not None:
                try:
                    salary.base_salary = Decimal(str(monthly_salary))
                    salary.hourly_rate = None  # Clear hourly rate for monthly employees
                    salary.calculation_type = 'monthly'
                    salary.save()
                    logger.info("Updated monthly salary", extra={
                        **safe_log_employee(employee, "salary_updated"),
                        "new_monthly_salary": str(salary.base_salary)
                    })
                except (ValueError, TypeError) as e:
                    logger.error("Invalid monthly salary value", extra={
                        **safe_log_employee(employee, "salary_update_error"),
                        "error": str(e),
                        "value": monthly_salary
                    })
            elif employee.employment_type == 'hourly' and hourly_rate is not None:
                try:
                    salary.hourly_rate = Decimal(str(hourly_rate))
                    salary.base_salary = None  # Clear monthly salary for hourly employees
                    salary.calculation_type = 'hourly'
                    salary.save()
                    logger.info("Updated hourly rate", extra={
                        **safe_log_employee(employee, "salary_updated"),
                        "new_hourly_rate": str(salary.hourly_rate)
                    })
                except (ValueError, TypeError) as e:
                    logger.error("Invalid hourly rate value", extra={
                        **safe_log_employee(employee, "salary_update_error"),
                        "error": str(e),
                        "value": hourly_rate
                    })
            elif employee.employment_type == 'contract' and monthly_salary is not None:
                try:
                    salary.base_salary = Decimal(str(monthly_salary))
                    salary.hourly_rate = None  # Clear hourly rate for contract employees
                    salary.calculation_type = 'project'
                    salary.save()
                    logger.info("Updated contract project salary", extra={
                        **safe_log_employee(employee, "salary_updated"),
                        "new_project_salary": str(salary.base_salary)
                    })
                except (ValueError, TypeError) as e:
                    logger.error("Invalid contract project salary value", extra={
                        **safe_log_employee(employee, "salary_update_error"),
                        "error": str(e),
                        "value": monthly_salary
                    })
        
        logger.info("Employee updated", extra={
            **safe_log_employee(employee, "employee_updated"),
            "updated_by": safe_log_employee(self.request.user, "updater") if hasattr(self.request.user, 'employee') else str(self.request.user.id)[:8]
        })

    def perform_destroy(self, instance):
        """Soft-delete: просто деактивируем сотрудника."""
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        logger.info("Employee deleted", extra={
            "action": "employee_deleted",
            "employee_id": str(instance.id)[:8],
            "deleted_by": safe_log_employee(self.request.user, "deleter") if hasattr(self.request.user, 'employee') else str(self.request.user.id)[:8]
        })

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate deactivated employee"""
        employee = self.get_object()
        employee.is_active = True
        employee.save()
        logger.info("Employee activated", extra={
            **safe_log_employee(employee, "employee_activated"),
            "activated_by": safe_log_employee(request.user, "activator") if hasattr(request.user, 'employee') else str(request.user.id)[:8]
        })
        return Response({'status': 'Employee activated'})

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate employee"""
        employee = self.get_object()
        employee.is_active = False
        employee.save()
        logger.info("Employee deactivated", extra={
            **safe_log_employee(employee, "employee_deactivated"),
            "deactivated_by": safe_log_employee(request.user, "deactivator") if hasattr(request.user, 'employee') else str(request.user.id)[:8]
        })
        return Response({'status': 'Employee deactivated'})
    
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def send_invitation(self, request, pk=None):
        """Send invitation email to employee"""
        employee = self.get_object()
        
        # Check if employee already has user account
        if employee.is_registered:
            return Response(
                {'error': 'Employee already has an account'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check for existing valid invitation
        if hasattr(employee, 'invitation') and employee.invitation.is_valid:
            return Response(
                {'error': 'Employee already has a pending invitation'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create or update invitation
        if hasattr(employee, 'invitation'):
            invitation = employee.invitation
            invitation.token = EmployeeInvitation._meta.get_field('token').default()
            invitation.expires_at = timezone.now() + timezone.timedelta(days=2)
            invitation.invited_by = request.user
            invitation.save()
        else:
            invitation = EmployeeInvitation.create_invitation(
                employee=employee,
                invited_by=request.user
            )
        
        # Send email (for now just log it)
        invitation_url = invitation.get_invitation_url(
            request.data.get('base_url', 'http://localhost:8100')
        )
        
        # TODO: Implement actual email sending
        safe_logger = get_safe_logger(__name__)
        safe_logger.info("Invitation URL generated", extra=safe_log_employee(employee, "invitation_sent"))
        
        # Mark as sent
        invitation.email_sent = True
        invitation.email_sent_at = timezone.now()
        invitation.save()
        
        serializer = EmployeeInvitationSerializer(invitation)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ValidateInvitationView(generics.GenericAPIView):
    """Validate invitation token"""
    permission_classes = [AllowAny]
    
    def get(self, request):
        token = request.query_params.get('token')
        if not token:
            return Response(
                {'error': 'Token is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            invitation = EmployeeInvitation.objects.get(token=token)
            
            if not invitation.is_valid:
                if invitation.is_accepted:
                    return Response(
                        {'error': 'This invitation has already been accepted'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                elif invitation.is_expired:
                    return Response(
                        {'error': 'This invitation has expired'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                else:
                    return Response(
                        {'error': 'Invalid invitation'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            return Response({
                'valid': True,
                'employee': {
                    'first_name': invitation.employee.first_name,
                    'last_name': invitation.employee.last_name,
                    'email': invitation.employee.email
                },
                'expires_at': invitation.expires_at
            })
        
        except EmployeeInvitation.DoesNotExist:
            return Response(
                {'error': 'Invalid invitation token'},
                status=status.HTTP_404_NOT_FOUND
            )


class AcceptInvitationView(generics.CreateAPIView):
    """Accept invitation and create user account"""
    serializer_class = AcceptInvitationSerializer
    permission_classes = [AllowAny]
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get invitation
        invitation = EmployeeInvitation.objects.get(
            token=serializer.validated_data['token']
        )
        
        # Create user
        user = User.objects.create_user(
            username=serializer.validated_data['username'],
            password=serializer.validated_data['password'],
            email=invitation.employee.email,
            first_name=invitation.employee.first_name,
            last_name=invitation.employee.last_name
        )
        
        # Accept invitation
        invitation.accept(user)
        
        # Generate auth token
        from rest_framework.authtoken.models import Token
        token, _ = Token.objects.get_or_create(user=user)
        
        # Return response with user info and token
        return Response({
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
            },
            'employee_id': invitation.employee.id,
            'token': token.key,
            'message': 'Account created successfully. Please register your biometric data.'
        }, status=status.HTTP_201_CREATED)