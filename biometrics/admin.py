# biometrics/admin.py
from django.contrib import admin
from django.utils.html import format_html
from .models import BiometricProfile, BiometricLog, BiometricAttempt, FaceQualityCheck


@admin.register(BiometricProfile)
class BiometricProfileAdmin(admin.ModelAdmin):
    list_display = ['employee_name', 'embeddings_count', 'is_active', 'last_updated', 'created_at']
    list_filter = ['is_active', 'created_at', 'last_updated']
    search_fields = ['employee__first_name', 'employee__last_name', 'employee__email']
    readonly_fields = ['mongodb_id', 'created_at', 'last_updated']
    
    def employee_name(self, obj):
        return obj.employee.get_full_name()
    employee_name.short_description = 'Employee'
    employee_name.admin_order_field = 'employee__last_name'
    
    actions = ['deactivate_profiles', 'activate_profiles']
    
    def deactivate_profiles(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} profiles deactivated.')
    deactivate_profiles.short_description = 'Deactivate selected profiles'
    
    def activate_profiles(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} profiles activated.')
    activate_profiles.short_description = 'Activate selected profiles'


@admin.register(BiometricLog)
class BiometricLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'action', 'employee_name', 'success', 'confidence_display', 
                   'location', 'processing_time_display', 'ip_address']
    list_filter = ['action', 'success', 'created_at']
    search_fields = ['employee__first_name', 'employee__last_name', 'employee__email', 
                     'ip_address', 'location']
    readonly_fields = ['id', 'created_at', 'device_info']
    date_hierarchy = 'created_at'
    
    def employee_name(self, obj):
        if obj.employee:
            return obj.employee.get_full_name()
        return '-'
    employee_name.short_description = 'Employee'
    
    def confidence_display(self, obj):
        if obj.confidence_score:
            score = obj.confidence_score * 100
            if score >= 80:
                color = 'green'
            elif score >= 60:
                color = 'orange'
            else:
                color = 'red'
            return format_html(
                '<span style="color: {};">{:.1f}%</span>',
                color,
                score
            )
        return '-'
    confidence_display.short_description = 'Confidence'
    
    def processing_time_display(self, obj):
        if obj.processing_time_ms:
            return f'{obj.processing_time_ms} ms'
        return '-'
    processing_time_display.short_description = 'Processing Time'
    
    def has_add_permission(self, request):
        return False  # Logs should not be manually added


@admin.register(BiometricAttempt)
class BiometricAttemptAdmin(admin.ModelAdmin):
    list_display = ['ip_address', 'attempts_count', 'last_attempt', 'is_blocked_display', 'blocked_until']
    list_filter = ['last_attempt']
    search_fields = ['ip_address']
    readonly_fields = ['last_attempt']
    
    def is_blocked_display(self, obj):
        if obj.is_blocked():
            return format_html('<span style="color: red;">Blocked</span>')
        return format_html('<span style="color: green;">Active</span>')
    is_blocked_display.short_description = 'Status'
    
    actions = ['reset_attempts']
    
    def reset_attempts(self, request, queryset):
        for attempt in queryset:
            attempt.reset_attempts()
        self.message_user(request, f'{queryset.count()} attempts reset.')
    reset_attempts.short_description = 'Reset selected attempts'


@admin.register(FaceQualityCheck)
class FaceQualityCheckAdmin(admin.ModelAdmin):
    list_display = ['biometric_log', 'face_detected', 'face_count', 'brightness_display', 
                   'blur_display', 'eye_visibility', 'created_at']
    list_filter = ['face_detected', 'eye_visibility', 'created_at']
    readonly_fields = ['biometric_log', 'created_at']
    
    def brightness_display(self, obj):
        if obj.brightness_score is not None:
            if obj.brightness_score < 50:
                color = 'red'
                status = 'Too Dark'
            elif obj.brightness_score > 200:
                color = 'red'
                status = 'Too Bright'
            else:
                color = 'green'
                status = 'Good'
            return format_html(
                '<span style="color: {};">{:.1f} ({})</span>',
                color,
                obj.brightness_score,
                status
            )
        return '-'
    brightness_display.short_description = 'Brightness'
    
    def blur_display(self, obj):
        if obj.blur_score is not None:
            if obj.blur_score < 100:
                color = 'red'
                status = 'Blurry'
            else:
                color = 'green'
                status = 'Sharp'
            return format_html(
                '<span style="color: {};">{:.1f} ({})</span>',
                color,
                obj.blur_score,
                status
            )
        return '-'
    blur_display.short_description = 'Blur Score'
    
    def has_add_permission(self, request):
        return False  # Quality checks should not be manually added