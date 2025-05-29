from django.db import models
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
import re

class Employee(models.Model):
    """Employee model with improved validation"""
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
    is_active = models.BooleanField(
        default=True,
        help_text="Whether the employee is currently active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # Добавлено

    EMPLOYMENT_TYPES = [
        ('monthly', 'Monthly Salary'),
        ('hourly', 'Hourly Wage'),
        ('contract', 'Contract Work'),
    ]
    employment_type = models.CharField(
        max_length=10, 
        choices=EMPLOYMENT_TYPES, 
        default='hourly',
        help_text="Type of employment contract"
    )

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
        
        # Validate phone number format
        if self.phone and not self._is_valid_phone(self.phone):
            raise ValidationError({
                'phone': 'Phone number must be in international format (+972... or +1...)'
            })
        
        # Validate email domain (optional business rule)
        if self.email and not self._is_valid_business_email(self.email):
            raise ValidationError({
                'email': 'Please use a business email address'
            })

    def _is_valid_phone(self, phone):
        """Validate phone number format"""
        # Simple international format validation
        phone_pattern = r'^\+\d{1,3}\d{8,15}$'
        return re.match(phone_pattern, phone.replace(' ', '').replace('-', ''))

    def _is_valid_business_email(self, email):
        """Validate business email (exclude common personal email providers)"""
        personal_domains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com']
        domain = email.split('@')[1].lower()
        return domain not in personal_domains

    def save(self, *args, **kwargs):
        # Clean data before saving
        self.full_clean()
        
        # Save current state before making changes
        is_new = self.pk is None
        old_employment_type = None
        
        if not is_new:
            try:
                old_employee = Employee.objects.get(pk=self.pk)
                old_employment_type = old_employee.employment_type
            except Employee.DoesNotExist:
                pass
                
        # Save the employee
        super().save(*args, **kwargs)

        # Update salary if employment type has changed
        if not is_new and old_employment_type and old_employment_type != self.employment_type:
            self._update_salary_calculation_type()

    def _update_salary_calculation_type(self):
        """Update salary calculation type when employment type changes"""
        employment_type_mapping = {
            'hourly': 'hourly',
            'monthly': 'monthly',
            'contract': 'project'
        }

        try:
            from payroll.models import Salary
            salary = Salary.objects.get(employee=self)
            salary.calculation_type = employment_type_mapping.get(
                self.employment_type, 'hourly'
            )
            salary.save()
        except ImportError:
            # Handle circular import during migrations
            pass
        except Salary.DoesNotExist:
            # No salary record exists yet
            pass

    def get_full_name(self):
        """Return the employee's full name"""
        return f"{self.first_name} {self.last_name}".strip()

    def get_display_name(self):
        """Return name for display purposes"""
        return f"{self.get_full_name()} ({self.email})"

    def __str__(self):
        return self.get_full_name()


