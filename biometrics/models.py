import uuid

from django.contrib.postgres.fields import JSONField
from django.db import models
from django.utils import timezone

from users.models import Employee


class BiometricProfile(models.Model):
    """Profile storing biometric metadata for an employee"""

    employee = models.OneToOneField(
        Employee, on_delete=models.CASCADE, related_name="biometric_profile"
    )
    embeddings_count = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    mongodb_id = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "biometric_profiles"
        verbose_name = "Biometric Profile"
        verbose_name_plural = "Biometric Profiles"
        indexes = [
            models.Index(fields=["employee"], name="bio_prof_emp_idx"),
            models.Index(fields=["is_active"], name="bio_prof_active_idx"),
            models.Index(fields=["-last_updated"], name="bio_prof_updated_idx"),
            models.Index(fields=["created_at"], name="bio_prof_created_idx"),
        ]

    def __str__(self):
        return f"Biometric Profile for {self.employee.get_full_name()}"


class BiometricLog(models.Model):
    """Log of all biometric check attempts"""

    ACTION_CHOICES = [
        ("check_in", "Check In"),
        ("check_out", "Check Out"),
        ("registration", "Registration"),
        ("failed", "Failed Attempt"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="biometric_logs",
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    confidence_score = models.FloatField(null=True, blank=True)
    location = models.CharField(max_length=255, blank=True)
    device_info = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    processing_time_ms = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "biometric_logs"
        verbose_name = "Biometric Log"
        verbose_name_plural = "Biometric Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employee", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["success", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.action} - {self.employee.get_full_name() if self.employee else 'Unknown'} - {self.created_at}"


class BiometricAttempt(models.Model):
    """Track failed attempts for rate limiting"""

    ip_address = models.GenericIPAddressField()
    attempts_count = models.IntegerField(default=0)
    last_attempt = models.DateTimeField(auto_now=True)
    blocked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "biometric_attempts"
        verbose_name = "Biometric Attempt"
        verbose_name_plural = "Biometric Attempts"
        indexes = [
            models.Index(fields=["ip_address"], name="bio_attempt_ip_idx"),
            models.Index(
                fields=["ip_address", "blocked_until"],
                name="bio_attempt_ip_blocked_idx",
            ),
            models.Index(fields=["blocked_until"], name="bio_attempt_blocked_idx"),
            models.Index(fields=["last_attempt"], name="bio_attempt_last_idx"),
        ]

    def is_blocked(self):
        if self.blocked_until:
            return timezone.now() < self.blocked_until
        return False

    def increment_attempts(self):
        self.attempts_count += 1
        self.last_attempt = timezone.now()

        # Block after 5 failed attempts
        if self.attempts_count >= 5:
            self.blocked_until = timezone.now() + timezone.timedelta(minutes=5)

        self.save()

    def reset_attempts(self):
        self.attempts_count = 0
        self.blocked_until = None
        self.save()


class FaceQualityCheck(models.Model):
    """Store face quality metrics for monitoring"""

    biometric_log = models.OneToOneField(
        BiometricLog, on_delete=models.CASCADE, related_name="quality_check"
    )
    face_detected = models.BooleanField(default=False)
    face_count = models.IntegerField(default=0)
    brightness_score = models.FloatField(null=True, blank=True)
    blur_score = models.FloatField(null=True, blank=True)
    face_size_ratio = models.FloatField(null=True, blank=True)
    eye_visibility = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "face_quality_checks"
        verbose_name = "Face Quality Check"
        verbose_name_plural = "Face Quality Checks"
