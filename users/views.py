from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import SearchFilter
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
    EmployeeInvitationSerializer,
    SendInvitationSerializer,
    AcceptInvitationSerializer
)
import logging

logger = logging.getLogger(__name__)

class EmployeeViewSet(viewsets.ModelViewSet):
    """Endpoints for employee management with proper security"""
    queryset = Employee.objects.all().order_by('last_name', 'first_name')
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]  # Requires authentication
    filter_backends = [SearchFilter, DjangoFilterBackend]
    search_fields = ['first_name', 'last_name', 'email']
    filterset_fields = ['employment_type', 'is_active']

    def perform_create(self, serializer):
        """Log employee creation"""
        employee = serializer.save()
        logger.info(f"New employee created: {employee.get_full_name()} by user {self.request.user}")

    def perform_update(self, serializer):
        """Log employee updates"""
        employee = serializer.save()
        logger.info(f"Employee updated: {employee.get_full_name()} by user {self.request.user}")

    def perform_destroy(self, instance):
        """Soft delete instead of hard delete"""
        instance.is_active = False
        instance.save()
        logger.info(f"Employee deactivated: {instance.get_full_name()} by user {self.request.user}")

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate deactivated employee"""
        employee = self.get_object()
        employee.is_active = True
        employee.save()
        logger.info(f"Employee activated: {employee.get_full_name()} by user {request.user}")
        return Response({'status': 'Employee activated'})

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate employee"""
        employee = self.get_object()
        employee.is_active = False
        employee.save()
        logger.info(f"Employee deactivated: {employee.get_full_name()} by user {request.user}")
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
        logger.info(f"Invitation URL for {employee.email}: {invitation_url}")
        
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