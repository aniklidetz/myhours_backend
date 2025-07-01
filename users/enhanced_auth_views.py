# users/enhanced_auth_views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.contrib.auth import authenticate
from django.utils import timezone
from django.conf import settings
from drf_spectacular.utils import extend_schema, OpenApiExample
import logging
import uuid

from .token_models import DeviceToken, BiometricSession
from .permissions import IsEmployeeOrAbove, BiometricVerificationRequired
from .authentication import DeviceTokenAuthentication
from biometrics.services.mongodb_service import mongodb_service
from biometrics.services.face_processor import face_processor

logger = logging.getLogger(__name__)


@extend_schema(
    operation_id='enhanced_login',
    tags=['Authentication'],
    summary='Enhanced login with device tracking',
    description='''
    Enhanced login system that creates device-specific tokens with expiration.
    
    **Features:**
    - Device-specific token generation
    - Token expiration (configurable TTL)
    - Device information tracking
    - Location tracking
    - Security logging
    
    **Response includes:**
    - Device token for API authentication
    - User information with role
    - Token expiration time
    - Device registration status
    ''',
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'email': {'type': 'string', 'format': 'email'},
                'password': {'type': 'string'},
                'device_id': {'type': 'string', 'description': 'Unique device identifier'},
                'device_info': {
                    'type': 'object',
                    'properties': {
                        'platform': {'type': 'string'},
                        'os_version': {'type': 'string'},
                        'app_version': {'type': 'string'},
                        'device_model': {'type': 'string'}
                    }
                },
                'location': {
                    'type': 'object',
                    'properties': {
                        'latitude': {'type': 'number'},
                        'longitude': {'type': 'number'},
                        'accuracy': {'type': 'number'}
                    }
                }
            },
            'required': ['email', 'password', 'device_id']
        }
    },
    responses={
        200: OpenApiExample(
            'Login Success',
            value={
                'success': True,
                'token': 'abc123...',
                'expires_at': '2025-06-12T21:00:00Z',
                'user': {
                    'id': 15,
                    'email': 'admin@example.com',
                    'first_name': 'Admin',
                    'last_name': 'User',
                    'role': 'admin',
                    'is_staff': True
                },
                'device_registered': True,
                'biometric_required': True,
                'security_info': {
                    'requires_biometric_verification': True,
                    'last_biometric_verification': None,
                    'device_trusted': False
                }
            }
        ),
        401: OpenApiExample(
            'Login Failed',
            value={
                'error': True,
                'code': 'AUTHENTICATION_FAILED',
                'message': 'Invalid email or password',
                'error_id': 'auth_001',
                'timestamp': '2025-06-05T21:00:00Z'
            }
        )
    }
)
@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([])
def enhanced_login(request):
    """
    Enhanced login with device tracking and security features
    """
    try:
        # Extract login data
        email = request.data.get('email')
        password = request.data.get('password')
        device_id = request.data.get('device_id')
        device_info = request.data.get('device_info', {})
        location = request.data.get('location')
        
        # Validate required fields
        if not all([email, password, device_id]):
            return Response({
                'error': True,
                'code': 'MISSING_REQUIRED_FIELDS',
                'message': 'Email, password, and device_id are required',
                'details': None,
                'error_id': 'auth_001',
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Authenticate user - try both email and username
        user = authenticate(username=email, password=password)
        if not user:
            # Try authenticating with email as username
            from django.contrib.auth.models import User
            try:
                user_obj = User.objects.get(email=email)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                pass
        if not user:
            logger.warning("Failed login attempt - invalid credentials")
            return Response({
                'error': True,
                'code': 'AUTHENTICATION_FAILED',
                'message': 'Invalid email or password',
                'details': None,
                'error_id': 'auth_002',
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        if not user.is_active:
            return Response({
                'error': True,
                'code': 'USER_INACTIVE',
                'message': 'User account is disabled',
                'details': None,
                'error_id': 'auth_003',
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Check if user has employee profile
        if not hasattr(user, 'employee_profile'):
            return Response({
                'error': True,
                'code': 'NO_EMPLOYEE_PROFILE',
                'message': 'User does not have an employee profile',
                'details': None,
                'error_id': 'auth_004',
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_400_BAD_REQUEST)
        
        employee = user.employee_profile
        
        # Create or update device token
        ttl_days = getattr(settings, 'AUTH_TOKEN_TTL_DAYS', 7)
        device_token = DeviceToken.create_token(
            user=user,
            device_id=device_id,
            device_info=device_info,
            ttl_days=ttl_days
        )
        
        # Check if biometric registration exists
        biometric_registered = bool(mongodb_service.get_face_embeddings(employee.id))
        
        # Determine if biometric verification is required
        requires_biometric = (
            biometric_registered and 
            device_token.requires_biometric_verification()
        )
        
        # Log successful login
        logger.info(f"Enhanced login successful: user={user.username}, device={device_id[:8]}...")
        
        return Response({
            'success': True,
            'token': device_token.token,
            'expires_at': device_token.expires_at.isoformat(),
            'user': {
                'id': employee.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': employee.role,
                'is_staff': user.is_staff,
                'is_superuser': user.is_superuser
            },
            'device_registered': True,
            'biometric_registered': biometric_registered,
            'security_info': {
                'requires_biometric_verification': requires_biometric,
                'last_biometric_verification': device_token.biometric_verified_at.isoformat() if device_token.biometric_verified_at else None,
                'device_trusted': not requires_biometric,
                'token_expires_in_days': ttl_days
            }
        })
        
    except Exception as e:
        logger.error(f"Enhanced login error: {e}")
        return Response({
            'error': True,
            'code': 'INTERNAL_SERVER_ERROR',
            'message': 'Login system error',
            'details': None,
            'error_id': 'auth_005',
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    operation_id='biometric_verification',
    tags=['Authentication'],
    summary='Biometric verification for 2FA',
    description='''
    Perform biometric verification to enhance security for sensitive operations.
    
    **Process:**
    1. User provides face image
    2. System matches against registered biometric data
    3. Creates biometric session if successful
    4. Marks device token as biometrically verified
    
    **Use Cases:**
    - Initial login 2FA
    - Sensitive operation verification (payroll, admin actions)
    - Periodic re-verification for security
    ''',
    responses={
        200: OpenApiExample(
            'Verification Success',
            value={
                'success': True,
                'biometric_session_id': 'abc-123-def',
                'confidence_score': 0.95,
                'session_expires_at': '2025-06-06T05:00:00Z',
                'verification_level': 'high',
                'access_granted': {
                    'payroll': True,
                    'admin_actions': True,
                    'time_tracking': True
                }
            }
        )
    }
)
@api_view(['POST'])
@permission_classes([IsEmployeeOrAbove])
@authentication_classes([DeviceTokenAuthentication])
def biometric_verification(request):
    """
    Biometric verification for 2FA and sensitive operations
    """
    try:
        image = request.data.get('image')
        operation_type = request.data.get('operation_type', 'general')
        location = request.data.get('location')
        
        if not image:
            return Response({
                'error': True,
                'code': 'MISSING_IMAGE',
                'message': 'Biometric image is required',
                'details': None,
                'error_id': 'bio_001',
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_400_BAD_REQUEST)
        
        employee = request.user.employee_profile
        device_token = request.device_token
        
        # Get all active embeddings for matching
        all_embeddings = mongodb_service.get_all_active_embeddings()
        if not all_embeddings:
            return Response({
                'error': True,
                'code': 'NO_BIOMETRIC_DATA',
                'message': 'No biometric data found in system',
                'details': None,
                'error_id': 'bio_002',
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Find matching employee
        match_result = face_processor.find_matching_employee(image, all_embeddings)
        
        if not match_result['success']:
            logger.warning("Biometric verification failed")
            return Response({
                'error': True,
                'code': 'BIOMETRIC_VERIFICATION_FAILED',
                'message': 'Biometric verification failed',
                'details': None,
                'error_id': 'bio_003',
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Verify that the matched employee is the requesting user
        if match_result['employee_id'] != employee.id:
            logger.warning(f"Biometric mismatch detected for user ID {request.user.id}")
            return Response({
                'error': True,
                'code': 'BIOMETRIC_MISMATCH',
                'message': 'Biometric verification mismatch',
                'details': None,
                'error_id': 'bio_004',
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Create biometric session
        confidence_score = match_result.get('confidence', 0.0)
        quality_score = match_result.get('quality_check', {}).get('quality_score', 0.0)
        
        # Determine session duration based on operation type
        if operation_type == 'payroll':
            ttl_hours = 0.5  # 30 minutes for payroll operations
        elif operation_type == 'admin_actions':
            ttl_hours = 1    # 1 hour for admin actions
        else:
            ttl_hours = getattr(settings, 'BIOMETRIC_SESSION_TTL_HOURS', 8)
        
        biometric_session = BiometricSession.create_session(
            device_token=device_token,
            confidence_score=confidence_score,
            quality_score=quality_score,
            location=location,
            ip_address=request.META.get('REMOTE_ADDR'),
            ttl_hours=ttl_hours
        )
        
        # Mark device token as biometrically verified
        device_token.mark_biometric_verified()
        
        # Determine access levels
        verification_level = 'high' if confidence_score >= 0.9 else 'medium' if confidence_score >= 0.7 else 'low'
        access_granted = {
            'payroll': verification_level in ['high', 'medium'] and operation_type == 'payroll',
            'admin_actions': verification_level == 'high' and operation_type == 'admin_actions',
            'time_tracking': verification_level in ['high', 'medium', 'low']
        }
        
        logger.info("Biometric verification successful for user")
        
        try:
            session_id = str(biometric_session.session_id) if biometric_session and biometric_session.session_id else None
            expires_at = biometric_session.expires_at.isoformat() if biometric_session and biometric_session.expires_at else None
        except Exception:
            session_id = None
            expires_at = None
            
        return Response({
            'success': True,
            'biometric_session_id': session_id,
            'verification_level': verification_level,
            'access_granted': access_granted
        })
        
    except Exception as e:
        logger.exception("Biometric verification error")
        return Response({
            'error': True,
            'code': 'INTERNAL_SERVER_ERROR',
            'message': 'Biometric verification system error',
            'details': None,
            'error_id': 'bio_005',
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    operation_id='refresh_token',
    tags=['Authentication'],
    summary='Refresh authentication token',
    description='''
    Refresh an existing authentication token to extend its expiration.
    
    **Security Features:**
    - Only valid, non-expired tokens can be refreshed
    - Biometric re-verification may be required for sensitive refresh
    - Token usage tracking and logging
    ''',
)
@api_view(['POST'])
@permission_classes([IsEmployeeOrAbove])
@authentication_classes([DeviceTokenAuthentication])
def refresh_token(request):
    """
    Refresh authentication token
    """
    try:
        device_token = request.device_token
        ttl_days = request.data.get('ttl_days', getattr(settings, 'AUTH_TOKEN_TTL_DAYS', 7))
        
        if device_token.refresh(ttl_days=ttl_days):
            logger.info(f"Token refresh successful: user={request.user.username}, "
                       f"device={device_token.device_id[:8]}...")
            
            return Response({
                'success': True,
                'token': device_token.token,
                'expires_at': device_token.expires_at.isoformat(),
                'refreshed_at': timezone.now().isoformat(),
                'ttl_days': ttl_days
            })
        else:
            return Response({
                'error': True,
                'code': 'TOKEN_REFRESH_FAILED',
                'message': 'Token cannot be refreshed',
                'details': None,
                'error_id': 'refresh_001',
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_400_BAD_REQUEST)
            
    except Exception as e:
        logger.exception("Token refresh error")
        return Response({
            'error': True,
            'code': 'INTERNAL_SERVER_ERROR',
            'message': 'Token refresh system error',
            'details': None,
            'error_id': 'refresh_002',
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    operation_id='logout_device',
    tags=['Authentication'],
    summary='Logout from specific device',
    description='''
    Logout from current device and invalidate all associated tokens and sessions.
    
    **Security Actions:**
    - Deactivate device token
    - End all biometric sessions
    - Log security event
    ''',
)
@api_view(['POST'])
@permission_classes([IsEmployeeOrAbove])
@authentication_classes([DeviceTokenAuthentication])
def logout_device(request):
    """
    Logout from current device
    """
    try:
        device_token = request.device_token
        
        # Deactivate device token
        device_token.is_active = False
        device_token.save()
        
        # End all biometric sessions for this device
        BiometricSession.objects.filter(
            device_token=device_token,
            is_active=True
        ).update(is_active=False)
        
        logger.info(f"Device logout successful: user={request.user.username}, "
                   f"device={device_token.device_id[:8]}...")
        
        return Response({
            'success': True,
            'message': 'Logout successful',
            'logged_out_at': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Logout error: {e}")
        return Response({
            'error': True,
            'code': 'INTERNAL_SERVER_ERROR',
            'message': 'Logout system error',
            'details': None,
            'error_id': 'logout_001',
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)