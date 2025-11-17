import logging

import numpy as np

from django.core.management.base import BaseCommand

from biometrics.services.mongodb_repository import MongoBiometricRepository
from users.models import Employee

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Test biometric registration process"

    def add_arguments(self, parser):
        parser.add_argument(
            "--employee-id",
            type=int,
            default=1,
            help="Employee ID to test with",
        )

    def handle(self, *args, **options):
        employee_id = options["employee_id"]

        # Enable detailed logging
        logging.basicConfig(level=logging.DEBUG)

        self.stdout.write("Testing biometric registration process...")

        try:
            # Get employee
            employee = Employee.objects.get(id=employee_id)
            self.stdout.write(
                f"Employee: {employee.get_full_name()} (ID: {employee.id})"
            )

            # Initialize MongoDB service
            mongodb_service = MongoBiometricRepository()

            if mongodb_service.collection is None:
                self.stdout.write(self.style.ERROR("MongoDB not available"))
                return

            # Create test embeddings
            test_embeddings = [
                {
                    "vector": np.random.rand(128).tolist(),
                    "quality_score": 0.95,
                    "angle": "frontal",
                    "created_at": None,
                }
            ]

            self.stdout.write("Saving test embeddings to MongoDB...")

            # Save embeddings
            mongodb_id = mongodb_service.save_face_embeddings(
                employee_id, test_embeddings
            )

            if mongodb_id:
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Saved to MongoDB with ID: {mongodb_id}")
                )

                # Verify
                saved_embeddings = mongodb_service.get_face_embeddings(employee_id)
                if saved_embeddings:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Verified: {len(saved_embeddings)} embeddings saved"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            "✗ Verification failed: Could not retrieve embeddings"
                        )
                    )

                # Check active embeddings
                all_active = mongodb_service.get_all_active_embeddings()
                self.stdout.write(f"Active embeddings in system: {len(all_active)}")
                for emp_id, embs in all_active:
                    self.stdout.write(f"  Employee {emp_id}: {len(embs)} embeddings")

            else:
                self.stdout.write(self.style.ERROR("✗ Failed to save to MongoDB"))

        except Employee.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Employee {employee_id} not found"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {e}"))
