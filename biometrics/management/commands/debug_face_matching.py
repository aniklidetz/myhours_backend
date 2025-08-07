import logging

import numpy as np

from django.core.management.base import BaseCommand

from biometrics.services.face_processor import face_processor
from biometrics.services.mongodb_service import mongodb_service

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Debug face matching process with different tolerance levels"

    def handle(self, *args, **options):
        # Enable detailed logging
        logging.basicConfig(level=logging.DEBUG)

        self.stdout.write("🔍 Debugging face matching process...")

        # Get all active embeddings
        all_embeddings = mongodb_service.get_all_active_embeddings()
        self.stdout.write(f"Found {len(all_embeddings)} employees with embeddings:")

        for emp_id, embeddings in all_embeddings:
            self.stdout.write(f"  - Employee {emp_id}: {len(embeddings)} embeddings")

        if len(all_embeddings) < 2:
            self.stdout.write(
                "❌ Need at least 2 employees with embeddings for testing"
            )
            return

        # Test with different tolerance levels
        tolerance_levels = [0.3, 0.4, 0.5, 0.6, 0.7]

        # Get embeddings from first two employees
        emp1_id, emp1_embeddings = all_embeddings[0]
        emp2_id, emp2_embeddings = all_embeddings[1]

        self.stdout.write(
            f"\n🧪 Testing matching between Employee {emp1_id} and Employee {emp2_id}"
        )

        # Use first embedding from employee 1
        if emp1_embeddings and "vector" in emp1_embeddings[0]:
            test_encoding = np.array(emp1_embeddings[0]["vector"])

            self.stdout.write(f"\n📊 Testing different tolerance levels:")
            self.stdout.write(
                "Tolerance | Match Emp1 | Distance Emp1 | Match Emp2 | Distance Emp2"
            )
            self.stdout.write("-" * 70)

            for tolerance in tolerance_levels:
                # Update processor tolerance
                face_processor.tolerance = tolerance

                # Test against employee 1 (should match)
                emp1_known = [
                    np.array(emb["vector"])
                    for emb in emp1_embeddings
                    if "vector" in emb
                ]
                match1, conf1 = face_processor.compare_faces(test_encoding, emp1_known)
                distance1 = 1 - conf1

                # Test against employee 2 (should not match)
                emp2_known = [
                    np.array(emb["vector"])
                    for emb in emp2_embeddings
                    if "vector" in emb
                ]
                match2, conf2 = face_processor.compare_faces(test_encoding, emp2_known)
                distance2 = 1 - conf2

                self.stdout.write(
                    f"{tolerance:>9.1f} | {match1:>10} | {distance1:>13.3f} | {match2:>10} | {distance2:>13.3f}"
                )

            # Reset to default tolerance
            face_processor.tolerance = 0.4

            # Test full matching process
            self.stdout.write(
                f"\n🎯 Testing full matching process with default tolerance (0.4):"
            )

            # Create a test base64 image (mock)
            # In reality, this would be the captured face image
            test_result = {
                "success": True,
                "encoding": test_encoding.tolist(),
                "quality_check": {"quality_score": 0.95, "passed": True},
            }

            # Simulate find_matching_employee process
            best_match_employee_id = None
            best_confidence = 0.0
            all_matches = []

            for employee_id, employee_embeddings in all_embeddings:
                known_encodings = []
                for embedding in employee_embeddings:
                    if "vector" in embedding:
                        known_encodings.append(np.array(embedding["vector"]))

                if known_encodings:
                    is_match, confidence = face_processor.compare_faces(
                        test_encoding, known_encodings
                    )
                    all_matches.append((employee_id, confidence, is_match))

                    if is_match and confidence > best_confidence:
                        best_match_employee_id = employee_id
                        best_confidence = confidence

            # Sort by confidence
            all_matches.sort(key=lambda x: x[1], reverse=True)

            self.stdout.write("Results (sorted by confidence):")
            for emp_id, conf, match in all_matches:
                status = "✅ MATCH" if match else "❌ NO MATCH"
                self.stdout.write(
                    f"  Employee {emp_id}: confidence={conf:.3f} - {status}"
                )

            if best_match_employee_id:
                self.stdout.write(
                    f"\n🏆 Best match: Employee {best_match_employee_id} (confidence: {best_confidence:.3f})"
                )
            else:
                self.stdout.write(f"\n❌ No match found above tolerance threshold")
        else:
            self.stdout.write("❌ No valid embeddings found for testing")
