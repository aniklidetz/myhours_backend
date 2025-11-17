import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from biometrics.models import BiometricProfile
from biometrics.services.mongodb_repository import MongoBiometricRepository
from users.models import Employee

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Check and fix biometric IDs in MongoDB to match PostgreSQL"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Fix mismatched IDs",
        )

    def handle(self, *args, **options):
        fix_mode = options["fix"]

        self.stdout.write("Checking biometric ID consistency...")

        # Initialize MongoDB service
        mongodb_service = MongoBiometricRepository()

        if mongodb_service.collection is None:
            self.stdout.write(self.style.ERROR("MongoDB not available"))
            return

        # Check all employees with biometric profiles
        employees = Employee.objects.filter(
            biometric_profile__isnull=False
        ).select_related("user", "biometric_profile")

        mismatches = []

        for employee in employees:
            profile = employee.biometric_profile
            user = employee.user

            # Get MongoDB data
            mongo_data = mongodb_service.collection.find_one(
                {"employee_id": employee.id}
            )

            self.stdout.write(
                f"\nEmployee: {employee.get_full_name()} (ID: {employee.id})"
            )
            self.stdout.write(f"  User ID: {user.id} ({user.email})")
            self.stdout.write(f"  Biometric Profile: {profile.id}")
            self.stdout.write(f"  MongoDB ID: {profile.mongodb_id}")

            if mongo_data:
                stored_employee_id = mongo_data.get("employee_id")
                self.stdout.write(f"  MongoDB employee_id: {stored_employee_id}")

                if stored_employee_id != employee.id:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  ⚠️  MISMATCH: MongoDB has employee_id {stored_employee_id}, "
                            f"but PostgreSQL employee.id is {employee.id}"
                        )
                    )
                    mismatches.append(
                        {
                            "employee": employee,
                            "mongo_id": stored_employee_id,
                            "correct_id": employee.id,
                            "mongo_doc_id": mongo_data["_id"],
                        }
                    )
                else:
                    self.stdout.write(self.style.SUCCESS("  ✓ IDs match"))
            else:
                # Check if there's a document with wrong employee_id
                wrong_doc = None

                # Check if document exists under user.id
                if user.id != employee.id:
                    wrong_doc = mongodb_service.collection.find_one(
                        {"employee_id": user.id}
                    )
                    if wrong_doc:
                        self.stdout.write(
                            self.style.WARNING(
                                f"  ⚠️  Found document with user.id {user.id} instead of employee.id {employee.id}"
                            )
                        )
                        mismatches.append(
                            {
                                "employee": employee,
                                "mongo_id": user.id,
                                "correct_id": employee.id,
                                "mongo_doc_id": wrong_doc["_id"],
                            }
                        )

                if not wrong_doc:
                    self.stdout.write(self.style.ERROR("  ✗ No MongoDB document found"))

        # Summary
        self.stdout.write(f"\n{'='*50}")
        self.stdout.write(f"Total employees checked: {employees.count()}")
        self.stdout.write(f"Mismatches found: {len(mismatches)}")

        if mismatches and fix_mode:
            self.stdout.write("\nFixing mismatches...")

            for mismatch in mismatches:
                try:
                    # Update MongoDB document
                    result = mongodb_service.collection.update_one(
                        {"_id": mismatch["mongo_doc_id"]},
                        {"$set": {"employee_id": mismatch["correct_id"]}},
                    )

                    if result.modified_count > 0:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  ✓ Fixed {mismatch['employee'].get_full_name()}: "
                                f"{mismatch['mongo_id']} → {mismatch['correct_id']}"
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.ERROR(
                                f"  ✗ Failed to fix {mismatch['employee'].get_full_name()}"
                            )
                        )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"  ✗ Error fixing {mismatch['employee'].get_full_name()}: {e}"
                        )
                    )

        elif mismatches and not fix_mode:
            self.stdout.write(
                self.style.WARNING("\nRun with --fix flag to correct these mismatches")
            )
