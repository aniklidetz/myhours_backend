from django.contrib import admin
from .models import WorkLog

@admin.register(WorkLog)
class WorkLogAdmin(admin.ModelAdmin):
    list_display = ('employee', 'check_in', 'check_out', 'get_total_hours')
    list_filter = ('check_in', 'check_out', 'employee')
    date_hierarchy = 'check_in'