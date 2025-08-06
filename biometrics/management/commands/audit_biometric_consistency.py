"""
Management command for biometric data consistency audit and repair
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from biometrics.services.enhanced_biometric_service import enhanced_biometric_service
from biometrics.models import BiometricProfile
from biometrics.services.mongodb_repository import mongo_biometric_repository
import json


class Command(BaseCommand):
    help = 'Audit biometric data consistency between MongoDB and PostgreSQL'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Automatically apply fix commands for inconsistencies'
        )
        
        parser.add_argument(
            '--employee-id',
            type=int,
            help='Check specific employee ID only'
        )
        
        parser.add_argument(
            '--output-format',
            choices=['text', 'json'],
            default='text',
            help='Output format (default: text)'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true', 
            help='Show what would be fixed without making changes'
        )
    
    def handle(self, *args, **options):
        self.stdout.write("🔍 Starting biometric consistency audit...")
        
        try:
            if options['employee_id']:
                # Check specific employee
                result = self._check_specific_employee(options['employee_id'])
            else:
                # Full audit
                result = enhanced_biometric_service.audit_consistency()
            
            # Output results
            if options['output_format'] == 'json':
                self.stdout.write(json.dumps(result, indent=2))
            else:
                self._display_text_results(result)
            
            # Apply fixes if requested
            if options['fix'] and result.get('fix_commands'):
                self._apply_fixes(result['fix_commands'], options['dry_run'])
            
            # Set exit code based on consistency
            if not result.get('is_consistent', False):
                raise CommandError("Inconsistencies found!")
                
        except Exception as e:
            raise CommandError(f"Audit failed: {str(e)}")
    
    def _check_specific_employee(self, employee_id):
        """Check specific employee biometric status"""
        self.stdout.write(f"Checking employee ID: {employee_id}")
        
        status = enhanced_biometric_service.get_employee_biometric_status(employee_id)
        
        # Generate fix commands if inconsistent
        fix_commands = []
        if not status['is_consistent']:
            pg_exists = status['postgresql'].get('exists', False)
            mongo_exists = status['mongodb']['exists']
            
            if pg_exists and not mongo_exists:
                # PostgreSQL says has data, but MongoDB is empty
                fix_commands.append(
                    f"# Fix PostgreSQL profile for employee {employee_id} (no MongoDB data)\n"
                    f"BiometricProfile.objects.filter(employee_id={employee_id})"
                    f".update(is_active=False, embeddings_count=0)"
                )
            elif not pg_exists and mongo_exists:
                # MongoDB has data, but no PostgreSQL profile
                fix_commands.append(
                    f"# Create missing PostgreSQL profile for employee {employee_id}\n"
                    f"BiometricProfile.objects.update_or_create("
                    f"employee_id={employee_id}, "
                    f"defaults={{'is_active': True, 'embeddings_count': 1}})"
                )
        
        return {
            'employee_specific': True,
            'employee_id': employee_id,
            'is_consistent': status['is_consistent'],
            'postgresql': status['postgresql'],
            'mongodb': status['mongodb'],
            'fix_commands': fix_commands,
            'timestamp': timezone.now().isoformat()
        }
    
    def _display_text_results(self, result):
        """Display audit results in human-readable format"""
        
        if result.get('employee_specific'):
            # Single employee results
            self.stdout.write("\n" + "="*60)
            self.stdout.write(f"EMPLOYEE {result['employee_id']} BIOMETRIC STATUS")
            self.stdout.write("="*60)
            
            if result['is_consistent']:
                self.stdout.write(self.style.SUCCESS("✅ Data is consistent"))
            else:
                self.stdout.write(self.style.ERROR("❌ Inconsistency detected"))
            
            # PostgreSQL status
            self.stdout.write("\n📊 PostgreSQL Status:")
            pg = result['postgresql']
            if pg.get('exists'):
                self.stdout.write(f"  - Profile exists: Yes")
                self.stdout.write(f"  - Is active: {pg.get('is_active')}")
                self.stdout.write(f"  - Embeddings count: {pg.get('embeddings_count', 0)}")
                self.stdout.write(f"  - Last updated: {pg.get('last_updated', 'N/A')}")
            else:
                self.stdout.write("  - Profile exists: No")
            
            # MongoDB status
            self.stdout.write("\n🍃 MongoDB Status:")
            mongo = result['mongodb']
            self.stdout.write(f"  - Data exists: {mongo['exists']}")
            self.stdout.write(f"  - Embeddings count: {mongo['embeddings_count']}")
            
        else:
            # Full audit results
            self.stdout.write("\n" + "="*60)
            self.stdout.write("BIOMETRIC DATA CONSISTENCY AUDIT RESULTS")
            self.stdout.write("="*60)
            
            # Summary
            self.stdout.write(f"📊 Audit timestamp: {result.get('timestamp', 'N/A')}")
            self.stdout.write(f"📊 Total PostgreSQL profiles: {result.get('total_pg_profiles', 0)}")
            self.stdout.write(f"📊 Total MongoDB records: {result.get('total_mongo_records', 0)}")
            
            if result.get('is_consistent', False):
                self.stdout.write(self.style.SUCCESS("\n✅ All data is consistent!"))
            else:
                self.stdout.write(self.style.ERROR(f"\n❌ Inconsistencies found:"))
                self.stdout.write(f"  - Orphaned MongoDB records: {result.get('orphaned_mongo_count', 0)}")
                self.stdout.write(f"  - Orphaned PostgreSQL records: {result.get('orphaned_pg_count', 0)}")
                
                # Show orphaned details
                if result.get('orphaned_mongo_ids'):
                    self.stdout.write(f"\n🍃 Orphaned MongoDB IDs: {result['orphaned_mongo_ids']}")
                
                if result.get('orphaned_pg_details'):
                    self.stdout.write(f"\n📊 Orphaned PostgreSQL profiles:")
                    for detail in result['orphaned_pg_details']:
                        self.stdout.write(f"  - ID {detail['employee_id']}: {detail['employee_name']} "
                                        f"(created: {detail['profile_created']})")
        
        # Show fix commands
        if result.get('fix_commands'):
            self.stdout.write(f"\n🔧 Fix Commands ({len(result['fix_commands'])} available):")
            self.stdout.write("-" * 40)
            for i, command in enumerate(result['fix_commands'], 1):
                self.stdout.write(f"\n{i}. {command}")
        else:
            if not result.get('is_consistent', True):
                self.stdout.write("\n⚠️ No automatic fix commands available")
    
    def _apply_fixes(self, fix_commands, dry_run=False):
        """Apply fix commands"""
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\n🧪 DRY RUN MODE - no changes will be made"))
        else:
            self.stdout.write(self.style.WARNING("\n🔧 Applying fixes..."))
        
        fixed_count = 0
        
        for i, command in enumerate(fix_commands, 1):
            try:
                self.stdout.write(f"\n{i}. {command}")
                
                if not dry_run:
                    # Parse and execute the command
                    if "BiometricProfile.objects.filter" in command:
                        # Extract employee_id and update fields
                        if "update(is_active=False" in command:
                            # Extract employee_id from command
                            import re
                            match = re.search(r'employee_id=(\d+)', command)
                            if match:
                                employee_id = int(match.group(1))
                                updated = BiometricProfile.objects.filter(
                                    employee_id=employee_id
                                ).update(
                                    is_active=False,
                                    embeddings_count=0,
                                    last_updated=timezone.now()
                                )
                                if updated:
                                    self.stdout.write(self.style.SUCCESS("   ✅ Fixed"))
                                    fixed_count += 1
                                else:
                                    self.stdout.write(self.style.WARNING("   ⚠️ No changes made"))
                    
                    elif "BiometricProfile.objects.update_or_create" in command:
                        # Extract employee_id and create profile
                        import re
                        match = re.search(r'employee_id=(\d+)', command)
                        if match:
                            employee_id = int(match.group(1))
                            profile, created = BiometricProfile.objects.update_or_create(
                                employee_id=employee_id,
                                defaults={
                                    'is_active': True,
                                    'embeddings_count': 1,
                                    'last_updated': timezone.now()
                                }
                            )
                            action = "created" if created else "updated"
                            self.stdout.write(self.style.SUCCESS(f"   ✅ Profile {action}"))
                            fixed_count += 1
                    
                    elif "mongo_repo.delete_embeddings" in command:
                        # Extract employee_id and delete MongoDB data
                        import re
                        match = re.search(r'delete_embeddings\((\d+)\)', command)
                        if match:
                            employee_id = int(match.group(1))
                            if mongo_biometric_repository.delete_embeddings(employee_id):
                                self.stdout.write(self.style.SUCCESS("   ✅ MongoDB data deleted"))
                                fixed_count += 1
                            else:
                                self.stdout.write(self.style.WARNING("   ⚠️ No MongoDB data found"))
                    
                    else:
                        self.stdout.write(self.style.WARNING("   ⚠️ Unknown command format - skipped"))
                else:
                    self.stdout.write(self.style.SUCCESS("   ✅ Would be executed"))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"   ❌ Failed: {str(e)}"))
        
        if not dry_run:
            self.stdout.write(self.style.SUCCESS(f"\n🎉 Applied {fixed_count} fixes successfully"))
        else:
            self.stdout.write(self.style.SUCCESS(f"\n🧪 Would apply {len(fix_commands)} fixes"))