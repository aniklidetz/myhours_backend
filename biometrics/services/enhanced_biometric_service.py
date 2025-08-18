"""
Enhanced Biometric Service with MongoDB First pattern and fail-safe logic
"""

import logging
from typing import Dict, List, Optional, Tuple

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from biometrics.models import BiometricProfile
from biometrics.services.mongodb_repository import MongoBiometricRepository
from core.logging_utils import err_tag, safe_biometric_subject, safe_extra
from users.models import Employee

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
        from core.logging_utils import safe_biometric_subject, safe_extra

        logger.info(
            "🔧 Starting biometric registration",
            extra=safe_extra(
                {
                    "subject": safe_biometric_subject({"id": employee_id}, "employee"),
                    "operation": "registration",
                },
                allow={"operation"},
            ),
        )  # lgtm[py/clear-text-logging-sensitive-data]

        # Use atomic transaction for consistent state
        with transaction.atomic():
            # 1. Validate employee with row-level locking (prevents race conditions)
            try:
                employee = Employee.objects.select_for_update().get(
                    id=employee_id, is_active=True
                )
                from django.conf import settings

                if settings.DEBUG:
                    logger.debug(
                        "✅ Employee validation passed",
                        extra=safe_extra(
                            {
                                "subject": safe_biometric_subject(employee, "employee"),
                                "validation": "passed",
                            },
                            allow={"validation"},
                        ),
                    )  # lgtm[py/clear-text-logging-sensitive-data]
            except Employee.DoesNotExist:
                error_msg = "Employee not found or inactive"
                logger.error(
                    f"❌ {error_msg}",
                    extra=safe_extra(
                        {
                            "subject": safe_biometric_subject(
                                {"id": employee_id}, "employee"
                            ),
                            "error": "not_found_or_inactive",
                        },
                        allow={"error"},
                    ),
                )  # lgtm[py/clear-text-logging-sensitive-data]
                raise ValidationError(error_msg)

            # 2. MongoDB operation (source of truth)
            try:
                mongodb_result = self.mongo_repo.save_face_embeddings(
                    employee_id=employee_id, embeddings=face_encodings
                )

                if not mongodb_result:
                    # CRITICAL: MongoDB failed silently
                    logger.critical(
                        "🚨 CRITICAL: MongoDB failure during registration",
                        extra=safe_extra(
                            {
                                "subject": safe_biometric_subject(employee, "employee"),
                                "operation": "mongodb_save",
                                "result": "critical_failure",
                            },
                            allow={"operation", "result"},
                        ),
                    )  # lgtm[py/clear-text-logging-sensitive-data]
                    raise CriticalBiometricError(
                        "MongoDB operation failed. "
                        "This requires immediate attention from DevOps team."
                    )

                logger.info(
                    "✅ MongoDB save successful",
                    extra=safe_extra(
                        {
                            "operation": "mongodb_save",
                            "result": "success",
                            "has_document_id": bool(mongodb_result),
                        },
                        allow={"operation", "result", "has_document_id"},
                    ),
                )  # lgtm[py/clear-text-logging-sensitive-data]

            except Exception as e:
                if isinstance(e, CriticalBiometricError):
                    raise  # Re-raise critical errors

                # Wrap other MongoDB errors as critical
                from core.logging_utils import err_tag

                logger.critical(
                    f"🚨 CRITICAL: MongoDB exception during registration: {err_tag(e)}",
                    extra=safe_extra(
                        {
                            "subject": safe_biometric_subject(
                                {"id": employee_id}, "employee"
                            ),
                            "operation": "mongodb_save",
                            "result": "critical_exception",
                        },
                        allow={"operation", "result"},
                    ),
                )  # lgtm[py/clear-text-logging-sensitive-data]
                raise CriticalBiometricError(
                    f"MongoDB operation exception: {err_tag(e)}"
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
                    f"✅ PostgreSQL profile {action}",
                    extra=safe_extra(
                        {
                            "subject": safe_biometric_subject(employee, "employee"),
                            "operation": "postgresql_profile",
                            "action": action,
                        },
                        allow={"operation", "action"},
                    ),
                )  # lgtm[py/clear-text-logging-sensitive-data]

            except Exception as e:
                # PostgreSQL failure is not critical - MongoDB data is safe
                from core.logging_utils import err_tag

                logger.error(
                    f"⚠️ PostgreSQL update failed: {err_tag(e)}. MongoDB data is safe",
                    extra=safe_extra(
                        {
                            "subject": safe_biometric_subject(
                                {"id": employee_id}, "employee"
                            ),
                            "operation": "postgresql_update",
                            "result": "failed",
                            "mongodb_safe": True,
                        },
                        allow={"operation", "result", "mongodb_safe"},
                    ),
                )  # lgtm[py/clear-text-logging-sensitive-data]
                # Continue - we can fix PostgreSQL later via audit

        # 4. Success logging for monitoring
        logger.info(
            "🎉 Biometric registration completed",
            extra=safe_extra(
                {
                    "subject": safe_biometric_subject({"id": employee_id}, "employee"),
                    "operation": "registration",
                    "result": "completed",
                    "embeddings_count": len(face_encodings),
                    "has_mongodb_id": bool(mongodb_result),
                },
                allow={"operation", "result", "embeddings_count", "has_mongodb_id"},
            ),
        )  # lgtm[py/clear-text-logging-sensitive-data]

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
        from django.conf import settings

        from core.logging_utils import safe_biometric_subject, safe_extra

        if settings.DEBUG:
            logger.debug(
                "🔍 Starting biometric verification",
                extra=safe_extra({"operation": "verification"}, allow={"operation"}),
            )  # lgtm[py/clear-text-logging-sensitive-data]

        try:
            result = self.mongo_repo.find_matching_employee(face_encoding)
            if result:
                employee_id, confidence = result
                logger.info(
                    "✅ Biometric match found",
                    extra=safe_extra(
                        {
                            "subject": safe_biometric_subject(
                                {"id": employee_id}, "employee"
                            ),
                            "operation": "verification",
                            "result": "match_found",
                            "confidence_level": (
                                "high"
                                if confidence >= 0.8
                                else "medium" if confidence >= 0.6 else "low"
                            ),
                        },
                        allow={"operation", "result", "confidence_level"},
                    ),
                )  # lgtm[py/clear-text-logging-sensitive-data]
            else:
                if settings.DEBUG:
                    logger.debug(
                        "❌ No biometric match found",
                        extra=safe_extra(
                            {"operation": "verification", "result": "no_match"},
                            allow={"operation", "result"},
                        ),
                    )  # lgtm[py/clear-text-logging-sensitive-data]
            return result

        except Exception as e:
            from core.logging_utils import err_tag

            logger.error("❌ Biometric verification failed", extra={"err": err_tag(e)})
            return None

    def delete_biometric(self, employee_id: int) -> bool:
        """
        Delete biometric data from both databases

        Args:
            employee_id: Employee ID

        Returns:
            True if successful, False otherwise
        """
        from core.logging_utils import safe_biometric_subject, safe_extra

        logger.info(
            "🗑️ Deleting biometric data",
            extra=safe_extra(
                {
                    "subject": safe_biometric_subject({"id": employee_id}, "employee"),
                    "operation": "deletion",
                },
                allow={"operation"},
            ),
        )  # lgtm[py/clear-text-logging-sensitive-data]

        success = True

        # 1. Delete from MongoDB (source of truth)
        try:
            mongo_deleted = self.mongo_repo.delete_embeddings(employee_id)
            if mongo_deleted:
                logger.info(
                    "✅ MongoDB deletion successful",
                    extra=safe_extra(
                        {
                            "subject": safe_biometric_subject(
                                {"id": employee_id}, "employee"
                            ),
                            "operation": "mongodb_deletion",
                            "result": "success",
                        },
                        allow={"operation", "result"},
                    ),
                )  # lgtm[py/clear-text-logging-sensitive-data]
            else:
                logger.warning(
                    "⚠️ No MongoDB data found",
                    extra=safe_extra(
                        {
                            "subject": safe_biometric_subject(
                                {"id": employee_id}, "employee"
                            ),
                            "operation": "mongodb_deletion",
                            "result": "no_data",
                        },
                        allow={"operation", "result"},
                    ),
                )  # lgtm[py/clear-text-logging-sensitive-data]
        except Exception as e:
            from core.logging_utils import err_tag

            logger.error(
                f"❌ MongoDB deletion failed: {err_tag(e)}",
                extra=safe_extra(
                    {
                        "subject": safe_biometric_subject(
                            {"id": employee_id}, "employee"
                        ),
                        "operation": "mongodb_deletion",
                        "result": "error",
                    },
                    allow={"operation", "result"},
                ),
            )  # lgtm[py/clear-text-logging-sensitive-data]
            success = False

        # 2. Update PostgreSQL status (even if MongoDB failed)
        try:
            updated = BiometricProfile.objects.filter(employee_id=employee_id).update(
                is_active=False, embeddings_count=0, last_updated=timezone.now()
            )
            if updated:
                logger.info(
                    "✅ PostgreSQL status updated",
                    extra=safe_extra(
                        {
                            "subject": safe_biometric_subject(
                                {"id": employee_id}, "employee"
                            ),
                            "operation": "postgresql_update",
                            "result": "success",
                        },
                        allow={"operation", "result"},
                    ),
                )  # lgtm[py/clear-text-logging-sensitive-data]
            else:
                logger.warning(
                    "⚠️ No PostgreSQL profile found",
                    extra=safe_extra(
                        {
                            "subject": safe_biometric_subject(
                                {"id": employee_id}, "employee"
                            ),
                            "operation": "postgresql_update",
                            "result": "not_found",
                        },
                        allow={"operation", "result"},
                    ),
                )  # lgtm[py/clear-text-logging-sensitive-data]
        except Exception as e:
            from core.logging_utils import err_tag

            logger.error(
                f"❌ PostgreSQL update failed: {err_tag(e)}",
                extra=safe_extra(
                    {
                        "subject": safe_biometric_subject(
                            {"id": employee_id}, "employee"
                        ),
                        "operation": "postgresql_update",
                        "result": "error",
                    },
                    allow={"operation", "result"},
                ),
            )  # lgtm[py/clear-text-logging-sensitive-data]
            success = False

        return success

    def audit_consistency(self) -> Dict:
        """
        Audit consistency between MongoDB and PostgreSQL with auto-repair commands

        Returns:
            Dictionary with inconsistencies and fix commands
        """
        from core.logging_utils import safe_extra

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
                "orphaned_mongo_count": len(orphaned_mongo),
                "orphaned_pg_count": len(orphaned_pg),
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
                    "⚠️ Inconsistencies detected",
                    extra=safe_extra(
                        {
                            "operation": "audit",
                            "result": "inconsistent",
                            "orphaned_mongo_count": len(orphaned_mongo),
                            "orphaned_pg_count": len(orphaned_pg),
                        },
                        allow={
                            "operation",
                            "result",
                            "orphaned_mongo_count",
                            "orphaned_pg_count",
                        },
                    ),
                )  # lgtm[py/clear-text-logging-sensitive-data]
                logger.info(
                    "🔧 Generated fix commands",
                    extra=safe_extra(
                        {"operation": "audit", "fix_commands_count": len(fix_commands)},
                        allow={"operation", "fix_commands_count"},
                    ),
                )  # lgtm[py/clear-text-logging-sensitive-data]

            return audit_result

        except Exception as e:
            from core.logging_utils import err_tag

            logger.error("❌ Consistency audit failed", extra={"err": err_tag(e)})
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
        from core.logging_utils import err_tag, safe_biometric_subject, safe_extra

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
                f"❌ Failed to get biometric status: {err_tag(e)}",
                extra=safe_extra(
                    {
                        "subject": safe_biometric_subject(
                            {"id": employee_id}, "employee"
                        ),
                        "operation": "get_status",
                        "result": "error",
                    },
                    allow={"operation", "result"},
                ),
            )  # lgtm[py/clear-text-logging-sensitive-data]
            return {
                "employee_id": employee_id,
                "is_consistent": False,
                "error": err_tag(e),
                "timestamp": timezone.now().isoformat(),
            }


# Global instance with lazy loading to prevent MongoDB connections during test imports
_enhanced_biometric_service = None


def get_enhanced_biometric_service():
    """Get the global enhanced biometric service instance with lazy initialization"""
    global _enhanced_biometric_service
    if _enhanced_biometric_service is None:
        _enhanced_biometric_service = EnhancedBiometricService()
    return _enhanced_biometric_service


# Backward compatibility - maintain the same interface
class _LazyBiometricServiceProxy:
    """Proxy that delays biometric service initialization until actually needed"""

    def __getattr__(self, name):
        return getattr(get_enhanced_biometric_service(), name)


enhanced_biometric_service = _LazyBiometricServiceProxy()
