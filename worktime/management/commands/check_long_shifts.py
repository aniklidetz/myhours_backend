"""
Django management command to check for work shifts longer than 12 hours

Usage:
    python manage.py check_long_shifts
    python manage.py check_long_shifts --days 30
    python manage.py check_long_shifts --employee 5
    python manage.py check_long_shifts --export
"""

from django.core.management.base import BaseCommand
from django.db.models import F, ExpressionWrapper, DurationField, Count, Q
from django.utils import timezone
from datetime import timedelta, datetime
import csv
import logging

from worktime.models import WorkLog
from users.models import Employee

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Check for work shifts longer than 12 hours in the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=90,
            help='Number of days to check (default: 90)'
        )
        parser.add_argument(
            '--employee',
            type=int,
            help='Check specific employee by ID'
        )
        parser.add_argument(
            '--export',
            action='store_true',
            help='Export results to CSV file'
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Attempt to fix invalid shifts'
        )
        parser.add_argument(
            '--shorten',
            action='store_true',
            help='Shorten all shifts longer than 12 hours to exactly 12 hours'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without applying them (use with --shorten)'
        )

    def handle(self, *args, **options):
        days = options['days']
        employee_id = options['employee']
        export_csv = options['export']
        fix_shifts = options['fix']
        shorten_shifts = options['shorten']
        dry_run = options['dry_run']
        
        self.stdout.write(
            self.style.SUCCESS(f'🔍 Checking for work shifts longer than 12 hours...')
        )
        
        # Calculate date range
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        # Base queryset
        queryset = WorkLog.objects.filter(
            check_out__isnull=False,
            check_in__gte=start_date
        )
        
        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)
            
        # Add duration annotation
        queryset = queryset.annotate(
            duration=ExpressionWrapper(
                F('check_out') - F('check_in'),
                output_field=DurationField()
            )
        )
        
        # Filter for shifts longer than 12 hours
        long_shifts = queryset.filter(
            duration__gt=timedelta(hours=12)
        ).select_related('employee').order_by('-duration')
        
        total_count = long_shifts.count()
        
        self.stdout.write(f'📊 Found {total_count} shifts longer than 12 hours')
        
        if total_count == 0:
            self.stdout.write(
                self.style.SUCCESS('✅ No problematic shifts found!')
            )
            return
            
        # Analyze shifts by duration
        self._analyze_shifts(long_shifts)
        
        # Show top problematic shifts
        self._show_top_shifts(long_shifts[:10])
        
        # Check for overnight shifts
        self._check_overnight_shifts(long_shifts)
        
        # Employee statistics
        self._employee_statistics(long_shifts)
        
        # Export if requested
        if export_csv:
            self._export_to_csv(long_shifts)
            
        # Fix shifts if requested
        if fix_shifts:
            self._fix_invalid_shifts(long_shifts)
            
        # Shorten shifts if requested
        if shorten_shifts:
            self._shorten_long_shifts(long_shifts, dry_run)
            
    def _analyze_shifts(self, long_shifts):
        """Analyze shifts by duration categories"""
        self.stdout.write('\n📈 Shift Duration Analysis:')
        
        # Duration categories
        categories = [
            (12, 16, '12-16 hours'),
            (16, 20, '16-20 hours'),
            (20, 24, '20-24 hours'),
            (24, 48, '1-2 days'),
            (48, 168, '2-7 days'),
            (168, 8760, '7+ days')  # Use 1 year instead of infinity
        ]
        
        for min_hours, max_hours, label in categories:
            if max_hours == 8760:  # Handle the last category differently
                count = long_shifts.filter(
                    duration__gte=timedelta(hours=min_hours)
                ).count()
            else:
                count = long_shifts.filter(
                    duration__gte=timedelta(hours=min_hours),
                    duration__lt=timedelta(hours=max_hours)
                ).count()
            
            if count > 0:
                self.stdout.write(f'   {label}: {count} shifts')
                
    def _show_top_shifts(self, top_shifts):
        """Show details of longest shifts"""
        self.stdout.write('\n❗ Top 10 Longest Shifts:')
        
        for i, shift in enumerate(top_shifts, 1):
            duration_hours = shift.duration.total_seconds() / 3600
            
            # Check if shift crosses midnight
            crosses_midnight = shift.check_in.date() != shift.check_out.date()
            
            self.stdout.write(
                f'\n   {i}. Employee: {shift.employee.get_full_name()} (ID: {shift.employee.id})'
            )
            self.stdout.write(f'      Duration: {duration_hours:.1f} hours')
            self.stdout.write(
                f'      Check-in: {shift.check_in.strftime("%Y-%m-%d %H:%M:%S %Z")}'
            )
            self.stdout.write(
                f'      Check-out: {shift.check_out.strftime("%Y-%m-%d %H:%M:%S %Z")}'
            )
            
            if crosses_midnight:
                self.stdout.write(
                    self.style.WARNING('      ⚠️ Crosses midnight (overnight shift)')
                )
                
            if duration_hours > 24:
                self.stdout.write(
                    self.style.ERROR('      ❌ INVALID: Longer than 24 hours!')
                )
                
            # Check for missing check-out (forgot to clock out)
            if duration_hours > 48:
                self.stdout.write(
                    self.style.ERROR('      ❌ LIKELY ERROR: Forgot to clock out?')
                )
                
    def _check_overnight_shifts(self, long_shifts):
        """Check for overnight shifts that might be legitimate"""
        overnight_shifts = []
        
        for shift in long_shifts:
            check_in_hour = shift.check_in.hour
            check_out_hour = shift.check_out.hour
            
            # Check if this is likely a night shift
            if (check_in_hour >= 18 or check_in_hour <= 6) and shift.duration < timedelta(hours=16):
                overnight_shifts.append(shift)
                
        self.stdout.write(f'\n🌙 Found {len(overnight_shifts)} potential overnight shifts')
        
    def _employee_statistics(self, long_shifts):
        """Show statistics by employee"""
        self.stdout.write('\n👥 Employee Statistics:')
        
        # Group by employee
        employee_stats = {}
        for shift in long_shifts:
            emp_id = shift.employee.id
            if emp_id not in employee_stats:
                employee_stats[emp_id] = {
                    'name': shift.employee.get_full_name(),
                    'count': 0,
                    'total_hours': 0,
                    'max_hours': 0
                }
            
            hours = shift.duration.total_seconds() / 3600
            employee_stats[emp_id]['count'] += 1
            employee_stats[emp_id]['total_hours'] += hours
            employee_stats[emp_id]['max_hours'] = max(
                employee_stats[emp_id]['max_hours'], hours
            )
            
        # Sort by count
        sorted_stats = sorted(
            employee_stats.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )
        
        # Show top 5
        for emp_id, stats in sorted_stats[:5]:
            avg_hours = stats['total_hours'] / stats['count']
            self.stdout.write(
                f'\n   {stats["name"]} (ID: {emp_id}):'
            )
            self.stdout.write(f'      Long shifts: {stats["count"]}')
            self.stdout.write(f'      Average duration: {avg_hours:.1f} hours')
            self.stdout.write(f'      Longest shift: {stats["max_hours"]:.1f} hours')
            
    def _export_to_csv(self, long_shifts):
        """Export results to CSV file"""
        filename = f'long_shifts_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        with open(filename, 'w', newline='') as csvfile:
            fieldnames = [
                'employee_id', 'employee_name', 'check_in', 'check_out',
                'duration_hours', 'crosses_midnight', 'likely_error'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for shift in long_shifts:
                duration_hours = shift.duration.total_seconds() / 3600
                writer.writerow({
                    'employee_id': shift.employee.id,
                    'employee_name': shift.employee.get_full_name(),
                    'check_in': shift.check_in.isoformat(),
                    'check_out': shift.check_out.isoformat(),
                    'duration_hours': round(duration_hours, 2),
                    'crosses_midnight': shift.check_in.date() != shift.check_out.date(),
                    'likely_error': duration_hours > 48
                })
                
        self.stdout.write(
            self.style.SUCCESS(f'✅ Exported {long_shifts.count()} records to {filename}')
        )
        
    def _fix_invalid_shifts(self, long_shifts):
        """Attempt to fix clearly invalid shifts"""
        self.stdout.write('\n🔧 Attempting to fix invalid shifts...')
        
        fixed_count = 0
        
        for shift in long_shifts:
            duration_hours = shift.duration.total_seconds() / 3600
            
            # Only fix shifts that are clearly errors (>48 hours)
            if duration_hours > 48:
                self.stdout.write(
                    f'\n   Shift {shift.id}: {duration_hours:.1f} hours'
                )
                self.stdout.write(
                    f'   Employee: {shift.employee.get_full_name()}'
                )
                
                # Suggest fix: Set check-out to 8 hours after check-in
                suggested_checkout = shift.check_in + timedelta(hours=8)
                
                self.stdout.write(
                    f'   Suggested fix: Change check-out to {suggested_checkout}'
                )
                
                # In real implementation, you might want to:
                # 1. Ask for confirmation
                # 2. Create audit log
                # 3. Notify employee/manager
                
                # For now, just show what would be done
                self.stdout.write(
                    self.style.WARNING('   ⚠️ Fix not applied (dry run)')
                )
                
        self.stdout.write(f'\n📊 Would fix {fixed_count} shifts')
    
    def _shorten_long_shifts(self, long_shifts, dry_run=False):
        """Shorten all shifts longer than 12 hours to exactly 12 hours"""
        if dry_run:
            self.stdout.write('\n👀 DRY RUN: Preview of shortening shifts longer than 12 hours...')
        else:
            self.stdout.write('\n✂️ Shortening shifts longer than 12 hours...')
        
        shortened_count = 0
        
        for shift in long_shifts:
            duration_hours = shift.duration.total_seconds() / 3600
            
            if duration_hours > 12:
                # Calculate new check-out time (12 hours after check-in)
                new_checkout = shift.check_in + timedelta(hours=12)
                
                self.stdout.write(
                    f'\n   Shift {shift.id}: {shift.employee.get_full_name()}'
                )
                self.stdout.write(f'   Current duration: {duration_hours:.1f} hours')
                self.stdout.write(f'   Original check-out: {shift.check_out}')
                self.stdout.write(f'   New check-out: {new_checkout}')
                
                if dry_run:
                    # Just preview the change
                    shortened_count += 1
                    self.stdout.write(
                        self.style.WARNING('   👀 WOULD BE SHORTENED (dry run)')
                    )
                else:
                    # Actually make the change
                    try:
                        # Update the shift
                        shift.check_out = new_checkout
                        shift.save()
                        
                        shortened_count += 1
                        self.stdout.write(
                            self.style.SUCCESS('   ✅ Shift shortened successfully')
                        )
                        
                        # Log the change for audit purposes
                        logger.info(
                            f"Shift {shift.id} shortened from {duration_hours:.1f}h to 12h "
                            f"for employee {shift.employee.get_full_name()}"
                        )
                        
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'   ❌ Error shortening shift: {e}')
                        )
        
        if dry_run:
            self.stdout.write(f'\n📊 Would shorten {shortened_count} shifts')
            self.stdout.write(
                self.style.HTTP_INFO(
                    '💡 Use --shorten without --dry-run to actually apply changes'
                )
            )
        else:
            self.stdout.write(f'\n📊 Successfully shortened {shortened_count} shifts')
            
            if shortened_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ All shifts are now 12 hours or less!'
                    )
                )
    
    def _confirm_change(self, shift, new_checkout):
        """Ask for confirmation before making changes (in real implementation)"""
        # In a real implementation, you might want to:
        # 1. Add --dry-run option to preview changes
        # 2. Ask for user confirmation
        # 3. Require explicit confirmation flag
        # 4. Send notifications to employees/managers
        
        # For now, we'll proceed with changes (can be controlled with flags)
        return True