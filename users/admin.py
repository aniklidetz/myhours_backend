from django.contrib import admin
from .models import Employee

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'employment_type', 'is_active')
    list_filter = ('employment_type', 'is_active')
    search_fields = ('first_name', 'last_name', 'email')