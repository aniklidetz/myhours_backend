import pytz

from django.contrib import admin

from .models import Holiday


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    """
    Admin configuration for Holiday model with proper timezone display.

    All DateTimeField values are stored in UTC but displayed in Israel timezone
    for better readability.
    """

    list_display = (
        "date",
        "name",
        "local_start_time",
        "local_end_time",
        "is_shabbat",
        "is_holiday",
        "is_special_shabbat",
    )
    list_filter = ("is_shabbat", "is_holiday", "is_special_shabbat", "date")
    search_fields = ("name",)
    ordering = ("-date",)
    date_hierarchy = "date"

    # Israel timezone for display
    ISRAEL_TZ = pytz.timezone("Asia/Jerusalem")

    def _convert_to_local(self, dt):
        """
        Convert UTC datetime to Israel timezone for display.

        Args:
            dt: Timezone-aware datetime (stored in UTC by Django)

        Returns:
            str: Formatted time string in Israel timezone, or "-" if None
        """
        if dt:
            local_dt = dt.astimezone(self.ISRAEL_TZ)
            return local_dt.strftime("%Y-%m-%d %H:%M")
        return "-"

    def local_start_time(self, obj):
        """Display start_time in Israel timezone."""
        return self._convert_to_local(obj.start_time)

    local_start_time.short_description = "Start (Israel)"
    local_start_time.admin_order_field = "start_time"

    def local_end_time(self, obj):
        """Display end_time in Israel timezone."""
        return self._convert_to_local(obj.end_time)

    local_end_time.short_description = "End (Israel)"
    local_end_time.admin_order_field = "end_time"

    # Make fields read-only in detail view to prevent accidental edits
    readonly_fields = ("local_start_time", "local_end_time")

    fieldsets = (
        (None, {"fields": ("date", "name")}),
        ("Type", {"fields": ("is_holiday", "is_shabbat", "is_special_shabbat")}),
        (
            "Times (Israel Timezone)",
            {
                "fields": ("local_start_time", "local_end_time"),
                "description": "Times are stored in UTC but displayed in Israel timezone (Asia/Jerusalem)",
            },
        ),
        (
            "Raw Times (UTC)",
            {
                "fields": ("start_time", "end_time"),
                "classes": ("collapse",),
                "description": "Raw UTC values as stored in database",
            },
        ),
    )
