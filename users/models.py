# users/models.py
import re

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models


class EmployeeQuerySet(models.QuerySet):
    """Custom QuerySet for Employee model with N+1 optimization annotations"""

    def with_optimized_annotations(self):
        """Add annotations to avoid N+1 queries for computed properties"""
        from django.db.models import Exists, OuterRef

        # Import here to avoid circular imports
        from biometrics.models import BiometricProfile

        return self.annotate(
            # Annotate has_biometric to avoid N+1 queries
            has_biometric_annotation=Exists(
                BiometricProfile.objects.filter(employee=OuterRef("pk"))
            ),
            # Annotate has_pending_invitation to avoid N+1 queries
            has_pending_invitation_annotation=Exists(
                EmployeeInvitation.objects.filter(
                    employee=OuterRef("pk"),
                    accepted_at__isnull=True,
                    expires_at__gt=models.functions.Now(),
                )
            ),
        )


class EmployeeManager(models.Manager):
    """Custom manager for Employee model"""

    def get_queryset(self):
        return EmployeeQuerySet(self.model, using=self._db)

    def with_optimized_annotations(self):
        """Get employees with optimized annotations"""
        return self.get_queryset().with_optimized_annotations()


class Employee(models.Model):
    """Employee model with improved validation and role support"""

    # Custom manager with N+1 optimization
    objects = EmployeeManager()

    # Link to Django user (null until invitation is accepted)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="employees",
        null=True,
        blank=True,
        help_text="Django user account (created when invitation is accepted)",
    )

    # Basic info
    first_name = models.CharField(max_length=50, help_text="Employee's first name")
    last_name = models.CharField(max_length=50, help_text="Employee's last name")
    email = models.EmailField(unique=True, help_text="Employee's email address")
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Phone number in international format",
    )

    # Employment details
    EMPLOYMENT_TYPES = [
        ("full_time", "Full Time"),
        ("part_time", "Part Time"),
        ("hourly", "Hourly"),
        ("contract", "Contract"),
    ]
    employment_type = models.CharField(
        max_length=10,
        choices=EMPLOYMENT_TYPES,
        default="full_time",
        help_text="Type of employment",
    )

    # Role
    ROLE_CHOICES = [
        ("employee", "Employee"),
        ("manager", "Manager"),
        ("accountant", "Accountant"),
        ("admin", "Administrator"),
        ("hr", "HR"),
        ("project_manager", "Project Manager"),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="employee")

    # Salary info
    hourly_rate = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Hourly rate for hourly employees",
    )

    monthly_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Monthly salary for full-time employees",
    )

    # Status
    is_active = models.BooleanField(
        default=True, help_text="Whether the employee is currently active"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        verbose_name = "Employee"
        verbose_name_plural = "Employees"
        default_related_name = "employees"
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["role"]),
            models.Index(fields=["employment_type"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "employment_type"],
                name="uniq_user_employment_type",
            )
        ]

    def clean(self):
        """Custom validation"""
        super().clean()

        # Validate phone number format if provided
        if self.phone and not self._is_valid_phone(self.phone):
            raise ValidationError(
                {
                    "phone": "Phone number must be in international format (+972... or +1...)"
                }
            )

        # Validate employment_type choices
        if self.employment_type and self.employment_type not in [
            choice[0] for choice in self.EMPLOYMENT_TYPES
        ]:
            raise ValidationError(
                {
                    "employment_type": f'Invalid employment type. Must be one of: {", ".join([choice[0] for choice in self.EMPLOYMENT_TYPES])}'
                }
            )

        # Validate role choices
        if self.role and self.role not in [choice[0] for choice in self.ROLE_CHOICES]:
            raise ValidationError(
                {
                    "role": f'Invalid role. Must be one of: {", ".join([choice[0] for choice in self.ROLE_CHOICES])}'
                }
            )

    def _is_valid_phone(self, phone):
        """Validate phone number format"""
        # Simple international format validation
        phone_pattern = r"^\+\d{1,3}\d{8,15}$"
        cleaned_phone = phone.replace(" ", "").replace("-", "")
        return re.match(phone_pattern, cleaned_phone) is not None

    def save(self, *args, **kwargs):
        # Don't auto-create user anymore - users are created when invitation is accepted
        # Update existing user if present
        if self.user:
            self.user.first_name = self.first_name
            self.user.last_name = self.last_name
            self.user.email = self.email

            # Update permissions based on role
            if self.role == "admin":
                self.user.is_staff = True
                self.user.is_superuser = True
            elif self.role in ["accountant", "manager", "hr", "project_manager"]:
                self.user.is_staff = True
                self.user.is_superuser = False
            else:
                self.user.is_staff = False
                self.user.is_superuser = False

            self.user.save()

        super().save(*args, **kwargs)

    def get_full_name(self):
        """Return the employee's full name"""
        return f"{self.first_name} {self.last_name}".strip()

    def get_display_name(self):
        """Return name for display purposes"""
        return f"{self.get_full_name()} ({self.email})"

    def __str__(self):
        return self.get_full_name()

    @property
    def is_registered(self):
        """Check if employee has completed registration (has user account)"""
        return self.user is not None

    @property
    def salary_info(self):
        """Get salary information for this employee"""
        from payroll.models import Salary

        try:
            return Salary.objects.get(employee=self)
        except Salary.DoesNotExist:
            return None

    @property
    def salary(self):
        """BACKWARD COMPATIBILITY: Alias for salary_info"""
        return self.salary_info

    @property
    def worklog_set(self):
        """BACKWARD COMPATIBILITY: Get related WorkLog objects"""
        from worktime.models import WorkLog

        return WorkLog.objects.filter(employee=self)

    @property
    def has_biometric(self):
        """Check if employee has registered biometric data - optimized with annotations"""
        # Use annotation if available (for bulk queries)
        if hasattr(self, "has_biometric_annotation"):
            return self.has_biometric_annotation

        # Fallback to database query for individual lookups
        if not self.user:
            return False
        # Check if biometric profile exists
        try:
            from biometrics.models import BiometricProfile

            return BiometricProfile.objects.filter(employee=self).exists()
        except:
            return False

    def send_notification(self, message, notification_type="info"):
        """Send notification to employee (placeholder implementation for tests)"""
        import logging

        logger = logging.getLogger("users.models")
        logger.info(f"Notification to {self.email}: [{notification_type}] {message}")
        return True


# Invitation model
import secrets
from datetime import timedelta

# Import enhanced token models
from .token_models import BiometricSession, DeviceToken, TokenRefreshLog


class EmployeeInvitation(models.Model):
    """
    Model for managing employee invitations
    """

    employee = models.OneToOneField(
        Employee, on_delete=models.CASCADE, related_name="invitation"
    )

    # Invitation details
    token = models.CharField(max_length=64, unique=True, db_index=True)
    invited_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="sent_invitations"
    )

    # Status tracking
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)

    # Email tracking
    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"Invitation for {self.employee.email} - {'Accepted' if self.is_accepted else 'Pending'}"

    @classmethod
    def create_invitation(cls, employee, invited_by, days_valid=2):
        """Create a new invitation with secure token"""
        from django.utils import timezone

        invitation = cls.objects.create(
            employee=employee,
            invited_by=invited_by,
            token=secrets.token_urlsafe(32),
            expires_at=timezone.now() + timedelta(days=days_valid),
        )
        return invitation

    @property
    def is_valid(self):
        """Check if invitation is still valid"""
        from django.utils import timezone

        return not self.is_accepted and timezone.now() < self.expires_at

    @property
    def is_accepted(self):
        """Check if invitation has been accepted"""
        return self.accepted_at is not None

    @property
    def is_expired(self):
        """Check if invitation has expired"""
        from django.utils import timezone

        return timezone.now() >= self.expires_at

    def accept(self, user):
        """Mark invitation as accepted and link user to employee"""
        from django.utils import timezone

        self.accepted_at = timezone.now()
        self.save()

        # Link the user to the employee
        self.employee.user = user
        self.employee.save()

        return self.employee

    def get_invitation_url(self, base_url):
        """Generate the invitation acceptance URL"""
        return f"{base_url}/invite?token={self.token}"
