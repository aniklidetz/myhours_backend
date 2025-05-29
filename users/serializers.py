from rest_framework import serializers
from django.core.exceptions import ValidationError
from .models import Employee


class EmployeeSerializer(serializers.ModelSerializer):
    """Employee serializer with custom validation"""
    full_name = serializers.ReadOnlyField(source='get_full_name')
    display_name = serializers.ReadOnlyField(source='get_display_name')

    class Meta:
        model = Employee
        fields = [
            'id', 'first_name', 'last_name', 'email', 'phone',
            'employment_type', 'is_active', 'created_at', 'updated_at',
            'full_name', 'display_name'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

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