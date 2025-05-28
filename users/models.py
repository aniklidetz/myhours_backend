from django.db import models

class Employee(models.Model):
    """Employee model"""
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    EMPLOYMENT_TYPES = [
        ('monthly', 'Monthly Salary'),  # Fixed monthly salary
        ('hourly', 'Hourly Wage'),      # Hourly wage
        ('contract', 'Contract Work'),  # Contract-based work
    ]
    employment_type = models.CharField(
        max_length=10, choices=EMPLOYMENT_TYPES, default='hourly'
    )  # Type of employment

    def save(self, *args, **kwargs):
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
            employment_type_mapping = {
                'hourly': 'hourly',
                'monthly': 'monthly',
                'contract': 'project'
            }

            from payroll.models import Salary
            try:
                salary = Salary.objects.get(employee=self)
                salary.calculation_type = employment_type_mapping.get(self.employment_type, 'hourly')
                salary.save()
            except Salary.DoesNotExist:
                pass

    def __str__(self):
        return f"{self.first_name} {self.last_name}"