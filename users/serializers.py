from rest_framework import serializers
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from .models import Employee, EmployeeInvitation


class EmployeeSerializer(serializers.ModelSerializer):
    """Employee serializer with custom validation and N+1 query optimization"""
    full_name = serializers.ReadOnlyField(source='get_full_name')
    display_name = serializers.ReadOnlyField(source='get_display_name')
    is_registered = serializers.ReadOnlyField()
    has_biometric = serializers.SerializerMethodField()  # Optimized with prefetch_related
    has_pending_invitation = serializers.SerializerMethodField()  # Optimized with prefetch_related
    
    # Salary information from related Salary model - optimized with prefetch_related
    # Allow these to be written during creation but they will be ignored
    hourly_rate = serializers.SerializerMethodField()
    monthly_salary = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            'id', 'first_name', 'last_name', 'email', 'phone',
            'employment_type', 'hourly_rate', 'monthly_salary', 'role', 'is_active', 
            'created_at', 'updated_at', 'full_name', 'display_name',
            'is_registered', 'has_biometric', 'has_pending_invitation'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_registered', 'has_biometric']
    
    def get_has_biometric(self, obj):
        """Check if employee has biometric profile - optimized for prefetch_related"""
        try:
            # Check if biometric_profile is prefetched and available
            if hasattr(obj, '_prefetched_objects_cache') and 'biometric_profile' in obj._prefetched_objects_cache:
                # Get prefetched biometric_profile 
                biometric_profile = getattr(obj, 'biometric_profile', None)
                return biometric_profile is not None
            
            # Alternative: check if biometric_profile exists without additional query
            if hasattr(obj, 'biometric_profile'):
                try:
                    # This will not trigger a query if prefetched, but will if not
                    return obj.biometric_profile is not None
                except obj.biometric_profile.RelatedObjectDoesNotExist:
                    return False
            
            # Use the property method as fallback (this might trigger N+1)
            return obj.has_biometric
        except:
            return False
    
    def get_hourly_rate(self, obj):
        """Get hourly rate from related Salary model - optimized for prefetch_related"""
        try:
            # Use prefetched salary_info if available
            if hasattr(obj, '_prefetched_objects_cache') and 'salary_info' in obj._prefetched_objects_cache:
                salary_info = getattr(obj, 'salary_info', None)
                return float(salary_info.hourly_rate) if salary_info and salary_info.hourly_rate else None
            # Fallback to property
            if hasattr(obj, 'salary_info') and obj.salary_info:
                return float(obj.salary_info.hourly_rate) if obj.salary_info.hourly_rate else None
            return None
        except:
            return None
    
    def get_monthly_salary(self, obj):
        """Get monthly salary from related Salary model - optimized for prefetch_related"""
        try:
            # Use prefetched salary_info if available
            if hasattr(obj, '_prefetched_objects_cache') and 'salary_info' in obj._prefetched_objects_cache:
                salary_info = getattr(obj, 'salary_info', None)
                return float(salary_info.base_salary) if salary_info and salary_info.base_salary else None
            # Fallback to property
            if hasattr(obj, 'salary_info') and obj.salary_info:
                return float(obj.salary_info.base_salary) if obj.salary_info.base_salary else None
            return None
        except:
            return None

    def get_has_pending_invitation(self, obj):
        """Check if employee has pending invitation - optimized for prefetch_related"""
        try:
            # Use prefetched invitation if available
            if hasattr(obj, '_prefetched_objects_cache') and 'invitation' in obj._prefetched_objects_cache:
                invitation = getattr(obj, 'invitation', None)
                return invitation is not None and invitation.is_valid
            # Fallback to property
            return hasattr(obj, 'invitation') and obj.invitation.is_valid
        except:
            return False

    def validate_email(self, value):
        """Custom email validation"""
        if value:
            if self.instance:
                if Employee.objects.exclude(pk=self.instance.pk).filter(email=value).exists():
                    raise serializers.ValidationError("Employee with this email already exists.")
            else:
                if Employee.objects.filter(email=value).exists():
                    raise serializers.ValidationError("Employee with this email already exists.")
        return value

    def validate_phone(self, value):
        """Custom phone validation"""
        if value:
            import re
            clean_phone = value.replace(' ', '').replace('-', '')
            phone_pattern = r'^\+\d{1,3}\d{8,15}$'
            if not re.match(phone_pattern, clean_phone):
                raise serializers.ValidationError(
                    "Phone number must be in international format (e.g., +972501234567)"
                )
        return value

    def validate(self, attrs):
        """Cross-field validation"""
        if attrs.get('first_name') == attrs.get('last_name'):
            raise serializers.ValidationError(
                "First name and last name cannot be identical"
            )
        return attrs


class EmployeeInvitationSerializer(serializers.ModelSerializer):
    """Serializer for employee invitations"""
    employee_name = serializers.CharField(source='employee.get_full_name', read_only=True)
    employee_email = serializers.CharField(source='employee.email', read_only=True)
    invited_by_name = serializers.CharField(source='invited_by.get_full_name', read_only=True)
    
    class Meta:
        model = EmployeeInvitation
        fields = [
            'id', 'employee', 'employee_name', 'employee_email',
            'token', 'invited_by', 'invited_by_name',
            'created_at', 'expires_at', 'accepted_at',
            'email_sent', 'email_sent_at',
            'is_valid', 'is_accepted', 'is_expired'
        ]
        read_only_fields = [
            'id', 'token', 'created_at', 'expires_at', 
            'accepted_at', 'is_valid', 'is_accepted', 'is_expired'
        ]


class SendInvitationSerializer(serializers.Serializer):
    """Serializer for sending invitations to employees"""
    employee_id = serializers.IntegerField()
    base_url = serializers.URLField(required=False, default='http://localhost:8100')
    
    def validate_employee_id(self, value):
        try:
            employee = Employee.objects.get(id=value)
            if employee.is_registered:
                raise serializers.ValidationError("Employee already has an account")
            if hasattr(employee, 'invitation') and employee.invitation.is_valid:
                raise serializers.ValidationError("Employee already has a pending invitation")
        except Employee.DoesNotExist:
            raise serializers.ValidationError("Employee not found")
        return value


class AcceptInvitationSerializer(serializers.Serializer):
    """Serializer for accepting invitation and creating user account"""
    token = serializers.CharField(max_length=64)
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)
    
    def validate_token(self, value):
        try:
            invitation = EmployeeInvitation.objects.get(token=value)
            if not invitation.is_valid:
                if invitation.is_accepted:
                    raise serializers.ValidationError("This invitation has already been accepted")
                elif invitation.is_expired:
                    raise serializers.ValidationError("This invitation has expired")
                else:
                    raise serializers.ValidationError("Invalid invitation")
        except EmployeeInvitation.DoesNotExist:
            raise serializers.ValidationError("Invalid invitation token")
        return value
    
    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken")
        return value
    
    def validate(self, attrs):
        if attrs.get('password') != attrs.get('confirm_password'):
            raise serializers.ValidationError({"confirm_password": "Passwords do not match"})
        return attrs