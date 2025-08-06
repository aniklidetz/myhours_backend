from django.contrib import admin
from django.conf import settings
from .models import Salary, CompensatoryDay, DailyPayrollCalculation, MonthlyPayrollSummary
from django import forms
from users.models import Employee

class SalaryAdminForm(forms.ModelForm):
    """Form for Salary admin to show employment_type"""
    
    class Meta:
        model = Salary
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Hide project calculation type if feature flag is disabled
        if not settings.FEATURE_FLAGS.get("ENABLE_PROJECT_PAYROLL", False):
            calculation_choices = [
                choice for choice in self.fields['calculation_type'].choices 
                if choice[0] != 'project'
            ]
            self.fields['calculation_type'].choices = calculation_choices
            
            # If editing existing project salary, show warning but keep current value
            if (self.instance and self.instance.pk and 
                self.instance.calculation_type == 'project'):
                self.fields['calculation_type'].help_text = (
                    "⚠️ Project payroll is disabled. This record is in legacy mode. "
                    "Contact administrator to enable project payroll feature."
                )
                self.fields['calculation_type'].disabled = True
        
        if self.instance and self.instance.pk:
            # Disable modification of calculation_type if the record already exists
            if not (self.instance.calculation_type == 'project' and 
                   not settings.FEATURE_FLAGS.get("ENABLE_PROJECT_PAYROLL", False)):
                self.fields['calculation_type'].disabled = True
                # Add informative message
                self.fields['calculation_type'].help_text = (
                    "To change calculation type, update the employment type in employee profile"
                )

@admin.register(Salary)
class SalaryAdmin(admin.ModelAdmin):
    form = SalaryAdminForm
    list_display = ('employee', 'calculation_type', 'base_salary', 'hourly_rate', 'currency', 'updated_at')
    list_filter = ('calculation_type', 'currency', 'created_at')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__email')
    readonly_fields = ('created_at', 'updated_at')
    
    def get_fieldsets(self, request, obj=None):
        """Dynamically adjust fieldsets based on feature flags"""
        main_fieldset = ('Main Information', {
            'fields': [
                'employee', 'calculation_type', 'currency',
                ('base_salary', 'hourly_rate'),
                ('created_at', 'updated_at')
            ]
        })
        
        # Only show project fieldset if feature is enabled OR editing existing project salary
        if (settings.FEATURE_FLAGS.get("ENABLE_PROJECT_PAYROLL", False) or 
            (obj and obj.calculation_type == 'project')):
            project_fieldset = ('Project-Based Payment', {
                'fields': [
                    ('project_start_date', 'project_end_date'),
                    'project_completed'
                ],
                'classes': ['collapse'],
            })
            return [main_fieldset, project_fieldset]
        
        return [main_fieldset]

@admin.register(CompensatoryDay)
class CompensatoryDayAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date_earned', 'reason', 'date_used', 'status')
    list_filter = ('reason', 'date_earned', 'date_used')
    search_fields = ('employee__first_name', 'employee__last_name')
    
    def status(self, obj):
        return "Used" if obj.date_used else "Not used"
    status.short_description = "Status"


@admin.register(DailyPayrollCalculation)
class DailyPayrollCalculationAdmin(admin.ModelAdmin):
    list_display = ('employee', 'work_date', 'base_pay', 'bonus_pay', 'total_gross_pay', 'regular_hours', 'overtime_hours_1', 'overtime_hours_2', 'sabbath_regular_hours', 'sabbath_overtime_hours_1', 'sabbath_overtime_hours_2', 'is_holiday', 'is_sabbath')
    list_filter = ('work_date', 'is_holiday', 'is_sabbath', 'is_night_shift', 'calculated_by_service')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__email')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'work_date'
    
    fieldsets = (
        ('Employee & Date', {
            'fields': ('employee', 'work_date')
        }),
        ('Hours Breakdown', {
            'fields': (
                ('regular_hours', 'overtime_hours_1', 'overtime_hours_2'),
                ('sabbath_regular_hours', 'sabbath_overtime_hours_1', 'sabbath_overtime_hours_2'),
                'night_hours'
            )
        }),
        ('New Unified Payment Structure', {
            'fields': (
                ('base_pay', 'bonus_pay'),
                'total_gross_pay'
            )
        }),
        ('Legacy Pay Breakdown', {
            'fields': (
                ('regular_pay', 'overtime_pay_1', 'overtime_pay_2'),
                ('sabbath_overtime_pay_1', 'sabbath_overtime_pay_2'),
                'total_pay'
            ),
            'classes': ('collapse',)
        }),
        ('Special Conditions', {
            'fields': (
                ('is_holiday', 'is_sabbath', 'is_night_shift'),
                'holiday_name'
            )
        }),
        ('System Information', {
            'fields': (
                'calculated_by_service',
                'calculation_details',
                ('created_at', 'updated_at')
            ),
            'classes': ('collapse',)
        })
    )


@admin.register(MonthlyPayrollSummary)
class MonthlyPayrollSummaryAdmin(admin.ModelAdmin):
    list_display = ('employee', 'year', 'month', 'total_gross_pay', 'total_hours', 'worked_days', 'compensatory_days_earned')
    list_filter = ('year', 'month', 'calculation_date')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__email')
    readonly_fields = ('calculation_date', 'last_updated')
    
    fieldsets = (
        ('Employee & Period', {
            'fields': ('employee', ('year', 'month'))
        }),
        ('Hours Summary', {
            'fields': (
                'total_hours',
                ('regular_hours', 'overtime_hours'),
                ('holiday_hours', 'sabbath_hours')
            )
        }),
        ('Pay Summary', {
            'fields': (
                'total_gross_pay',
                ('base_pay', 'overtime_pay'),
                ('holiday_pay', 'sabbath_pay')
            )
        }),
        ('Work Statistics', {
            'fields': (
                ('worked_days', 'compensatory_days_earned')
            )
        }),
        ('System Information', {
            'fields': (
                'calculation_details',
                ('calculation_date', 'last_updated')
            ),
            'classes': ('collapse',)
        })
    )