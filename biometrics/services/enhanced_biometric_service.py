"""
Enhanced Biometric Service with MongoDB First pattern and fail-safe logic
"""

import logging
from typing import Dict, List, Optional, Tuple
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from users.models import Employee
from biometrics.models import BiometricProfile
from biometrics.services.mongodb_repository import MongoBiometricRepository

logger = logging.getLogger("biometrics")


class BiometricServiceError(Exception):
    """Custom exception for biometric service errors"""

    pass


class CriticalBiometricError(BiometricServiceError):
    """Critical errors that require immediate attention"""

    pass


class EnhancedBiometricService:
    """
    Enhanced biometric service with MongoDB First pattern

    Architecture:
    - MongoDB: Single source of truth for biometric data
    - PostgreSQL: Status indicator and metadata cache
    - Fail-safe: Critical error logging for monitoring
    - Audit: Consistency checking and auto-repair commands
    """

    def __init__(self):
        self.mongo_repo = MongoBiometricRepository()

    def register_biometric(
        self, employee_id: int, face_encodings: List[Dict]
    ) -> BiometricProfile:
        """
        Register biometric data with fail-safe logic

        Args:
            employee_id: Employee ID
            face_encodings: List of face encoding dictionaries

        Returns:
            BiometricProfile instance

        Raises:
            ValidationError: Invalid employee_id
            CriticalBiometricError: MongoDB operation failed
        """
        logger.info(f"🔧 Starting biometric registration for employee {employee_id}")

        # Use atomic transaction for consistent state
        with transaction.atomic():
            # 1. Validate employee with row-level locking (prevents race conditions)
            try:
                employee = Employee.objects.select_for_update().get(
                    id=employee_id, is_active=True
                )
                logger.debug(
                    f"✅ Employee validation passed: {employee.get_full_name()}"
                )
            except Employee.DoesNotExist:
                error_msg = f"Employee {employee_id} not found or inactive"
                logger.error(f"❌ {error_msg}")
                raise ValidationError(error_msg)

            # 2. MongoDB operation (source of truth)
            try:
                mongodb_result = self.mongo_repo.save_face_embeddings(
                    employee_id=employee_id, embeddings=face_encodings
                )

                if not mongodb_result:
                    # CRITICAL: MongoDB failed silently
                    logger.critical(
                        f"🚨 CRITICAL: MongoDB failure during registration: "
                        f"employee_id={employee_id}, employee_name={employee.get_full_name()}"
                    )
                    raise CriticalBiometricError(
                        f"MongoDB operation failed for employee {employee_id}. "
                        "This requires immediate attention from DevOps team."
                    )

                logger.info(f"✅ MongoDB save successful: document_id={mongodb_result}")

            except Exception as e:
                if isinstance(e, CriticalBiometricError):
                    raise  # Re-raise critical errors

                # Wrap other MongoDB errors as critical
                logger.critical(
                    f"🚨 CRITICAL: MongoDB exception during registration: "
                    f"employee_id={employee_id}, error={str(e)}"
                )
                raise CriticalBiometricError(
                    f"MongoDB operation exception for employee {employee_id}: {str(e)}"
                ) from e

            # 3. PostgreSQL status update (idempotent)
            try:
                profile, created = BiometricProfile.objects.update_or_create(
                    employee_id=employee_id,
                    defaults={
                        "embeddings_count": len(face_encodings),
                        "mongodb_id": mongodb_result,
                        "is_active": True,
                        "last_updated": timezone.now(),
                    },
                )

                action = "created" if created else "updated"
                logger.info(
                    f"✅ PostgreSQL profile {action} for employee {employee_id}"
                )

            except Exception as e:
                # PostgreSQL failure is not critical - MongoDB data is safe
                logger.error(
                    f"⚠️ PostgreSQL update failed for employee {employee_id}: {str(e)}. "
                    f"MongoDB data is safe (document_id={mongodb_result})"
                )
                # Continue - we can fix PostgreSQL later via audit

        # 4. Success logging for monitoring
        logger.info(
            f"🎉 Biometric registration completed: employee_id={employee_id}, "
            f"embeddings_count={len(face_encodings)}, mongodb_id={mongodb_result}"
        )

        return profile if "profile" in locals() else None

    def verify_biometric(
        self, face_encoding: List[float]
    ) -> Optional[Tuple[int, float]]:
        """
        Verify biometric data against all registered employees

        Args:
            face_encoding: Face encoding vector

        Returns:
            Tuple of (employee_id, confidence_score) if match found, None otherwise
        """
        logger.debug("🔍 Starting biometric verification")

        try:
            result = self.mongo_repo.find_matching_employee(face_encoding)
            if result:
                employee_id, confidence = result
                logger.info(
                    f"✅ Biometric match found: employee_id={employee_id}, confidence={confidence:.3f}"
                )
            else:
                logger.debug("❌ No biometric match found")
            return result

        except Exception as e:
            logger.error(f"❌ Biometric verification failed: {str(e)}")
            return None

    def delete_biometric(self, employee_id: int) -> bool:
        """
        Delete biometric data from both databases

        Args:
            employee_id: Employee ID

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"🗑️ Deleting biometric data for employee {employee_id}")

        success = True

        # 1. Delete from MongoDB (source of truth)
        try:
            mongo_deleted = self.mongo_repo.delete_embeddings(employee_id)
            if mongo_deleted:
                logger.info(
                    f"✅ MongoDB deletion successful for employee {employee_id}"
                )
            else:
                logger.warning(f"⚠️ No MongoDB data found for employee {employee_id}")
        except Exception as e:
            logger.error(
                f"❌ MongoDB deletion failed for employee {employee_id}: {str(e)}"
            )
            success = False

        # 2. Update PostgreSQL status (even if MongoDB failed)
        try:
            updated = BiometricProfile.objects.filter(employee_id=employee_id).update(
                is_active=False, embeddings_count=0, last_updated=timezone.now()
            )
            if updated:
                logger.info(f"✅ PostgreSQL status updated for employee {employee_id}")
            else:
                logger.warning(
                    f"⚠️ No PostgreSQL profile found for employee {employee_id}"
                )
        except Exception as e:
            logger.error(
                f"❌ PostgreSQL update failed for employee {employee_id}: {str(e)}"
            )
            success = False

        return success

    def audit_consistency(self) -> Dict:
        """
        Audit consistency between MongoDB and PostgreSQL with auto-repair commands

        Returns:
            Dictionary with inconsistencies and fix commands
        """
        logger.info("🔍 Starting consistency audit between MongoDB and PostgreSQL")

        try:
            # Get active profiles from PostgreSQL
            pg_profiles = BiometricProfile.objects.filter(
                is_active=True
            ).select_related("employee")
            pg_employee_ids = set(profile.employee_id for profile in pg_profiles)

            # Get all employee IDs from MongoDB
            mongo_employee_ids = set(self.mongo_repo.get_all_employee_ids())

            # Find inconsistencies
            orphaned_mongo = (
                mongo_employee_ids - pg_employee_ids
            )  # In MongoDB but not in PostgreSQL
            orphaned_pg = (
                pg_employee_ids - mongo_employee_ids
            )  # In PostgreSQL but not in MongoDB

            # Generate fix commands
            fix_commands = []

            # Commands to fix orphaned MongoDB data
            for employee_id in orphaned_mongo:
                # Check if employee exists in system
                if Employee.objects.filter(id=employee_id, is_active=True).exists():
                    # Employee exists, create PostgreSQL profile
                    fix_commands.append(
                        f"# Create missing PostgreSQL profile for employee {employee_id}\n"
                        f"BiometricProfile.objects.update_or_create("
                        f"employee_id={employee_id}, "
                        f"defaults={{'is_active': True, 'embeddings_count': 1}})"
                    )
                else:
                    # Employee doesn't exist, remove MongoDB data
                    fix_commands.append(
                        f"# Remove orphaned MongoDB data for non-existent employee {employee_id}\n"
                        f"mongo_repo.delete_embeddings({employee_id})"
                    )

            # Commands to fix orphaned PostgreSQL data
            for employee_id in orphaned_pg:
                fix_commands.append(
                    f"# Fix PostgreSQL profile for employee {employee_id} (no MongoDB data)\n"
                    f"BiometricProfile.objects.filter(employee_id={employee_id})"
                    f".update(is_active=False, embeddings_count=0)"
                )

            # Detailed employee info for orphaned PostgreSQL records
            orphaned_pg_details = []
            for profile in pg_profiles:
                if profile.employee_id in orphaned_pg:
                    orphaned_pg_details.append(
                        {
                            "employee_id": profile.employee_id,
                            "employee_name": profile.employee.get_full_name(),
                            "profile_created": profile.created_at,
                            "last_updated": profile.last_updated,
                        }
                    )

            audit_result = {
                "timestamp": timezone.now().isoformat(),
                "total_pg_profiles": len(pg_employee_ids),
                "total_mongo_records": len(mongo_employee_ids),
                "orphaned_mongo_count": len(orphaned_mongo),
                "orphaned_pg_count": len(orphaned_pg),
                "orphaned_mongo_ids": list(orphaned_mongo),
                "orphaned_pg_ids": list(orphaned_pg),
                "orphaned_pg_details": orphaned_pg_details,
                "is_consistent": len(orphaned_mongo) == 0 and len(orphaned_pg) == 0,
                "fix_commands": fix_commands,
            }

            # Log results
            if audit_result["is_consistent"]:
                logger.info(
                    "✅ Biometric data is consistent between MongoDB and PostgreSQL"
                )
            else:
                logger.warning(
                    f"⚠️ Inconsistencies detected: "
                    f"orphaned_mongo={len(orphaned_mongo)}, "
                    f"orphaned_pg={len(orphaned_pg)}"
                )
                logger.info(f"🔧 Generated {len(fix_commands)} fix commands")

            return audit_result

        except Exception as e:
            logger.error(f"❌ Consistency audit failed: {str(e)}")
            return {
                "timestamp": timezone.now().isoformat(),
                "is_consistent": False,
                "error": str(e),
                "fix_commands": [],
            }

    def get_employee_biometric_status(self, employee_id: int) -> Dict:
        """
        Get detailed biometric status for an employee

        Args:
            employee_id: Employee ID

        Returns:
            Dictionary with biometric status details
        """
        try:
            # Check PostgreSQL
            try:
                profile = BiometricProfile.objects.get(employee_id=employee_id)
                pg_status = {
                    "exists": True,
                    "is_active": profile.is_active,
                    "embeddings_count": profile.embeddings_count,
                    "last_updated": (
                        profile.last_updated.isoformat()
                        if profile.last_updated
                        else None
                    ),
                    "mongodb_id": profile.mongodb_id,
                }
            except BiometricProfile.DoesNotExist:
                pg_status = {"exists": False}

            # Check MongoDB
            mongo_embeddings = self.mongo_repo.get_face_embeddings(employee_id)
            mongo_status = {
                "exists": mongo_embeddings is not None,
                "embeddings_count": len(mongo_embeddings) if mongo_embeddings else 0,
            }

            # Determine overall status
            is_consistent = pg_status.get("exists", False) == mongo_status[
                "exists"
            ] and (
                not pg_status.get("exists", False)
                or pg_status.get("is_active", False)
                == (mongo_status["embeddings_count"] > 0)
            )

            return {
                "employee_id": employee_id,
                "is_consistent": is_consistent,
                "postgresql": pg_status,
                "mongodb": mongo_status,
                "timestamp": timezone.now().isoformat(),
            }

        except Exception as e:
            logger.error(
                f"❌ Failed to get biometric status for employee {employee_id}: {str(e)}"
            )
            return {
                "employee_id": employee_id,
                "is_consistent": False,
                "error": str(e),
                "timestamp": timezone.now().isoformat(),
            }


# Global instance
enhanced_biometric_service = EnhancedBiometricService()
