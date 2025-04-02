from django.contrib import admin
from .models import Salary, CompensatoryDay
from django import forms
from users.models import Employee

class SalaryAdminForm(forms.ModelForm):
    """Form for Salary admin to show employment_type"""
    
    class Meta:
        model = Salary
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Disable modification of calculation_type if the record already exists
            self.fields['calculation_type'].disabled = True
            # Add informative message
            self.fields['calculation_type'].help_text = (
                "To change calculation type, update the employment type in employee profile"
            )

@admin.register(Salary)
class SalaryAdmin(admin.ModelAdmin):
    list_display = ('employee', 'calculation_type', 'base_salary', 'hourly_rate', 'currency', 'updated_at')
    list_filter = ('calculation_type', 'currency', 'created_at')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__email')
    # Removing inlines since there is no relation between Salary and CompensatoryDay
    # inlines = [CompensatoryDayInline]
    
    fieldsets = [
        ('Main Information', {
            'fields': [
                'employee', 'calculation_type', 'currency',
                ('base_salary', 'hourly_rate'),
                ('created_at', 'updated_at')
            ]
        }),
        ('Project-Based Payment', {
            'fields': [
                ('project_start_date', 'project_end_date'),
                'project_completed'
            ],
            'classes': ['collapse'],
        })
    ]
    
    readonly_fields = ('created_at', 'updated_at')

@admin.register(CompensatoryDay)
class CompensatoryDayAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date_earned', 'reason', 'date_used', 'status')
    list_filter = ('reason', 'date_earned', 'date_used')
    search_fields = ('employee__first_name', 'employee__last_name')
    
    def status(self, obj):
        return "Used" if obj.date_used else "Not used"
    status.short_description = "Status"