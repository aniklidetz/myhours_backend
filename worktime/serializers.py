from rest_framework import serializers
from django.utils import timezone
from .models import WorkLog
from users.serializers import EmployeeSerializer


class WorkLogSerializer(serializers.ModelSerializer):
    """WorkLog serializer with custom validation"""
    employee_name = serializers.ReadOnlyField(source='employee.get_full_name')
    total_hours = serializers.ReadOnlyField(source='get_total_hours')
    status = serializers.ReadOnlyField(source='get_status')
    duration = serializers.SerializerMethodField()

    class Meta:
        model = WorkLog
        fields = [
            'id', 'employee', 'employee_name', 'check_in', 'check_out',
            'location_check_in', 'location_check_out', 'notes', 'is_approved',
            'total_hours', 'status', 'duration', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_duration(self, obj):
        """Get formatted duration string"""
        if obj.check_out:
            duration = obj.get_duration()
            hours = int(duration.total_seconds() // 3600)
            minutes = int((duration.total_seconds() % 3600) // 60)
            return f"{hours}h {minutes}m"
        current_duration = timezone.now() - obj.check_in
        hours = int(current_duration.total_seconds() // 3600)
        minutes = int((current_duration.total_seconds() % 3600) // 60)
        return f"{hours}h {minutes}m (ongoing)"

    def validate_check_in(self, value):
        """Validate check-in time"""
        if value > timezone.now():
            raise serializers.ValidationError("Check-in time cannot be in the future")
        week_ago = timezone.now() - timezone.timedelta(days=7)
        if value < week_ago:
            raise serializers.ValidationError(
                "Check-in time cannot be more than 7 days in the past"
            )
        return value

    def validate_check_out(self, value):
        """Validate check-out time"""
        if value and value > timezone.now():
            raise serializers.ValidationError("Check-out time cannot be in the future")
        return value

    def validate(self, attrs):
        """Cross-field validation"""
        check_in = attrs.get('check_in')
        check_out = attrs.get('check_out')
        employee = attrs.get('employee')

        if self.instance:
            check_in = check_in or self.instance.check_in
            check_out = check_out or self.instance.check_out
            employee = employee or self.instance.employee

        if check_out and check_in and check_out <= check_in:
            raise serializers.ValidationError({
                'check_out': 'Check-out time must be after check-in time'
            })

        if check_out and check_in:
            duration = check_out - check_in
            if duration.total_seconds() > 16 * 3600:
                raise serializers.ValidationError({
                    'check_out': 'Work session cannot exceed 16 hours'
                })

        if employee and check_in:
            overlapping_query = WorkLog.objects.filter(
                employee=employee,
                check_in__lt=check_out or timezone.now(),
                check_out__gt=check_in
            )
            if self.instance:
                overlapping_query = overlapping_query.exclude(pk=self.instance.pk)
            if overlapping_query.exists():
                raise serializers.ValidationError(
                    "This work session overlaps with another work session"
                )
        return attrs