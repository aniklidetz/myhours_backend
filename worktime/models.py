import sys
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from users.models import Employee


def _round6(val):
    """Round decimal to 6 decimal places for geolocation coordinates"""
    if val is None:
        return None
    try:
        # Return as Decimal for DecimalField compatibility
        return Decimal(val).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    except (ValueError, TypeError):
        return val  # Let validators catch invalid data


from .querysets import WorkLogQuerySet


class WorkLogManager(models.Manager):
    """Custom manager for WorkLog with soft delete support"""

    def get_queryset(self):
        """Return only non-deleted records by default"""
        return WorkLogQuerySet(self.model, using=self._db).filter(is_deleted=False)

    def all_with_deleted(self):
        """Return all records including soft deleted ones"""
        return WorkLogQuerySet(self.model, using=self._db)

    def deleted_only(self):
        """Return only soft deleted records"""
        return WorkLogQuerySet(self.model, using=self._db).filter(is_deleted=True)


class WorkLog(models.Model):
    """Work time log entry model with improved validation"""

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="work_logs"
    )
    check_in = models.DateTimeField(help_text="When the employee started work")
    check_out = models.DateTimeField(
        blank=True, null=True, help_text="When the employee finished work"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Location tracking
    location_check_in = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Location where check-in occurred",
    )
    location_check_out = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Location where check-out occurred",
    )

    # GPS coordinates for location tracking
    latitude_check_in = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
        help_text="Latitude coordinate for check-in location",
    )
    longitude_check_in = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
        help_text="Longitude coordinate for check-in location",
    )
    latitude_check_out = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
        help_text="Latitude coordinate for check-out location",
    )
    longitude_check_out = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
        help_text="Longitude coordinate for check-out location",
    )

    # Break time tracking
    break_minutes = models.PositiveIntegerField(
        default=0, help_text="Break time taken during this work session (in minutes)"
    )

    # Additional fields for better tracking
    notes = models.TextField(
        blank=True, help_text="Optional notes about this work session"
    )
    is_approved = models.BooleanField(
        default=False, help_text="Whether this work log has been approved by manager"
    )

    # Soft delete functionality
    is_deleted = models.BooleanField(
        default=False,
        help_text="Soft delete flag - records are marked as deleted instead of being removed",
    )
    deleted_at = models.DateTimeField(
        null=True, blank=True, help_text="When this record was soft deleted"
    )
    deleted_by = models.ForeignKey(
        Employee,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deleted_work_logs",
        help_text="Who deleted this record",
    )

    # Managers
    objects = WorkLogManager()  # Default manager (excludes deleted)
    all_objects = models.Manager()  # Manager that includes deleted records

    class Meta:
        ordering = ["-check_in"]
        verbose_name = "Work Log"
        verbose_name_plural = "Work Logs"
        indexes = [
            # Partial indexes (only index active/non-deleted records for better performance)
            models.Index(
                fields=["employee", "check_in"],
                name="wt_emp_checkin_active_idx",
                condition=models.Q(is_deleted=False),
            ),
            models.Index(
                fields=["check_in"],
                name="wt_checkin_active_idx",
                condition=models.Q(is_deleted=False),
            ),
            models.Index(
                fields=["check_out"],
                name="wt_checkout_active_idx",
                condition=models.Q(is_deleted=False),
            ),
            models.Index(
                fields=["employee", "check_in", "check_out"],
                name="wt_emp_cin_cout_active_idx",
                condition=models.Q(is_deleted=False),
            ),
            models.Index(
                fields=["is_approved"],
                name="wt_approved_active_idx",
                condition=models.Q(is_deleted=False),
            ),
        ]
        constraints = [
            # Ensure only one active check-in per employee (prevent concurrent sessions)
            models.UniqueConstraint(
                fields=["employee"],
                condition=models.Q(check_out__isnull=True, is_deleted=False),
                name="unique_active_checkin_per_employee",
            ),
        ]

    def clean(self):
        """Custom validation"""
        # ✅ Round geolocation coordinates before Django's field validation
        self.latitude_check_in = _round6(self.latitude_check_in)
        self.longitude_check_in = _round6(self.longitude_check_in)
        self.latitude_check_out = _round6(self.latitude_check_out)
        self.longitude_check_out = _round6(self.longitude_check_out)

        super().clean()

        # Check that check_out is after check_in
        if self.check_out and self.check_in and self.check_out <= self.check_in:
            raise ValidationError(
                {"check_out": "Check-out time must be after check-in time"}
            )

        # Check for reasonable work duration (max 16 hours)
        if self.check_out:
            duration = self.get_duration()
            if duration > timedelta(hours=16):
                raise ValidationError(
                    {"check_out": "Work session cannot exceed 16 hours"}
                )

        # Run overlap validation (can be disabled for specific tests if needed)
        self._validate_no_overlaps()

    def _validate_no_overlaps(self):
        """Ensure no overlapping work sessions for the same employee

        OPTIMIZED: Uses database query instead of Python loop
        Complexity: O(N²) -> O(1)
        """
        # Determine end time for comparison
        end_time = self.check_out or timezone.now()

        # OPTIMIZED: Use database query to find overlaps directly
        # Two sessions overlap if:
        # 1. Session A starts before Session B ends AND
        # 2. Session A ends after Session B starts
        overlapping = (
            WorkLog.objects.filter(
                employee=self.employee,
                check_in__lt=end_time,  # Other session starts before this ends
            )
            .filter(
                Q(check_out__isnull=True)  # Other session still ongoing
                | Q(check_out__gt=self.check_in)  # Other session ends after this starts
            )
            .exclude(pk=self.pk)
        )

        if overlapping.exists():
            raise ValidationError(
                "This work session overlaps with another work session"
            )

    def get_duration(self):
        """Get the duration of the work session"""
        if self.check_out:
            return self.check_out - self.check_in
        return timezone.now() - self.check_in

    def get_total_hours(self):
        """Calculate the total number of hours worked in a shift, minus break time"""
        from decimal import Decimal

        duration = self.get_duration()
        hours = duration.total_seconds() / 3600

        # Subtract break time
        break_hours = self.break_minutes / 60.0
        net_hours = hours - break_hours

        return round(Decimal(str(net_hours)), 2)

    def get_overtime_hours(self):
        """Calculate overtime hours using Israeli labor law"""
        from .utils import calc_overtime

        total_hours = self.get_total_hours()
        return calc_overtime(total_hours)

    def get_night_hours(self):
        """Calculate night shift hours (22:00 to 06:00)"""
        if not self.check_out:
            return 0.0
        from .night_shift import night_hours

        return night_hours(self.check_in, self.check_out)

    def is_current_session(self):
        """Check if this is an ongoing work session"""
        return self.check_out is None

    def send_simple_notifications(self):
        """Send simple push notifications for work hour warnings"""
        try:
            from .simple_notifications import SimpleNotificationService

            # Check daily hours
            SimpleNotificationService.check_daily_hours(self.employee, self)

            # Check weekly hours (only on checkout)
            if self.check_out:
                SimpleNotificationService.check_weekly_hours(self.employee)

            # Check if working on holiday
            try:
                from integrations.models import Holiday

                holidays = Holiday.objects.filter(date=self.check_in.date())
                if holidays.exists():
                    holiday = holidays.first()
                    SimpleNotificationService.notify_holiday_work(
                        self.employee, holiday.name
                    )
            except ImportError:
                pass  # Holiday model not available

        except ImportError:
            pass  # Notifications not available

    def get_status(self):
        """Get human-readable status"""
        if self.is_deleted:
            return "Deleted"
        elif self.check_out is None:
            return "In Progress"
        elif self.is_approved:
            return "Approved"
        else:
            return "Pending Approval"

    def soft_delete(self, deleted_by=None):
        """Soft delete this WorkLog record"""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = deleted_by
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    def restore(self):
        """Restore a soft deleted WorkLog record"""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    def save(self, *args, **kwargs):
        # ✅ Round geolocation coordinates to prevent validation errors
        self.latitude_check_in = _round6(self.latitude_check_in)
        self.longitude_check_in = _round6(self.longitude_check_in)
        self.latitude_check_out = _round6(self.latitude_check_out)
        self.longitude_check_out = _round6(self.longitude_check_out)

        # Validate before saving
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        status = (
            "Still working"
            if self.check_out is None
            else f"Worked {self.get_total_hours()}h"
        )
        return f"{self.employee.get_full_name()} - {self.check_in.strftime('%Y-%m-%d %H:%M')} ({status})"
