from decimal import Decimal

from rest_framework import serializers

from django.conf import settings

from users.serializers import EmployeeSerializer

from .models import CompensatoryDay, Salary


class SalarySerializer(serializers.ModelSerializer):
    """Salary serializer with validation"""

    employee_name = serializers.ReadOnlyField(source="employee.get_full_name")
    calculated_salary = serializers.SerializerMethodField()

    class Meta:
        model = Salary
        fields = [
            "id",
            "employee",
            "employee_name",
            "base_salary",
            "hourly_rate",
            "calculation_type",
            "project_start_date",
            "project_end_date",
            "project_completed",
            "currency",
            "calculated_salary",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_calculated_salary(self, obj):
        """Get current month's calculated salary"""
        try:
            from django.utils import timezone

            now = timezone.now()
            return obj.calculate_monthly_salary(now.month, now.year)
        except Exception:
            return None

    def validate_base_salary(self, value):
        """Validate base salary"""
        if value < 0:
            raise serializers.ValidationError("Base salary cannot be negative")
        if value > 0 and value < Decimal("5300"):
            raise serializers.ValidationError(
                "Base salary cannot be less than minimum wage (5300 ILS)"
            )
        return value

    def validate_hourly_rate(self, value):
        """Validate hourly rate"""
        if value < 0:
            raise serializers.ValidationError("Hourly rate cannot be negative")
        min_hourly = Decimal("28.49")  # Current minimum wage in Israel
        if value > 0 and value < min_hourly:
            raise serializers.ValidationError(
                f"Hourly rate cannot be less than minimum wage ({min_hourly} ILS/hour)"
            )
        return value

    def validate_calculation_type(self, value):
        """Validate calculation type against feature flags"""
        if value == "project" and not settings.FEATURE_FLAGS.get(
            "ENABLE_PROJECT_PAYROLL", False
        ):
            raise serializers.ValidationError(
                "Project payroll calculation is currently disabled. "
                "Contact administrator to enable this feature."
            )
        return value

    def validate(self, attrs):
        """Cross-field validation"""
        calculation_type = attrs.get("calculation_type")
        project_start_date = attrs.get("project_start_date")
        project_end_date = attrs.get("project_end_date")
        
        # Handle monthly_hourly field - convert 0 to None for consistency
        monthly_hourly = attrs.get("monthly_hourly", None)
        if monthly_hourly is not None and Decimal(str(monthly_hourly)) == 0:
            attrs["monthly_hourly"] = None

        # Check if project payroll is enabled
        if calculation_type == "project":
            if not settings.FEATURE_FLAGS.get("ENABLE_PROJECT_PAYROLL", False):
                raise serializers.ValidationError(
                    {
                        "calculation_type": "Project payroll calculation is currently disabled. "
                        "Contact administrator to enable this feature."
                    }
                )

            if not project_start_date or not project_end_date:
                raise serializers.ValidationError(
                    "Project start and end dates are required for project-based calculation"
                )
            if project_start_date >= project_end_date:
                raise serializers.ValidationError(
                    {"project_end_date": "Project end date must be after start date"}
                )
        return attrs


class CompensatoryDaySerializer(serializers.ModelSerializer):
    """Compensatory day serializer"""

    employee_name = serializers.ReadOnlyField(source="employee.get_full_name")
    is_used = serializers.SerializerMethodField()

    class Meta:
        model = CompensatoryDay
        fields = [
            "id",
            "employee",
            "employee_name",
            "date_earned",
            "reason",
            "date_used",
            "is_used",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_is_used(self, obj):
        """Check if compensatory day has been used"""
        return obj.date_used is not None

    def validate_date_used(self, value):
        """Validate date_used"""
        if value:
            from django.utils import timezone

            # Use localdate() for consistent timezone handling
            today = timezone.localdate()
            if value > today:
                raise serializers.ValidationError("Used date cannot be in the future")
        return value
