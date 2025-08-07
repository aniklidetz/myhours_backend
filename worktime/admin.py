from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import WorkLog


@admin.register(WorkLog)
class WorkLogAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "check_in",
        "check_out",
        "get_total_hours",
        "get_status",
        "soft_delete_info",
    )
    list_filter = ("check_in", "check_out", "employee", "is_deleted", "is_approved")
    date_hierarchy = "check_in"
    search_fields = ("employee__first_name", "employee__last_name", "notes")

    # Show all records including soft deleted by default
    def get_queryset(self, request):
        return WorkLog.all_objects.get_queryset()

    def soft_delete_info(self, obj):
        """Display soft delete information"""
        if obj.is_deleted:
            return format_html(
                '<span style="color: red;">Deleted: {}</span>',
                (
                    obj.deleted_at.strftime("%Y-%m-%d %H:%M")
                    if obj.deleted_at
                    else "Unknown"
                ),
            )
        return format_html('<span style="color: green;">Active</span>')

    soft_delete_info.short_description = "Status"

    actions = ["soft_delete_selected", "restore_selected"]

    def soft_delete_selected(self, request, queryset):
        """Soft delete selected WorkLog records"""
        count = 0
        for obj in queryset.filter(is_deleted=False):
            obj.soft_delete(
                deleted_by=(
                    request.user.employee_profile
                    if hasattr(request.user, "employee_profile")
                    else None
                )
            )
            count += 1
        self.message_user(request, f"{count} records soft deleted.")

    soft_delete_selected.short_description = "Soft delete selected records"

    def restore_selected(self, request, queryset):
        """Restore soft deleted WorkLog records"""
        count = 0
        for obj in queryset.filter(is_deleted=True):
            obj.restore()
            count += 1
        self.message_user(request, f"{count} records restored.")

    restore_selected.short_description = "Restore selected records"

    # Prevent hard delete in admin
    def has_delete_permission(self, request, obj=None):
        return False  # Disable hard delete, use soft delete instead
