from django.contrib import admin
from django import forms
from users.models import Employee
from worktime.models import WorkLog
from payroll.models import Salary


# 📌 Добавляем Employee обратно в админку
@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'employment_type', 'is_active')
    list_filter = ('employment_type', 'is_active')


# 📌 Добавляем WorkLog обратно в админку
@admin.register(WorkLog)
class WorkLogAdmin(admin.ModelAdmin):
    list_display = ('employee', 'check_in', 'check_out')
    list_filter = ('check_in', 'check_out')


# 📌 Создаём форму для Salary, чтобы отображался employment_type
class SalaryAdminForm(forms.ModelForm):
    """Форма для админки Salary, чтобы показать employment_type."""
    
    employment_type = forms.ChoiceField(
        choices=Employee.EMPLOYMENT_TYPES,  # Используем те же опции, что и в модели Employee
        required=False,
        label="Employment Type"
    )

    class Meta:
        model = Salary
        fields = '__all__'  # Все стандартные поля

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:  # Если зарплата уже создана
            self.fields['employment_type'].initial = self.instance.employee.employment_type

    def save(self, commit=True):
        """Сохраняем employment_type в Employee"""
        instance = super().save(commit=False)
        instance.employee.employment_type = self.cleaned_data['employment_type']
        instance.employee.save()
        if commit:
            instance.save()
        return instance


# 📌 Регистрируем Salary с новой формой
@admin.register(Salary)
class SalaryAdmin(admin.ModelAdmin):
    form = SalaryAdminForm  # Используем новую форму
    list_display = ('employee', 'get_employment_type', 'base_salary', 'hourly_rate', 'calculated_salary', 'currency', 'updated_at')
    list_filter = ('employee__employment_type', 'currency')

    def get_employment_type(self, obj):
        return obj.employee.employment_type
    get_employment_type.short_description = "Employment Type"  # Название в админке
    get_employment_type.admin_order_field = "employee__employment_type"  # Позволяет сортировать