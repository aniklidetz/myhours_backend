from django.core.management.base import BaseCommand
from django.utils import timezone
from integrations.services.hebcal_service import HebcalService
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Syncs holidays from Hebcal API to the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            help='Year to sync holidays for (defaults to current year)',
        )
        
        parser.add_argument(
            '--future',
            type=int,
            default=1,
            help='Number of future years to sync (defaults to 1)',
        )

    def handle(self, *args, **options):
        year = options['year']
        future_years = options['future']
        
        if not year:
            year = timezone.now().year
            
        total_created = 0
        total_updated = 0
        
        self.stdout.write(f"Syncing holidays for year {year}")
        try:
            created, updated = HebcalService.sync_holidays_to_db(year)
            self.stdout.write(f"Year {year}: Created {created}, Updated {updated}")
            total_created += created
            total_updated += updated
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error syncing year {year}: {e}"))
        
        # Sync holidays for future years
        for i in range(1, future_years + 1):
            future_year = year + i
            self.stdout.write(f"Syncing holidays for year {future_year}")
            try:
                created, updated = HebcalService.sync_holidays_to_db(future_year)
                self.stdout.write(f"Year {future_year}: Created {created}, Updated {updated}")
                total_created += created
                total_updated += updated
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error syncing year {future_year}: {e}"))
            
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully synced holidays: {total_created} created, {total_updated} updated'
            )
        )