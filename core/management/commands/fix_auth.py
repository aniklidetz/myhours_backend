from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from users.models import Employee, EnhancedDeviceToken

User = get_user_model()


class Command(BaseCommand):
    help = "Fix authentication issues"

    def handle(self, *args, **options):
        self.stdout.write("Fixing authentication issues...")

        # 1. Clean up expired tokens
        old_tokens = EnhancedDeviceToken.objects.filter(expires_at__lt=timezone.now())
        deleted_count = old_tokens.count()
        old_tokens.delete()
        self.stdout.write(f"Deleted {deleted_count} expired tokens")

        # 2. Deactivate all active tokens (force re-login)
        active_tokens = EnhancedDeviceToken.objects.filter(is_active=True)
        active_count = active_tokens.count()
        active_tokens.update(is_active=False)
        self.stdout.write(f"Deactivated {active_count} active tokens")

        # 3. Fix User-Employee relationships
        self.stdout.write("\nFixing User-Employee relationships:")

        users_without_employees = User.objects.filter(employee__isnull=True)
        for user in users_without_employees:
            try:
                employee = Employee.objects.get(email=user.email)
                if not employee.user:
                    employee.user = user
                    employee.save()
                    self.stdout.write(f"Linked {user.email} to existing Employee")
            except Employee.DoesNotExist:
                employee = Employee.objects.create(
                    user=user,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    email=user.email,
                    role=(
                        "employee"
                        if not user.is_staff
                        else ("admin" if user.is_superuser else "accountant")
                    ),
                    hourly_rate=50.0,
                    employment_type="full_time",
                )
                self.stdout.write(f"Created Employee for {user.email}")

        employees_without_users = Employee.objects.filter(user__isnull=True)
        for employee in employees_without_users:
            try:
                user = User.objects.get(email=employee.email)
                employee.user = user
                employee.save()
                self.stdout.write(f"Linked Employee {employee.email} to User")
            except User.DoesNotExist:
                user = User.objects.create_user(
                    email=employee.email,
                    first_name=employee.first_name,
                    last_name=employee.last_name,
                    password="temp123",
                    is_staff=employee.role in ["admin", "accountant"],
                    is_superuser=employee.role == "admin",
                )
                employee.user = user
                employee.save()
                self.stdout.write(
                    f"Created User for {employee.email} (password: temp123)"
                )

        # 4. Summary
        self.stdout.write(f"\nFinal counts:")
        self.stdout.write(f"   Users: {User.objects.count()}")
        self.stdout.write(f"   Employees: {Employee.objects.count()}")
        self.stdout.write(
            f"   Active tokens: {EnhancedDeviceToken.objects.filter(is_active=True).count()}"
        )

        self.stdout.write(self.style.SUCCESS("\nAuthentication issues fixed!"))
        self.stdout.write("Note: All users will need to login again")
