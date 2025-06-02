# users/models.py
from django.db import models
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
import re

class Employee(models.Model):
    """Employee model with improved validation and role support"""
    
    # Link to Django user
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='employee_profile',
        null=True,
        blank=True
    )
    
    # Basic info
    first_name = models.CharField(
        max_length=50, 
        help_text="Employee's first name"
    )
    last_name = models.CharField(
        max_length=50, 
        help_text="Employee's last name"
    )
    email = models.EmailField(
        unique=True,
        help_text="Employee's email address"
    )
    phone = models.CharField(
        max_length=20, 
        blank=True, 
        null=True,
        help_text="Phone number in international format"
    )
    
    # Employment details
    EMPLOYMENT_TYPES = [
        ('full_time', 'Full Time'),
        ('part_time', 'Part Time'),
        ('hourly', 'Hourly'),
        ('contract', 'Contract'),
    ]
    employment_type = models.CharField(
        max_length=10, 
        choices=EMPLOYMENT_TYPES, 
        default='full_time',
        help_text="Type of employment"
    )
    
    # Role
    ROLE_CHOICES = [
        ('employee', 'Employee'),
        ('accountant', 'Accountant'),
        ('admin', 'Administrator'),
    ]
    role = models.CharField(
        max_length=20, 
        choices=ROLE_CHOICES, 
        default='employee'
    )
    
    # Salary info
    hourly_rate = models.DecimalField(
        max_digits=8, 
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Hourly rate for hourly employees"
    )
    
    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Whether the employee is currently active"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name = 'Employee'
        verbose_name_plural = 'Employees'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['is_active']),
        ]

    def clean(self):
        """Custom validation"""
        super().clean()
        
        # Validate phone number format if provided
        if self.phone and not self._is_valid_phone(self.phone):
            raise ValidationError({
                'phone': 'Phone number must be in international format (+972... or +1...)'
            })

    def _is_valid_phone(self, phone):
        """Validate phone number format"""
        # Simple international format validation
        phone_pattern = r'^\+\d{1,3}\d{8,15}$'
        cleaned_phone = phone.replace(' ', '').replace('-', '')
        return re.match(phone_pattern, cleaned_phone) is not None

    def save(self, *args, **kwargs):
        # Create or update Django user
        if not self.user and self.email:
            username = self.email.split('@')[0]
            # Check if username already exists
            if User.objects.filter(username=username).exists():
                username = f"{username}_{self.id or User.objects.count()}"
            
            self.user = User.objects.create_user(
                username=username,
                email=self.email,
                first_name=self.first_name,
                last_name=self.last_name
            )
            
            # Set permissions based on role
            if self.role == 'admin':
                self.user.is_staff = True
                self.user.is_superuser = True
            elif self.role == 'accountant':
                self.user.is_staff = True
                self.user.is_superuser = False
            else:
                self.user.is_staff = False
                self.user.is_superuser = False
            
            self.user.save()
        
        # Update existing user if needed
        elif self.user:
            self.user.first_name = self.first_name
            self.user.last_name = self.last_name
            self.user.email = self.email
            
            # Update permissions based on role
            if self.role == 'admin':
                self.user.is_staff = True
                self.user.is_superuser = True
            elif self.role == 'accountant':
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