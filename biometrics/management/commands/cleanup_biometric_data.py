"""
Management command to clean up biometric data for employees
Handles both MongoDB and PostgreSQL cleanup with proper error handling
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from biometrics.models import BiometricProfile
from biometrics.services.enhanced_biometric_service import enhanced_biometric_service
from users.models import Employee

logger = logging.getLogger("biometrics")


class Command(BaseCommand):
    help = "Clean up biometric data for specified employees or all employees"

    def add_arguments(self, parser):
        parser.add_argument(
            "--employee-id", type=int, help="Specific employee ID to clean up"
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Clean up ALL biometric data (use with caution)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force cleanup even if inconsistencies are found",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )

    def handle(self, *args, **options):
        if not options["employee_id"] and not options["all"]:
            raise CommandError("You must specify either --employee-id or --all")

        if options["all"] and not options["force"]:
            raise CommandError(
                "To clean up ALL biometric data, you must use --force flag. "
                "This is a destructive operation!"
            )

        # Determine which employees to process
        if options["employee_id"]:
            employee_ids = [options["employee_id"]]
            # Validate employee exists
            try:
                Employee.objects.get(id=options["employee_id"])
            except Employee.DoesNotExist:
                raise CommandError(f'Employee {options["employee_id"]} does not exist')
        else:
            # Get all employees with biometric profiles
            employee_ids = list(
                BiometricProfile.objects.filter(is_active=True).values_list(
                    "employee_id", flat=True
                )
            )

        if not employee_ids:
            self.stdout.write(self.style.WARNING("No biometric data found to clean up"))
            return

        self.stdout.write(
            f"Found {len(employee_ids)} employees with biometric data: {employee_ids}"
        )

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No data will be actually deleted")
            )

        # Process each employee
        success_count = 0
        error_count = 0

        for employee_id in employee_ids:
            try:
                self.process_employee(employee_id, options["dry_run"], options["force"])
                success_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Failed to cleanup employee {employee_id}: {e}")
                )
                error_count += 1

        # Summary
        self.stdout.write("")
        self.stdout.write(f"Cleanup completed:")
        self.stdout.write(f"  Successful: {success_count}")
        self.stdout.write(f"  Errors: {error_count}")

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING("This was a dry run - no data was actually deleted")
            )

    def process_employee(self, employee_id: int, dry_run: bool, force: bool):
        """Process cleanup for a single employee"""
        self.stdout.write(f"\nProcessing employee {employee_id}...")

        # Check current status
        status = enhanced_biometric_service.get_employee_biometric_status(employee_id)

        pg_exists = status.get("postgresql", {}).get("exists", False)
        mongo_exists = status.get("mongodb", {}).get("exists", False)
        is_consistent = status.get("is_consistent", False)

        self.stdout.write(f'  PostgreSQL data: {"Yes" if pg_exists else "No"}')
        self.stdout.write(f'  MongoDB data: {"Yes" if mongo_exists else "No"}')
        self.stdout.write(f'  Consistent: {"Yes" if is_consistent else "No"}')

        if not pg_exists and not mongo_exists:
            self.stdout.write("  No biometric data found - skipping")
            return

        # Warn about inconsistencies
        if not is_consistent and not force:
            raise CommandError(
                f"Employee {employee_id} has inconsistent data. "
                "Use --force to proceed anyway."
            )

        if dry_run:
            self.stdout.write("  [DRY RUN] Would delete biometric data")
            return

        # Perform actual cleanup
        with transaction.atomic():
            success = enhanced_biometric_service.delete_biometric(employee_id)

            if success:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Successfully cleaned up employee {employee_id}"
                    )
                )
            else:
                raise Exception("delete_biometric returned False")

            # Verify cleanup
            post_status = enhanced_biometric_service.get_employee_biometric_status(
                employee_id
            )
            post_pg = post_status.get("postgresql", {}).get("exists", False)
            post_mongo = post_status.get("mongodb", {}).get("exists", False)

            if post_pg or post_mongo:
                raise Exception(
                    f"Cleanup verification failed - data still exists: "
                    f"PostgreSQL={post_pg}, MongoDB={post_mongo}"
                )

            self.stdout.write("  Cleanup verification: PASSED")

    def handle_inconsistent_data(self, employee_id: int, force: bool):
        """
        Handle cases where MongoDB and PostgreSQL are out of sync
        This can happen due to the ID mismatch bug
        """
        if not force:
            raise CommandError(
                f"Employee {employee_id} has inconsistent biometric data. "
                "This may be due to ID mismatch issues. Use --force to proceed."
            )

        # Force cleanup with both methods
        from biometrics.models import BiometricProfile
        from biometrics.services.mongodb_repository import MongoBiometricRepository

        mongo_repo = MongoBiometricRepository()

        # Clean MongoDB by employee_id (not by stored MongoDB ID)
        mongo_success = mongo_repo.delete_embeddings(employee_id)

        # Clean PostgreSQL
        pg_updated = BiometricProfile.objects.filter(employee_id=employee_id).update(
            is_active=False, embeddings_count=0
        )

        self.stdout.write(
            f"  Force cleanup: MongoDB={mongo_success}, PostgreSQL={pg_updated > 0}"
        )
