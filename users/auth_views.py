# users/auth_views.py
import logging

from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from django.contrib.auth import authenticate
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


# Schema serializers for API documentation
class LoginRequest(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class UserInfo(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    username = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    is_staff = serializers.BooleanField()
    is_superuser = serializers.BooleanField()
    role = serializers.CharField()


class TokenResponse(serializers.Serializer):
    token = serializers.CharField()
    user = UserInfo()


class TestConnectionResponse(serializers.Serializer):
    status = serializers.CharField()
    message = serializers.CharField()
    method = serializers.CharField()
    headers = serializers.DictField()


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    """
    Login endpoint that returns a token for authentication
    """
    email = request.data.get("email")
    password = request.data.get("password")

    # Log the attempt (without email for security)
    logger.info("Login attempt received")

    # Validate input
    if not email or not password:
        logger.warning(f"Login failed - missing credentials")
        return Response(
            {"error": "Email and password are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Try to authenticate using username (since Django uses username by default)
    # First, try to find user by email
    try:
        user = User.objects.get(email=email)
        username = user.username
    except User.DoesNotExist:
        # If email doesn't exist, try using email as username
        username = email

    # Authenticate user
    user = authenticate(username=username, password=password)

    if user:
        # Create or get token
        token, created = Token.objects.get_or_create(user=user)

        # Get role from Employee model if exists
        role = "employee"  # default role
        try:
            from users.models import Employee

            employee = Employee.objects.get(user=user)
            role = employee.role
        except Employee.DoesNotExist:
            # If no employee profile, determine role from user permissions
            if user.is_superuser:
                role = "admin"
            elif user.is_staff:
                role = "accountant"

        # Prepare user data
        user_data = {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
            "role": role,
        }

        logger.info(f"Login successful for user ID: {user.id}")

        return Response({"token": token.key, "user": user_data})
    else:
        logger.warning("Login failed - invalid credentials")
        return Response(
            {"error": "Invalid email or password"}, status=status.HTTP_401_UNAUTHORIZED
        )


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def test_connection(request):
    """
    Test endpoint to check if API is accessible
    """
    return Response(
        {
            "status": "ok",
            "message": "API is connected successfully!",
            "method": request.method,
            "headers": dict(request.headers),
        }
    )


@api_view(["POST"])
def logout_view(request):
    """
    Logout endpoint that deletes the token
    """
    try:
        # Delete the user's token
        request.user.auth_token.delete()
        logger.info(f"Logout successful for user: {request.user.username}")
        return Response({"message": "Logged out successfully"})
    except:
        return Response({"message": "Logout completed"})


# Note: OpenAPI decorators removed for stability - can be re-added when drf_spectacular is enabled
