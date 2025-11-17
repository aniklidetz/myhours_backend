"""
Management command to migrate all legacy biometric collections to face_embeddings.

This command consolidates data from THREE collections into one:
1. face_encodings (BiometricService legacy)
2. faces (MongoDBService conditional legacy)
3. face_embeddings (modern - target)

Critical: Handles the mongodb_service.py collection selection problem by
ensuring ALL data ends up in face_embeddings regardless of source.

Usage:
    # Dry run (recommended first)
    python manage.py migrate_biometric_collections --dry-run

    # Full migration with backup
    python manage.py migrate_biometric_collections --backup

    # Merge mode (handles duplicates)
    python manage.py migrate_biometric_collections --merge

    # Rollback to backup
    python manage.py migrate_biometric_collections --rollback backup_file.json
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from bson import ObjectId
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.logging_utils import safe_id


class Command(BaseCommand):
    help = (
        "Migrate all biometric collections (face_encodings, faces) to face_embeddings"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate migration without making changes",
        )
        parser.add_argument(
            "--backup",
            action="store_true",
            help="Create backup before migration",
        )
        parser.add_argument(
            "--backup-dir",
            type=str,
            default="./biometric_backups",
            help="Directory for backup files",
        )
        parser.add_argument(
            "--merge",
            action="store_true",
            help="Merge mode - handle duplicate employee_ids intelligently",
        )
        parser.add_argument(
            "--rollback",
            type=str,
            help="Rollback from backup file (path to backup JSON)",
        )
        parser.add_argument(
            "--delete-legacy",
            action="store_true",
            help="Delete legacy collections after successful migration",
        )

    def handle(self, *args, **options):
        """Execute the migration"""
        self.dry_run = options.get("dry_run", False)
        self.backup_enabled = options.get("backup", False)
        self.backup_dir = Path(options.get("backup_dir"))
        self.merge_mode = options.get("merge", False)
        self.rollback_file = options.get("rollback")
        self.delete_legacy = options.get("delete_legacy", False)

        try:
            # Get MongoDB database
            self.db = settings.MONGO_DB
            if self.db is None:
                raise CommandError("MongoDB database not available")

            # Handle rollback
            if self.rollback_file:
                return self._execute_rollback()

            # Print header
            self._print_header()

            # Step 1: Audit current state
            self.stdout.write("\n" + "=" * 80)
            self.stdout.write("STEP 1: Auditing current state")
            self.stdout.write("=" * 80 + "\n")

            audit_results = self._audit_collections()
            self._print_audit_summary(audit_results)

            # Check if migration is needed
            if not self._migration_needed(audit_results):
                self.stdout.write(
                    self.style.SUCCESS(
                        "\n✅ No migration needed - all data is already in face_embeddings"
                    )
                )
                return

            # Step 2: Create backup if requested
            backup_file = None
            if self.backup_enabled and not self.dry_run:
                self.stdout.write("\n" + "=" * 80)
                self.stdout.write("STEP 2: Creating backup")
                self.stdout.write("=" * 80 + "\n")
                backup_file = self._create_backup(audit_results)

            # Step 3: Perform migration
            self.stdout.write("\n" + "=" * 80)
            mode_text = "DRY RUN" if self.dry_run else "MIGRATION"
            merge_text = " (MERGE MODE)" if self.merge_mode else ""
            self.stdout.write(f"STEP 3: {mode_text}{merge_text}")
            self.stdout.write("=" * 80 + "\n")

            migration_results = self._perform_migration(audit_results)

            # Step 4: Verification
            self.stdout.write("\n" + "=" * 80)
            self.stdout.write("STEP 4: Verification")
            self.stdout.write("=" * 80 + "\n")

            if not self.dry_run:
                self._verify_migration(audit_results, migration_results)

            # Step 5: Cleanup (if requested)
            if self.delete_legacy and not self.dry_run:
                self.stdout.write("\n" + "=" * 80)
                self.stdout.write("STEP 5: Cleanup")
                self.stdout.write("=" * 80 + "\n")
                self._cleanup_legacy_collections(migration_results)

            # Final summary
            self._print_final_summary(migration_results, backup_file)

        except Exception as e:
            raise CommandError(f"Migration failed: {str(e)}")

    def _print_header(self):
        """Print migration header"""
        self.stdout.write(self.style.SUCCESS("\n" + "=" * 80))
        self.stdout.write(
            self.style.SUCCESS("BIOMETRIC COLLECTIONS MIGRATION - Phase 2")
        )
        self.stdout.write(self.style.SUCCESS("=" * 80))

        if self.dry_run:
            self.stdout.write(
                self.style.WARNING("\n⚠️  DRY RUN MODE - No changes will be made\n")
            )
        elif self.merge_mode:
            self.stdout.write(
                self.style.WARNING(
                    "\n⚠️  MERGE MODE - Will handle duplicate employee_ids\n"
                )
            )

    def _audit_collections(self) -> Dict:
        """Audit all three collections"""
        results = {}

        collections_to_check = ["face_encodings", "faces", "face_embeddings"]

        for coll_name in collections_to_check:
            if coll_name in self.db.list_collection_names():
                collection = self.db[coll_name]
                count = collection.count_documents({})

                # Get employee IDs
                employee_ids = set()
                if count > 0:
                    docs = collection.find({}, {"employee_id": 1})
                    employee_ids = {
                        doc["employee_id"] for doc in docs if "employee_id" in doc
                    }

                results[coll_name] = {
                    "exists": True,
                    "count": count,
                    "employee_ids": employee_ids,
                    "collection": collection,
                }
            else:
                results[coll_name] = {
                    "exists": False,
                    "count": 0,
                    "employee_ids": set(),
                    "collection": None,
                }

        return results

    def _print_audit_summary(self, audit: Dict):
        """Print audit summary"""
        self.stdout.write(
            f"{'Collection':<20} {'Exists':<8} {'Documents':<12} {'Employees'}"
        )
        self.stdout.write("─" * 80)

        for name in ["face_encodings", "faces", "face_embeddings"]:
            data = audit[name]
            exists = "✓" if data["exists"] else "✗"
            count = data["count"]
            emp_count = len(data["employee_ids"])

            self.stdout.write(f"{name:<20} {exists:<8} {count:<12} {emp_count}")

        # Check for overlaps
        face_enc_ids = audit["face_encodings"]["employee_ids"]
        faces_ids = audit["faces"]["employee_ids"]
        face_emb_ids = audit["face_embeddings"]["employee_ids"]

        overlap_enc_faces = face_enc_ids & faces_ids
        overlap_enc_emb = face_enc_ids & face_emb_ids
        overlap_faces_emb = faces_ids & face_emb_ids

        if overlap_enc_faces or overlap_enc_emb or overlap_faces_emb:
            self.stdout.write("\n⚠️  Overlapping employee IDs detected:")
            if overlap_enc_faces:
                self.stdout.write(
                    f"   face_encodings ∩ faces: {len(overlap_enc_faces)} employees"
                )
            if overlap_enc_emb:
                self.stdout.write(
                    f"   face_encodings ∩ face_embeddings: {len(overlap_enc_emb)} employees"
                )
            if overlap_faces_emb:
                self.stdout.write(
                    f"   faces ∩ face_embeddings: {len(overlap_faces_emb)} employees"
                )

            if self.merge_mode:
                self.stdout.write(
                    "\n✓ MERGE MODE enabled - will handle duplicates intelligently"
                )
            else:
                self.stdout.write(
                    "\n⚠️  Consider using --merge flag to handle duplicates"
                )

    def _migration_needed(self, audit: Dict) -> bool:
        """Check if migration is needed"""
        has_legacy_data = (
            audit["face_encodings"]["count"] > 0 or audit["faces"]["count"] > 0
        )
        return has_legacy_data

    def _create_backup(self, audit: Dict) -> Optional[str]:
        """Create backup of all collections"""
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"biometric_backup_{timestamp}.json"

        backup_data = {
            "timestamp": timestamp,
            "collections": {},
        }

        for coll_name in ["face_encodings", "faces", "face_embeddings"]:
            if audit[coll_name]["exists"] and audit[coll_name]["count"] > 0:
                collection = audit[coll_name]["collection"]
                documents = list(collection.find({}))

                # Convert ObjectId and numpy arrays to JSON-serializable format
                for doc in documents:
                    doc["_id"] = str(doc["_id"])
                    # Handle various array fields
                    for key in [
                        "face_encoding",
                        "encodings",
                        "embeddings",
                    ]:
                        if key in doc:
                            doc[key] = self._serialize_array_field(doc[key])

                backup_data["collections"][coll_name] = {
                    "count": len(documents),
                    "documents": documents,
                }

                self.stdout.write(
                    f"✓ Backed up {coll_name}: {len(documents)} documents"
                )

        # Save backup
        with open(backup_file, "w") as f:
            json.dump(backup_data, f, indent=2, default=str)

        self.stdout.write(self.style.SUCCESS(f"\n✅ Backup created: {backup_file}"))
        return str(backup_file)

    def _serialize_array_field(self, value):
        """Serialize array fields for JSON"""
        if isinstance(value, np.ndarray):
            return value.tolist()
        elif isinstance(value, list):
            # Handle nested structures
            return [
                (
                    self._serialize_array_field(item)
                    if isinstance(item, (dict, list, np.ndarray))
                    else item
                )
                for item in value
            ]
        elif isinstance(value, dict):
            return {k: self._serialize_array_field(v) for k, v in value.items()}
        return value

    def _perform_migration(self, audit: Dict) -> Dict:
        """Perform the actual migration"""
        results = {
            "migrated_from_face_encodings": 0,
            "migrated_from_faces": 0,
            "skipped_duplicates": 0,
            "merged_duplicates": 0,
            "errors": [],
        }

        target_collection = audit["face_embeddings"]["collection"]
        if target_collection is None:
            target_collection = self.db["face_embeddings"]

        # Track processed employee IDs
        processed_employee_ids = set(audit["face_embeddings"]["employee_ids"])

        # Migrate from face_encodings
        if audit["face_encodings"]["count"] > 0:
            self.stdout.write("\n📦 Migrating from face_encodings...")
            count = self._migrate_from_face_encodings(
                audit["face_encodings"]["collection"],
                target_collection,
                processed_employee_ids,
                results,
            )
            results["migrated_from_face_encodings"] = count

        # Migrate from faces
        if audit["faces"]["count"] > 0:
            self.stdout.write("\n📦 Migrating from faces...")
            count = self._migrate_from_faces(
                audit["faces"]["collection"],
                target_collection,
                processed_employee_ids,
                results,
            )
            results["migrated_from_faces"] = count

        return results

    def _migrate_from_face_encodings(
        self,
        source_collection,
        target_collection,
        processed_ids: set,
        results: Dict,
    ) -> int:
        """Migrate from face_encodings collection (BiometricService legacy)"""
        migrated_count = 0

        for doc in source_collection.find({}):
            employee_id = doc.get("employee_id")
            if not employee_id:
                results["errors"].append(
                    f"face_encodings document missing employee_id: {doc.get('_id')}"
                )
                continue

            # Check for duplicate
            if employee_id in processed_ids:
                if self.merge_mode:
                    self._handle_duplicate_merge(
                        employee_id, doc, target_collection, "face_encodings", results
                    )
                else:
                    results["skipped_duplicates"] += 1
                    self.stdout.write(
                        f"  ⚠️  Skipped duplicate employee_id: {safe_id(employee_id)}"
                    )
                continue

            # Convert legacy schema to modern schema
            modern_doc = self._convert_face_encodings_to_embeddings(doc)

            if not self.dry_run:
                try:
                    target_collection.insert_one(modern_doc)
                    processed_ids.add(employee_id)
                    migrated_count += 1
                except Exception as e:
                    results["errors"].append(
                        f"Failed to migrate employee {employee_id}: {str(e)}"
                    )
            else:
                migrated_count += 1
                processed_ids.add(employee_id)

            self.stdout.write(
                f"  ✓ Migrated employee {safe_id(employee_id)} from face_encodings"
            )

        return migrated_count

    def _migrate_from_faces(
        self,
        source_collection,
        target_collection,
        processed_ids: set,
        results: Dict,
    ) -> int:
        """Migrate from faces collection (MongoDBService conditional legacy)"""
        migrated_count = 0

        for doc in source_collection.find({}):
            employee_id = doc.get("employee_id")
            if not employee_id:
                results["errors"].append(
                    f"faces document missing employee_id: {doc.get('_id')}"
                )
                continue

            # Check for duplicate
            if employee_id in processed_ids:
                if self.merge_mode:
                    self._handle_duplicate_merge(
                        employee_id, doc, target_collection, "faces", results
                    )
                else:
                    results["skipped_duplicates"] += 1
                    self.stdout.write(
                        f"  ⚠️  Skipped duplicate employee_id: {safe_id(employee_id)}"
                    )
                continue

            # Convert faces schema to modern schema
            modern_doc = self._convert_faces_to_embeddings(doc)

            if not self.dry_run:
                try:
                    target_collection.insert_one(modern_doc)
                    processed_ids.add(employee_id)
                    migrated_count += 1
                except Exception as e:
                    results["errors"].append(
                        f"Failed to migrate employee {employee_id}: {str(e)}"
                    )
            else:
                migrated_count += 1
                processed_ids.add(employee_id)

            self.stdout.write(
                f"  ✓ Migrated employee {safe_id(employee_id)} from faces"
            )

        return migrated_count

    def _convert_face_encodings_to_embeddings(self, old_doc: Dict) -> Dict:
        """
        Convert face_encodings schema to face_embeddings schema.

        Old schema (BiometricService):
        {
            "employee_id": int,
            "face_encoding": [128 floats],
            "created_at": datetime
        }

        New schema:
        {
            "employee_id": int,
            "embeddings": [{
                "vector": [128 floats],
                "quality_score": float,
                "created_at": datetime,
                "angle": str
            }],
            "metadata": {...},
            "is_active": bool
        }
        """
        face_encoding = old_doc.get("face_encoding")
        if not face_encoding:
            face_encoding = []

        # Convert single encoding to embeddings array
        embeddings = []
        if face_encoding:
            embeddings.append(
                {
                    "vector": (
                        face_encoding
                        if isinstance(face_encoding, list)
                        else face_encoding.tolist()
                    ),
                    "quality_score": 0.7,  # Default quality for legacy data
                    "created_at": old_doc.get("created_at", datetime.now()),
                    "angle": "frontal",  # Default angle
                }
            )

        return {
            "employee_id": old_doc["employee_id"],
            "embeddings": embeddings,
            "metadata": {
                "algorithm": "dlib_face_recognition_resnet_model_v1",
                "version": "1.0",
                "created_at": old_doc.get("created_at", datetime.now()),
                "last_updated": datetime.now(),
                "migrated_from": "face_encodings",
            },
            "is_active": True,
        }

    def _convert_faces_to_embeddings(self, old_doc: Dict) -> Dict:
        """
        Convert faces schema to face_embeddings schema.

        Handles multiple possible schemas in 'faces' collection.
        """
        # Try to detect schema
        if "encodings" in old_doc:
            # Array of encodings
            encodings = old_doc.get("encodings", [])
            embeddings = []
            for idx, encoding in enumerate(encodings):
                embeddings.append(
                    {
                        "vector": (
                            encoding
                            if isinstance(encoding, list)
                            else encoding.tolist()
                        ),
                        "quality_score": 0.7,
                        "created_at": old_doc.get("created_at", datetime.now()),
                        "angle": f"angle_{idx}",
                    }
                )
        elif "face_encoding" in old_doc:
            # Single encoding
            face_encoding = old_doc.get("face_encoding")
            embeddings = [
                {
                    "vector": (
                        face_encoding
                        if isinstance(face_encoding, list)
                        else face_encoding.tolist()
                    ),
                    "quality_score": 0.7,
                    "created_at": old_doc.get("created_at", datetime.now()),
                    "angle": "frontal",
                }
            ]
        else:
            # Unknown schema - preserve as-is if it looks modern
            if "embeddings" in old_doc:
                return old_doc
            embeddings = []

        return {
            "employee_id": old_doc["employee_id"],
            "embeddings": embeddings,
            "metadata": {
                "algorithm": "dlib_face_recognition_resnet_model_v1",
                "version": "1.0",
                "created_at": old_doc.get("created_at", datetime.now()),
                "last_updated": datetime.now(),
                "migrated_from": "faces",
            },
            "is_active": True,
        }

    def _handle_duplicate_merge(
        self,
        employee_id: int,
        new_doc: Dict,
        target_collection,
        source_name: str,
        results: Dict,
    ):
        """Handle duplicate employee_id by merging embeddings"""
        # Get existing document
        existing_doc = target_collection.find_one({"employee_id": employee_id})
        if not existing_doc:
            return

        # Convert new doc to modern format
        if source_name == "face_encodings":
            new_modern = self._convert_face_encodings_to_embeddings(new_doc)
        else:
            new_modern = self._convert_faces_to_embeddings(new_doc)

        # Merge embeddings
        existing_embeddings = existing_doc.get("embeddings", [])
        new_embeddings = new_modern.get("embeddings", [])

        merged_embeddings = existing_embeddings + new_embeddings

        if not self.dry_run:
            target_collection.update_one(
                {"employee_id": employee_id},
                {
                    "$set": {
                        "embeddings": merged_embeddings,
                        "metadata.last_updated": datetime.now(),
                        "metadata.merged_from": source_name,
                    }
                },
            )

        results["merged_duplicates"] += 1
        self.stdout.write(
            f"  ✓ Merged {len(new_embeddings)} embeddings for employee {safe_id(employee_id)} from {source_name}"
        )

    def _verify_migration(self, audit_before: Dict, migration_results: Dict):
        """Verify migration was successful"""
        # Re-audit to check final state
        audit_after = self._audit_collections()

        expected_count = (
            audit_before["face_encodings"]["count"]
            + audit_before["faces"]["count"]
            + audit_before["face_embeddings"]["count"]
            - migration_results["skipped_duplicates"]
        )

        actual_count = audit_after["face_embeddings"]["count"]

        self.stdout.write(f"Expected documents in face_embeddings: {expected_count}")
        self.stdout.write(f"Actual documents in face_embeddings: {actual_count}")

        if actual_count >= expected_count - migration_results["merged_duplicates"]:
            self.stdout.write(self.style.SUCCESS("\n✅ Verification PASSED"))
        else:
            self.stdout.write(
                self.style.ERROR(f"\n❌ Verification FAILED - document count mismatch")
            )

    def _cleanup_legacy_collections(self, migration_results: Dict):
        """Delete legacy collections after successful migration"""
        if migration_results["errors"]:
            self.stdout.write(
                self.style.WARNING("⚠️  Skipping cleanup due to migration errors")
            )
            return

        collections_to_delete = []
        if migration_results["migrated_from_face_encodings"] > 0:
            collections_to_delete.append("face_encodings")
        if migration_results["migrated_from_faces"] > 0:
            collections_to_delete.append("faces")

        for coll_name in collections_to_delete:
            self.stdout.write(f"Deleting legacy collection: {coll_name}...")
            if not self.dry_run:
                self.db[coll_name].drop()
            self.stdout.write(self.style.SUCCESS(f"  ✅ Deleted {coll_name}"))

    def _print_final_summary(self, results: Dict, backup_file: Optional[str]):
        """Print final migration summary"""
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("📊 MIGRATION SUMMARY"))
        self.stdout.write("=" * 80 + "\n")

        self.stdout.write(
            f"Migrated from face_encodings: {results['migrated_from_face_encodings']}"
        )
        self.stdout.write(f"Migrated from faces: {results['migrated_from_faces']}")
        self.stdout.write(f"Skipped duplicates: {results['skipped_duplicates']}")
        self.stdout.write(f"Merged duplicates: {results['merged_duplicates']}")
        self.stdout.write(f"Errors: {len(results['errors'])}")

        if results["errors"]:
            self.stdout.write("\n❌ Errors encountered:")
            for error in results["errors"]:
                self.stdout.write(f"   - {error}")

        if backup_file:
            self.stdout.write(f"\n💾 Backup file: {backup_file}")

        if self.dry_run:
            self.stdout.write(
                self.style.WARNING("\n⚠️  DRY RUN completed - no changes were made")
            )
            self.stdout.write(
                "\nTo perform actual migration, run without --dry-run flag"
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("\n✅ Migration completed successfully!")
            )
            self.stdout.write("\nNext steps:")
            self.stdout.write("1. Verify face_embeddings collection data")
            self.stdout.write("2. Fix mongodb_service.py to use ONLY 'face_embeddings'")
            self.stdout.write("3. Update views and management commands")
            self.stdout.write("4. Run tests to ensure compatibility")

    def _execute_rollback(self):
        """Rollback from a backup file"""
        self.stdout.write(
            self.style.WARNING(f"\n🔄 Rolling back from: {self.rollback_file}\n")
        )

        if not Path(self.rollback_file).exists():
            raise CommandError(f"Backup file not found: {self.rollback_file}")

        # Load backup
        with open(self.rollback_file, "r") as f:
            backup_data = json.load(f)

        # Restore each collection
        for coll_name, coll_data in backup_data["collections"].items():
            self.stdout.write(f"Restoring {coll_name}...")

            collection = self.db[coll_name]

            # Clear existing data
            collection.delete_many({})

            # Restore documents
            documents = coll_data["documents"]
            if documents:
                # Convert string IDs back to ObjectId
                for doc in documents:
                    doc["_id"] = ObjectId(doc["_id"])

                collection.insert_many(documents)

            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✅ Restored {len(documents)} documents to {coll_name}"
                )
            )

        self.stdout.write(self.style.SUCCESS("\n✅ Rollback completed successfully"))
