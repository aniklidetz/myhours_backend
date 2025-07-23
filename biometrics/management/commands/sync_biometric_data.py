# biometrics/management/commands/sync_biometric_data.py
from django.core.management.base import BaseCommand
from django.conf import settings
from biometrics.services.mongodb_service import mongodb_service
from biometrics.models import BiometricProfile
from users.models import Employee
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Synchronize PostgreSQL BiometricProfile with MongoDB data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--employee-id',
            type=int,
            help='Sync specific employee ID only'
        )
        parser.add_argument(
            '--create-missing',
            action='store_true',
            help='Create MongoDB entries for PostgreSQL profiles without data'
        )

    def handle(self, *args, **options):
        employee_id = options.get('employee_id')
        create_missing = options.get('create_missing', False)

        if employee_id:
            self.sync_employee(employee_id, create_missing)
        else:
            self.sync_all_employees(create_missing)

    def sync_employee(self, employee_id, create_missing=False):
        """Sync single employee"""
        try:
            employee = Employee.objects.get(id=employee_id)
            self.stdout.write(f"Syncing employee {employee_id}: {employee.get_full_name()}")

            # Check PostgreSQL BiometricProfile
            try:
                profile = employee.biometric_profile
                self.stdout.write(f"  PostgreSQL profile: {profile.embeddings_count} embeddings, active: {profile.is_active}")
            except BiometricProfile.DoesNotExist:
                self.stdout.write(f"  No PostgreSQL BiometricProfile found")
                return

            # Check MongoDB data
            mongo_embeddings = mongodb_service.get_face_embeddings(employee_id)
            if mongo_embeddings:
                self.stdout.write(f"  MongoDB: {len(mongo_embeddings)} embeddings found")
            else:
                self.stdout.write(f"  MongoDB: No embeddings found")
                
                if create_missing and profile.embeddings_count > 0:
                    self.stdout.write(f"  Creating placeholder MongoDB entry...")
                    # Create a placeholder entry (requires actual face registration)
                    self.stdout.write(f"  WARNING: Employee {employee_id} needs to re-register their face")

        except Employee.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Employee {employee_id} not found"))

    def sync_all_employees(self, create_missing=False):
        """Sync all employees with BiometricProfile"""
        profiles = BiometricProfile.objects.all()
        
        self.stdout.write(f"Found {profiles.count()} BiometricProfiles to check")
        
        for profile in profiles:
            employee_id = profile.employee.id
            self.sync_employee(employee_id, create_missing)

    def check_mongodb_connection(self):
        """Check MongoDB connection"""
        if mongodb_service.health_check():
            self.stdout.write(self.style.SUCCESS("MongoDB connection: OK"))
            stats = mongodb_service.get_statistics()
            self.stdout.write(f"MongoDB stats: {stats}")
        else:
            self.stdout.write(self.style.ERROR("MongoDB connection: FAILED"))