from django.db import models
from users.models import Employee

class WorkLog(models.Model):
    """Work time log entry model"""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    check_in = models.DateTimeField()
    check_out = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)  # Record creation date
    location_check_in = models.CharField(max_length=255, blank=True, null=True)
    location_check_out = models.CharField(max_length=255, blank=True, null=True)

    def get_total_hours(self):
        """
        Calculates the total number of hours worked in a shift.
        """
        if self.check_out:
            duration = self.check_out - self.check_in
            return duration.total_seconds() / 3600  # Convert to hours
        return 0  # If check_out is missing, the employee is still working

    def __str__(self):
        return f"{self.employee} - {self.check_in} to {self.check_out or 'Still working'}"