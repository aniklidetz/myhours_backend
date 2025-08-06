from users.models import Employee
from worktime.models import WorkLog
from payroll.models import Salary
from django.utils import timezone
from decimal import Decimal


class TestFixtures:
    """Test data factory"""

    @staticmethod
    def create_employee(first_name="Test", last_name="User", email=None, **kwargs):
        """Create test employee"""
        if email is None:
            email = f"{first_name.lower()}.{last_name.lower()}@example.com"

        defaults = {"employment_type": "hourly", "is_active": True}
        defaults.update(kwargs)

        return Employee.objects.create(
            first_name=first_name, last_name=last_name, email=email, **defaults
        )

    @staticmethod
    def create_worklog(employee, hours=8, days_ago=0):
        """Create work time record"""
        check_in = timezone.now() - timezone.timedelta(days=days_ago)
        check_out = check_in + timezone.timedelta(hours=hours)

        return WorkLog.objects.create(
            employee=employee, check_in=check_in, check_out=check_out
        )

    @staticmethod
    def create_salary(employee, hourly_rate=50.00, **kwargs):
        """Create salary record"""
        defaults = {"base_salary": Decimal("0.00"), "currency": "ILS"}
        defaults.update(kwargs)

        return Salary.objects.create(
            employee=employee, hourly_rate=Decimal(str(hourly_rate)), **defaults
        )
