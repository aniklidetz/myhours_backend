# users/authentication.py
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from .token_models import DeviceToken, BiometricSession
import logging

logger = logging.getLogger(__name__)

class DeviceTokenAuthentication(BaseAuthentication):
    """
    Enhanced token authentication with device tracking and expiration
    """
    keyword = 'DeviceToken'
    model = DeviceToken

    def authenticate(self, request):
        auth = self.get_authorization_header(request).split()

        if not auth or auth[0].lower() != self.keyword.lower().encode():
            return None

        if len(auth) == 1:
            msg = 'Invalid token header. No credentials provided.'
            raise AuthenticationFailed(msg)
        elif len(auth) > 2:
            msg = 'Invalid token header. Token string should not contain spaces.'
            raise AuthenticationFailed(msg)

        try:
            token = auth[1].decode()
        except UnicodeError:
            msg = 'Invalid token header. Token string should not contain invalid characters.'
            raise AuthenticationFailed(msg)

        return self.authenticate_credentials(token, request)

    def authenticate_credentials(self, key, request):
        try:
            device_token = self.model.objects.select_related('user').get(
                token=key,
                is_active=True
            )
        except self.model.DoesNotExist:
            raise AuthenticationFailed('Invalid token.')

        if not device_token.is_valid():
            # Token is expired
            device_token.is_active = False
            device_token.save()
            raise AuthenticationFailed('Token expired.')

        if not device_token.user.is_active:
            raise AuthenticationFailed('User inactive or deleted.')

        # Update token usage tracking
        ip_address = self.get_client_ip(request)
        device_token.mark_used(ip_address=ip_address)
        
        # Attach device token to request for use in permissions
        request.device_token = device_token
        
        # Log authentication for security monitoring
        logger.info(f"Device token authentication successful: "
                   f"user={device_token.user.username}, "
                   f"device={device_token.device_id[:8]}..., "
                   f"ip={ip_address}")

        return (device_token.user, device_token)

    def get_authorization_header(self, request):
        """
        Return request's 'Authorization:' header, as a bytestring.
        """
        auth = request.META.get('HTTP_AUTHORIZATION', b'')
        if isinstance(auth, str):
            auth = auth.encode('iso-8859-1')
        return auth

    def get_client_ip(self, request):
        """Extract client IP from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def authenticate_header(self, request):
        return self.keyword


class BiometricSessionAuthentication(BaseAuthentication):
    """
    Authentication class that requires both device token and valid biometric session
    """
    
    def authenticate(self, request):
        # First, get device token authentication
        device_auth = DeviceTokenAuthentication()
        auth_result = device_auth.authenticate(request)
        
        if not auth_result:
            return None
        
        user, device_token = auth_result
        
        # Check for valid biometric session
        try:
            biometric_session = BiometricSession.objects.filter(
                device_token=device_token,
                is_active=True
            ).latest('started_at')
            
            if not biometric_session.is_valid():
                raise AuthenticationFailed('Biometric session expired. Please re-authenticate with biometrics.')
                
        except BiometricSession.DoesNotExist:
            raise AuthenticationFailed('Biometric verification required.')
        
        # Attach biometric session to request
        request.biometric_session = biometric_session
        
        logger.info("Biometric session authentication successful")
        
        return (user, {'device_token': device_token, 'biometric_session': biometric_session})


class HybridAuthentication(BaseAuthentication):
    """
    Hybrid authentication that supports both old token system and new device tokens
    for backward compatibility during migration
    """
    
    def authenticate(self, request):
        # Get authorization header
        auth = self.get_authorization_header(request).split()
        
        # Enhanced logging for debugging authentication issues
        auth_header = request.META.get('HTTP_AUTHORIZATION', 'MISSING')
        request_path = request.path
        query_params = dict(request.GET)
        
        # Log authentication attempt with context
        logger.debug(f"HybridAuth attempt: path={request_path}, params={query_params}, auth_header={auth_header[:50]}...")
        
        if not auth:
            logger.debug(f"HybridAuth: No authorization header for {request_path}")
            return None
            
        if len(auth) == 1:
            logger.warning(f"HybridAuth: Invalid auth header format (1 part) for {request_path}")
            return None
        elif len(auth) > 2:
            logger.warning(f"HybridAuth: Invalid auth header format (>2 parts) for {request_path}")
            return None
            
        try:
            auth_type = auth[0].decode().lower()
            token = auth[1].decode()
        except UnicodeError:
            logger.error(f"HybridAuth: Unicode decode error for {request_path}")
            return None
        
        # Try DeviceToken authentication first
        if auth_type == 'devicetoken':
            logger.debug(f"HybridAuth: Trying DeviceToken auth for {request_path}")
            device_auth = DeviceTokenAuthentication()
            try:
                result = device_auth.authenticate(request)
                if result:
                    logger.info(f"HybridAuth: DeviceToken success for {request_path} - user: {result[0].username}")
                    return result
                else:
                    logger.warning(f"HybridAuth: DeviceToken auth returned None for {request_path}")
            except AuthenticationFailed as e:
                logger.error(f"HybridAuth: DeviceToken auth failed for {request_path}: {e}")
                pass
        
        # Try legacy Token authentication
        elif auth_type == 'token':
            logger.debug(f"HybridAuth: Trying legacy Token auth for {request_path}")
            from rest_framework.authentication import TokenAuthentication
            old_auth = TokenAuthentication()
            try:
                result = old_auth.authenticate(request)
                if result:
                    # Mark this as legacy authentication
                    request.is_legacy_auth = True
                    logger.warning(f"Legacy token authentication used for user: {result[0].username} on {request_path}")
                    return result
                else:
                    logger.warning(f"HybridAuth: Legacy Token auth returned None for {request_path}")
            except AuthenticationFailed as e:
                logger.error(f"HybridAuth: Legacy Token auth failed for {request_path}: {e}")
                pass
        else:
            logger.warning(f"HybridAuth: Unknown auth type '{auth_type}' for {request_path}")
        
        logger.warning(f"HybridAuth: All authentication methods failed for {request_path}")
        return None

    def get_authorization_header(self, request):
        """
        Return request's 'Authorization:' header, as a bytestring.
        """
        auth = request.META.get('HTTP_AUTHORIZATION', b'')
        if isinstance(auth, str):
            auth = auth.encode('iso-8859-1')
        return auth

    def authenticate_header(self, request):
        return 'DeviceToken'


class SecurityMiddleware:
    """
    Enhanced security middleware for authentication monitoring and protection
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.failed_attempts = {}  # In production, use Redis
        self.max_attempts = 5
        self.lockout_duration = 900  # 15 minutes

    def __call__(self, request):
        # Pre-request security checks
        ip_address = self.get_client_ip(request)
        
        # Check for IP-based rate limiting
        if self.is_ip_locked_out(ip_address):
            from django.http import JsonResponse
            return JsonResponse({
                'error': True,
                'code': 'IP_LOCKED_OUT',
                'message': 'Too many failed authentication attempts. Please try again later.',
                'details': None,
                'error_id': 'security_001',
                'timestamp': timezone.now().isoformat()
            }, status=429)

        response = self.get_response(request)

        # Post-request security logging
        if hasattr(request, 'user') and request.user.is_authenticated:
            # Log successful authentication
            if hasattr(request, 'device_token'):
                self.log_successful_auth(request, ip_address)
        
        return response

    def get_client_ip(self, request):
        """Extract client IP from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def is_ip_locked_out(self, ip_address):
        """Check if IP is currently locked out"""
        if ip_address in self.failed_attempts:
            attempts, last_attempt = self.failed_attempts[ip_address]
            time_since_last = (timezone.now() - last_attempt).total_seconds()
            
            if attempts >= self.max_attempts and time_since_last < self.lockout_duration:
                return True
            elif time_since_last >= self.lockout_duration:
                # Reset counter after lockout period
                del self.failed_attempts[ip_address]
        
        return False

    def record_failed_attempt(self, ip_address):
        """Record a failed authentication attempt"""
        if ip_address in self.failed_attempts:
            attempts, _ = self.failed_attempts[ip_address]
            self.failed_attempts[ip_address] = (attempts + 1, timezone.now())
        else:
            self.failed_attempts[ip_address] = (1, timezone.now())
        
        logger.warning(f"Failed authentication attempt from IP: {ip_address}")

    def log_successful_auth(self, request, ip_address):
        """Log successful authentication for monitoring"""
        device_token = getattr(request, 'device_token', None)
        if device_token:
            logger.info(f"Successful authentication: "
                       f"user={request.user.username}, "
                       f"device={device_token.device_id[:8]}..., "
                       f"ip={ip_address}, "
                       f"biometric_verified={device_token.biometric_verified}")
            
            # Reset failed attempts on successful auth
            if ip_address in self.failed_attempts:
                del self.failed_attempts[ip_address]