from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from worktime.models import WorkLog
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Hard delete old soft-deleted work logs (DANGEROUS!)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=365,
            help='Delete soft-deleted records older than N days (default: 365)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Actually perform the deletion (required for real deletion)'
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        confirm = options['confirm']
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        self.stdout.write(f"🔍 Looking for soft-deleted work logs older than {days} days ({cutoff_date.strftime('%Y-%m-%d')})")
        
        # Find old soft-deleted records
        old_logs = WorkLog.all_objects.filter(
            is_deleted=True,
            deleted_at__lt=cutoff_date
        )
        
        count = old_logs.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS("✅ No old soft-deleted records found"))
            return
        
        self.stdout.write(f"📊 Found {count} old soft-deleted work logs:")
        
        # Show sample records
        for log in old_logs[:5]:  # Show first 5
            self.stdout.write(
                f"  - ID {log.id}: {log.employee.get_full_name()} - "
                f"{log.check_in.strftime('%Y-%m-%d')} (deleted: {log.deleted_at.strftime('%Y-%m-%d')})"
            )
        
        if count > 5:
            self.stdout.write(f"  ... and {count - 5} more")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("🔍 DRY RUN - No records were deleted"))
            return
        
        if not confirm:
            self.stdout.write(
                self.style.ERROR("❌ Add --confirm flag to actually delete records")
            )
            return
        
        # Confirm deletion
        self.stdout.write(
            self.style.ERROR(f"⚠️  WARNING: This will PERMANENTLY delete {count} work log records!")
        )
        
        response = input("Type 'DELETE' to confirm: ")
        if response != 'DELETE':
            self.stdout.write("❌ Deletion cancelled")
            return
        
        # Perform hard deletion
        deleted_count, deleted_details = old_logs.delete()
        
        self.stdout.write(
            self.style.SUCCESS(f"✅ Successfully deleted {deleted_count} records")
        )
        
        logger.warning(f"Hard deleted {deleted_count} old work log records older than {days} days")