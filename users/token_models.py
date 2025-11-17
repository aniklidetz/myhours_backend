# users/token_models.py
import logging
import secrets
import uuid
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class DeviceToken(models.Model):
    """Enhanced token model with device tracking and expiration"""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="device_tokens"
    )
    token = models.CharField(max_length=64, unique=True)
    device_id = models.CharField(max_length=100, help_text="Unique device identifier")
    device_info = models.JSONField(
        default=dict, help_text="Device metadata (OS, model, etc)"
    )

    # Security tracking
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    # Location and usage tracking
    last_ip = models.GenericIPAddressField(null=True, blank=True)
    last_location = models.JSONField(null=True, blank=True)
    usage_count = models.PositiveIntegerField(default=0)

    # Biometric verification status
    biometric_verified = models.BooleanField(default=False)
    biometric_verified_at = models.DateTimeField(null=True, blank=True)

    # Token rotation fields (for replay attack detection)
    rotation_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this token has been rotated"
    )
    previous_token = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        db_index=True,
        help_text="Previous token before rotation (for replay attack detection)"
    )
    previous_token_expires_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Grace period for previous token (allows for clock skew)"
    )

    class Meta:
        unique_together = ["user", "device_id"]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.device_id[:8]}..."

    @classmethod
    def create_token(cls, user, device_id, device_info=None, ttl_days=7):
        """Create a new device token"""
        # Deactivate old tokens for this device
        cls.objects.filter(user=user, device_id=device_id).update(is_active=False)

        token = secrets.token_hex(32)  # 64 character hex token
        expires_at = timezone.now() + timedelta(days=ttl_days)

        return cls.objects.create(
            user=user,
            token=token,
            device_id=device_id,
            device_info=device_info or {},
            expires_at=expires_at,
        )

    def is_valid(self):
        """Check if token is valid and not expired"""
        return self.is_active and self.expires_at > timezone.now()

    def refresh(self, ttl_days=7, grace_period_seconds=300):
        """
        Rotate token for security (prevents replay attacks).

        Returns the new token string or None if rotation failed.

        Token rotation:
        1. Store current token in previous_token with grace period
        2. Generate new token
        3. Increment rotation_count
        4. Update expires_at
        """
        if not self.is_valid():
            return None

        # Store current token for grace period (handles clock skew)
        self.previous_token = self.token
        self.previous_token_expires_at = timezone.now() + timedelta(seconds=grace_period_seconds)

        # Generate new token
        new_token = secrets.token_hex(32)
        self.token = new_token

        # Update rotation count and expiration
        self.rotation_count += 1
        self.expires_at = timezone.now() + timedelta(days=ttl_days)

        self.save(update_fields=[
            "token",
            "previous_token",
            "previous_token_expires_at",
            "rotation_count",
            "expires_at"
        ])

        logger.info(
            f"Token rotated for user {self.user.username}, "
            f"device {self.device_id[:8]}..., "
            f"rotation_count={self.rotation_count}"
        )

        return new_token

    def mark_used(self, ip_address=None, location=None):
        """Mark token as used and update tracking info"""
        self.last_used = timezone.now()
        self.usage_count += 1
        if ip_address:
            self.last_ip = ip_address
        if location:
            self.last_location = location
        self.save(
            update_fields=["last_used", "usage_count", "last_ip", "last_location"]
        )

    def mark_biometric_verified(self):
        """Mark that biometric verification was successful"""
        self.biometric_verified = True
        self.biometric_verified_at = timezone.now()
        self.save(update_fields=["biometric_verified", "biometric_verified_at"])

    def requires_biometric_verification(self):
        """Check if biometric verification is required"""
        # Require biometric verification if:
        # 1. Never verified, OR
        # 2. Last verification was more than 24 hours ago
        if not self.biometric_verified:
            return True

        if self.biometric_verified_at:
            time_since_verification = timezone.now() - self.biometric_verified_at
            return time_since_verification > timedelta(hours=24)

        return True


class TokenRefreshLog(models.Model):
    """Log token refresh events for security monitoring"""

    device_token = models.ForeignKey(DeviceToken, on_delete=models.CASCADE)
    old_expires_at = models.DateTimeField()
    new_expires_at = models.DateTimeField()
    refreshed_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        ordering = ["-refreshed_at"]


class BiometricSession(models.Model):
    """Track biometric authentication sessions"""

    device_token = models.ForeignKey(DeviceToken, on_delete=models.CASCADE)
    session_id = models.UUIDField(default=uuid.uuid4, unique=True)

    # Biometric verification details
    verification_method = models.CharField(max_length=50, default="face_recognition")
    confidence_score = models.FloatField()
    quality_score = models.FloatField(null=True, blank=True)

    # Session tracking
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    # Location and context
    location = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    @classmethod
    def create_session(
        cls,
        device_token,
        confidence_score,
        quality_score=None,
        location=None,
        ip_address=None,
        ttl_hours=8,
    ):
        """Create a new biometric session"""
        expires_at = timezone.now() + timedelta(hours=ttl_hours)

        # End any existing active sessions for this device
        cls.objects.filter(device_token=device_token, is_active=True).update(
            is_active=False
        )

        return cls.objects.create(
            device_token=device_token,
            confidence_score=confidence_score,
            quality_score=quality_score,
            location=location,
            ip_address=ip_address,
            expires_at=expires_at,
        )

    def is_valid(self):
        """Check if biometric session is valid"""
        return self.is_active and self.expires_at > timezone.now()

    def extend_session(self, hours=2):
        """Extend biometric session"""
        if self.is_valid():
            self.expires_at = timezone.now() + timedelta(hours=hours)
            self.save(update_fields=["expires_at"])
            return True
        return False
