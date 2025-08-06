from django.contrib import admin
from django.utils.html import format_html
from .models import Employee, EmployeeInvitation


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "first_name",
        "last_name",
        "email",
        "employment_type",
        "is_active",
        "is_registered",
        "has_invitation",
    )
    list_filter = ("employment_type", "is_active", "role")
    search_fields = ("first_name", "last_name", "email")
    readonly_fields = ("created_at", "updated_at")

    def is_registered(self, obj):
        return obj.is_registered

    is_registered.boolean = True
    is_registered.short_description = "Registered"

    def has_invitation(self, obj):
        try:
            if hasattr(obj, "invitation"):
                if obj.invitation.is_valid:
                    return format_html('<span style="color: orange;">Pending</span>')
                elif obj.invitation.is_accepted:
                    return format_html('<span style="color: green;">Accepted</span>')
                else:
                    return format_html('<span style="color: red;">Expired</span>')
        except:
            pass
        return "-"

    has_invitation.short_description = "Invitation"


@admin.register(EmployeeInvitation)
class EmployeeInvitationAdmin(admin.ModelAdmin):
    list_display = (
        "employee_email",
        "status",
        "invited_by",
        "created_at",
        "expires_at",
        "email_sent",
    )
    list_filter = ("email_sent", "accepted_at")
    search_fields = ("employee__email", "employee__first_name", "employee__last_name")
    readonly_fields = ("token", "created_at", "accepted_at", "email_sent_at")

    def employee_email(self, obj):
        return obj.employee.email

    employee_email.short_description = "Employee"

    def status(self, obj):
        if obj.is_accepted:
            return format_html('<span style="color: green;">✓ Accepted</span>')
        elif obj.is_valid:
            return format_html('<span style="color: orange;">⏳ Pending</span>')
        else:
            return format_html('<span style="color: red;">✗ Expired</span>')

    status.short_description = "Status"
