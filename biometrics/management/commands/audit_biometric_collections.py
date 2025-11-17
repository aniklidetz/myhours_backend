"""
Management command to audit all three MongoDB biometric collections.

This command checks for data in:
1. face_encodings (legacy BiometricService collection)
2. faces (legacy conditional collection from mongodb_service.py)
3. face_embeddings (modern MongoDBRepository collection)

Usage:
    python manage.py audit_biometric_collections
    python manage.py audit_biometric_collections --detailed
"""

import json
from typing import Dict, List

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.logging_utils import safe_id


class Command(BaseCommand):
    help = "Audit all MongoDB biometric collections for migration planning"

    def add_arguments(self, parser):
        parser.add_argument(
            "--detailed",
            action="store_true",
            help="Show detailed information about each document",
        )
        parser.add_argument(
            "--export",
            type=str,
            help="Export audit results to JSON file",
        )

    def handle(self, *args, **options):
        """Execute the audit"""
        self.detailed = options.get("detailed", False)
        self.export_path = options.get("export")

        try:
            # Get MongoDB database
            db = settings.MONGO_DB
            if db is None:
                raise CommandError("MongoDB database not available")

            self.stdout.write(self.style.SUCCESS("\n" + "=" * 80))
            self.stdout.write(
                self.style.SUCCESS("BIOMETRIC COLLECTIONS AUDIT - Phase 1.2")
            )
            self.stdout.write(self.style.SUCCESS("=" * 80 + "\n"))

            # Get all collection names
            all_collections = db.list_collection_names()

            # Audit each collection
            results = {
                "total_collections": len(all_collections),
                "biometric_collections": {},
                "all_collections": all_collections,
            }

            # Collection schemas to check
            collections_to_audit = {
                "face_encodings": {
                    "service": "BiometricService (LEGACY)",
                    "schema": "Flat array",
                    "risk": "HIGH",
                },
                "faces": {
                    "service": "MongoDBService conditional (CRITICAL)",
                    "schema": "Unknown/Legacy",
                    "risk": "CRITICAL",
                },
                "face_embeddings": {
                    "service": "MongoDBRepository (MODERN)",
                    "schema": "Structured with metadata",
                    "risk": "LOW",
                },
            }

            for collection_name, info in collections_to_audit.items():
                self.stdout.write(f"\n{'─' * 80}")
                self.stdout.write(self.style.WARNING(f"📊 Auditing: {collection_name}"))
                self.stdout.write(f"{'─' * 80}")

                collection_data = self._audit_collection(
                    db, collection_name, info, self.detailed
                )
                results["biometric_collections"][collection_name] = collection_data

            # Summary
            self._print_summary(results)

            # Export if requested
            if self.export_path:
                self._export_results(results)

            # Migration recommendations
            self._print_recommendations(results)

            self.stdout.write(self.style.SUCCESS("\n✅ Audit completed successfully\n"))

        except Exception as e:
            raise CommandError(f"Audit failed: {str(e)}")

    def _audit_collection(
        self, db, collection_name: str, info: Dict, detailed: bool
    ) -> Dict:
        """Audit a single collection"""
        result = {
            "service": info["service"],
            "schema": info["schema"],
            "risk_level": info["risk"],
            "exists": collection_name in db.list_collection_names(),
            "count": 0,
            "sample_documents": [],
            "employee_ids": [],
            "schema_analysis": {},
        }

        if not result["exists"]:
            self.stdout.write(
                self.style.WARNING(f"  ⚠️  Collection does not exist: {collection_name}")
            )
            return result

        collection = db[collection_name]
        result["count"] = collection.count_documents({})

        self.stdout.write(f"  ✓ Exists: Yes")
        self.stdout.write(f"  ✓ Service: {info['service']}")
        self.stdout.write(f"  ✓ Risk Level: {info['risk']}")
        self.stdout.write(f"  ✓ Document Count: {result['count']}")

        if result["count"] == 0:
            self.stdout.write(
                self.style.SUCCESS("  ✅ Collection is EMPTY - safe to migrate")
            )
            return result

        # Get sample documents
        samples = list(collection.find({}).limit(5))
        result["employee_ids"] = [
            doc.get("employee_id") for doc in samples if "employee_id" in doc
        ]

        # Analyze schema
        if samples:
            first_doc = samples[0]
            result["schema_analysis"] = {
                "fields": list(first_doc.keys()),
                "has_employee_id": "employee_id" in first_doc,
                "has_embeddings": "embeddings" in first_doc,
                "has_encodings": "encodings" in first_doc,
                "has_face_encoding": "face_encoding" in first_doc,
                "has_metadata": "metadata" in first_doc,
                "has_is_active": "is_active" in first_doc,
            }

            self.stdout.write(f"\n  📋 Schema Analysis:")
            self.stdout.write(
                f"     Fields: {', '.join(result['schema_analysis']['fields'])}"
            )
            self.stdout.write(
                f"     Employee IDs found: {len(set(result['employee_ids']))}"
            )

            # Detailed output
            if detailed:
                self.stdout.write(f"\n  🔍 Sample Documents:")
                for idx, doc in enumerate(samples[:3], 1):
                    # Sanitize sensitive data
                    sanitized = self._sanitize_document(doc)
                    self.stdout.write(f"\n     Document {idx}:")
                    self.stdout.write(
                        f"     {json.dumps(sanitized, indent=6, default=str)}"
                    )

            # Store sanitized samples for export
            result["sample_documents"] = [
                self._sanitize_document(doc) for doc in samples
            ]

        # Check for data quality issues
        self._check_data_quality(collection, result)

        return result

    def _sanitize_document(self, doc: Dict) -> Dict:
        """Sanitize document for safe display"""
        sanitized = {}
        for key, value in doc.items():
            if key == "_id":
                sanitized[key] = str(value)
            elif key == "employee_id":
                sanitized[key] = f"emp_{safe_id(value)}"
            elif key in ["face_encoding", "encodings"]:
                if isinstance(value, list):
                    if len(value) > 0 and isinstance(value[0], list):
                        sanitized[key] = (
                            f"[{len(value)} encodings of {len(value[0])} dims]"
                        )
                    else:
                        sanitized[key] = f"[{len(value)} dims]"
                else:
                    sanitized[key] = str(type(value))
            elif key == "embeddings":
                if isinstance(value, list):
                    sanitized[key] = f"[{len(value)} embeddings]"
                else:
                    sanitized[key] = str(type(value))
            else:
                sanitized[key] = value
        return sanitized

    def _check_data_quality(self, collection, result: Dict):
        """Check for data quality issues"""
        issues = []

        # Check for missing employee_id
        missing_emp_id = collection.count_documents({"employee_id": {"$exists": False}})
        if missing_emp_id > 0:
            issues.append(f"{missing_emp_id} documents missing employee_id")

        # Check for null/empty embeddings
        empty_embeddings = collection.count_documents(
            {
                "$or": [
                    {"embeddings": {"$exists": False}},
                    {"embeddings": []},
                    {"encodings": {"$exists": False}},
                    {"encodings": []},
                    {"face_encoding": {"$exists": False}},
                    {"face_encoding": None},
                ]
            }
        )
        if empty_embeddings > 0:
            issues.append(f"{empty_embeddings} documents with empty/missing embeddings")

        result["data_quality_issues"] = issues

        if issues:
            self.stdout.write(f"\n  ⚠️  Data Quality Issues:")
            for issue in issues:
                self.stdout.write(f"     - {issue}")

    def _print_summary(self, results: Dict):
        """Print audit summary"""
        self.stdout.write(f"\n{'=' * 80}")
        self.stdout.write(self.style.SUCCESS("📊 AUDIT SUMMARY"))
        self.stdout.write(f"{'=' * 80}\n")

        self.stdout.write(f"Total MongoDB collections: {results['total_collections']}")
        self.stdout.write(
            f"Biometric collections checked: {len(results['biometric_collections'])}\n"
        )

        # Table header
        self.stdout.write(
            f"{'Collection':<20} {'Exists':<8} {'Count':<8} {'Risk':<12} {'Status'}"
        )
        self.stdout.write("─" * 80)

        total_docs = 0
        collections_with_data = []

        for name, data in results["biometric_collections"].items():
            exists = "✓" if data["exists"] else "✗"
            count = data["count"]
            risk = data["risk_level"]

            status = "EMPTY ✅" if count == 0 else "HAS DATA ⚠️"
            if count > 0:
                collections_with_data.append(name)
                total_docs += count

            self.stdout.write(f"{name:<20} {exists:<8} {count:<8} {risk:<12} {status}")

        self.stdout.write("─" * 80)
        self.stdout.write(f"Total documents across all collections: {total_docs}\n")

        if collections_with_data:
            self.stdout.write(
                self.style.WARNING(
                    f"⚠️  {len(collections_with_data)} collection(s) contain data:"
                )
            )
            for coll in collections_with_data:
                count = results["biometric_collections"][coll]["count"]
                self.stdout.write(f"   - {coll}: {count} documents")
        else:
            self.stdout.write(
                self.style.SUCCESS("✅ All collections are EMPTY - safe to proceed")
            )

    def _print_recommendations(self, results: Dict):
        """Print migration recommendations"""
        self.stdout.write(f"\n{'=' * 80}")
        self.stdout.write(self.style.SUCCESS("💡 MIGRATION RECOMMENDATIONS"))
        self.stdout.write(f"{'=' * 80}\n")

        # Count non-empty collections
        non_empty = [
            name
            for name, data in results["biometric_collections"].items()
            if data["count"] > 0
        ]

        if len(non_empty) == 0:
            self.stdout.write(
                self.style.SUCCESS("✅ OPTIMAL SITUATION: All collections are empty")
            )
            self.stdout.write("\nRecommended Actions:")
            self.stdout.write("1. Fix mongodb_service.py to use ONLY 'face_embeddings'")
            self.stdout.write(
                "2. Remove conditional collection selection (lines 32-42)"
            )
            self.stdout.write(
                "3. No data migration needed - proceed directly to code fixes"
            )
            self.stdout.write(
                "\nPriority: HIGH - Fix before any production data is created"
            )

        elif len(non_empty) == 1:
            collection_name = non_empty[0]
            count = results["biometric_collections"][collection_name]["count"]

            self.stdout.write(
                self.style.WARNING(f"⚠️  ONE COLLECTION has data: {collection_name}")
            )
            self.stdout.write(f"   Documents: {count}")
            self.stdout.write("\nRecommended Actions:")

            if collection_name == "face_embeddings":
                self.stdout.write(
                    "1. ✅ Data is already in the modern collection - GOOD"
                )
                self.stdout.write(
                    "2. Fix mongodb_service.py to use ONLY 'face_embeddings'"
                )
                self.stdout.write("3. Verify data integrity")
                self.stdout.write("4. Proceed with legacy code removal")
            else:
                self.stdout.write(
                    f"1. ⚠️  Data is in LEGACY collection '{collection_name}'"
                )
                self.stdout.write(
                    "2. RUN: python manage.py migrate_biometric_collections --dry-run"
                )
                self.stdout.write("3. BACKUP: Create MongoDB backup before migration")
                self.stdout.write(
                    "4. MIGRATE: python manage.py migrate_biometric_collections"
                )
                self.stdout.write("5. VERIFY: Check face_embeddings collection")
                self.stdout.write(
                    "6. FIX: Update mongodb_service.py collection selection"
                )

        else:
            self.stdout.write(
                self.style.ERROR(
                    f"❌ CRITICAL: {len(non_empty)} collections have data!"
                )
            )
            self.stdout.write("\nCollections with data:")
            for coll in non_empty:
                count = results["biometric_collections"][coll]["count"]
                self.stdout.write(f"   - {coll}: {count} documents")

            self.stdout.write("\n⚠️  DATA SPLIT DETECTED - Risk of inconsistency!")
            self.stdout.write("\nRecommended Actions:")
            self.stdout.write("1. 🛑 STOP all biometric registration/verification")
            self.stdout.write("2. 💾 BACKUP all MongoDB collections immediately")
            self.stdout.write(
                "3. 🔍 ANALYZE data overlap: python manage.py check_biometric_data_consistency"
            )
            self.stdout.write(
                "4. 🔄 MIGRATE: python manage.py migrate_biometric_collections --merge"
            )
            self.stdout.write("5. ✅ VERIFY: Check for duplicates and conflicts")
            self.stdout.write(
                "6. 🔧 FIX: Update mongodb_service.py collection selection"
            )
            self.stdout.write("\nPriority: CRITICAL - Resolve immediately")

    def _export_results(self, results: Dict):
        """Export results to JSON file"""
        try:
            with open(self.export_path, "w") as f:
                json.dump(results, f, indent=2, default=str)
            self.stdout.write(
                self.style.SUCCESS(f"\n✅ Results exported to: {self.export_path}")
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"\n❌ Failed to export results: {str(e)}")
            )
