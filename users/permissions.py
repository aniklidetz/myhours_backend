# users/permissions.py
from datetime import timedelta

from rest_framework.permissions import BasePermission

from django.utils import timezone


class IsEmployeeOrAbove(BasePermission):
    """
    Permission for employee role and above
    """

    message = "Employee access required"

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.employees.exists()
            and request.user.employees.first().role
            in ["employee", "accountant", "admin"]
        )


class IsAccountantOrAdmin(BasePermission):
    """
    Permission for accountant and admin roles only
    """

    message = "Accountant or Admin access required"

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.employees.exists()
            and request.user.employees.first().role in ["accountant", "admin"]
        )


class IsAdminOnly(BasePermission):
    """
    Permission for admin role only
    """

    message = "Admin access required"

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.employees.exists()
            and request.user.employees.first().role == "admin"
        )


class IsSelfOrAbove(BasePermission):
    """
    Permission to access own data or higher role access
    """

    message = "Access denied: can only access own data or need higher privileges"

    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Admin can access everything
        if (
            request.user.employees.exists()
            and request.user.employees.first().role == "admin"
        ):
            return True

        # Accountant can access employee data
        if (
            request.user.employees.exists()
            and request.user.employees.first().role == "accountant"
            and hasattr(obj, "role")
            and obj.role == "employee"
        ):
            return True

        # Users can access their own data
        if hasattr(obj, "user"):
            return obj.user == request.user
        elif hasattr(obj, "employee"):
            return obj.employee.user == request.user

        return False


class BiometricVerificationRequired(BasePermission):
    """
    Permission that requires recent biometric verification for sensitive operations
    """

    message = "Biometric verification required for this operation"

    def __init__(self, max_age_hours=1):
        self.max_age_hours = max_age_hours

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        # Check if user has a valid biometric session
        device_token = getattr(request, "device_token", None)
        if not device_token:
            return False

        # Check if biometric verification is recent enough
        if device_token.biometric_verified_at:
            time_since_verification = (
                timezone.now() - device_token.biometric_verified_at
            )
            return time_since_verification <= timedelta(hours=self.max_age_hours)

        return False


class WorkTimeOperationPermission(BasePermission):
    """
    Special permission for work time operations (check-in/out)
    Checks if time tracking operations require biometric verification based on settings
    """

    message = "Biometric verification required for time tracking operations"

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        # Check if time tracking requires biometric verification in settings
        from django.conf import settings

        required_operations = getattr(
            settings, "BIOMETRIC_VERIFICATION_REQUIRED_FOR", []
        )

        # If time_tracking is not in the required list, allow access
        if "time_tracking" not in required_operations:
            return True

        # If time_tracking IS required, check biometric verification
        # Admin users can bypass biometric for emergency operations
        if (
            request.user.employees.exists()
            and request.user.employees.first().role == "admin"
            and request.META.get("HTTP_X_ADMIN_OVERRIDE") == "true"
        ):
            return True

        # Regular users must have valid biometric session
        device_token = getattr(request, "device_token", None)
        if device_token and device_token.biometric_verified:
            # Check if biometric session is recent (within 8 hours)
            if device_token.biometric_verified_at:
                time_since_verification = (
                    timezone.now() - device_token.biometric_verified_at
                )
                return time_since_verification <= timedelta(hours=8)

        return False


class LocationBasedPermission(BasePermission):
    """
    Permission that checks if user is in allowed location
    """

    message = "Operation not allowed from current location"

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        # Get location from request
        location_data = (
            request.data.get("location") if hasattr(request, "data") else None
        )
        if not location_data:
            # Allow if no location data (for non-location-sensitive operations)
            return True

        # TODO: Implement location validation logic
        # For now, allow all locations
        return True


class PayrollAccessPermission(BasePermission):
    """
    Special permission for payroll operations
    Requires accountant/admin role + recent biometric verification
    """

    message = "Payroll access requires accountant privileges and biometric verification"

    def has_permission(self, request, view):
        # Must be accountant or admin
        if not (
            request.user.is_authenticated
            and request.user.employees.exists()
            and request.user.employees.first().role in ["accountant", "admin"]
        ):
            return False

        # Must have recent biometric verification (within 30 minutes for payroll)
        device_token = getattr(request, "device_token", None)
        if device_token and device_token.biometric_verified_at:
            time_since_verification = (
                timezone.now() - device_token.biometric_verified_at
            )
            return time_since_verification <= timedelta(minutes=30)

        return False


# Convenience permission combinations
class EmployeeWithBiometric(BasePermission):
    """Employee role + biometric verification"""

    def has_permission(self, request, view):
        employee_check = IsEmployeeOrAbove().has_permission(request, view)
        biometric_check = BiometricVerificationRequired(max_age_hours=8).has_permission(
            request, view
        )
        return employee_check and biometric_check


class AccountantWithBiometric(BasePermission):
    """Accountant role + biometric verification"""

    def has_permission(self, request, view):
        accountant_check = IsAccountantOrAdmin().has_permission(request, view)
        biometric_check = BiometricVerificationRequired(max_age_hours=1).has_permission(
            request, view
        )
        return accountant_check and biometric_check
