from django.core.management.base import BaseCommand
from django.db import models
from payroll.models import Salary, CompensatoryDay
from users.models import Employee


class Command(BaseCommand):
    help = 'Clean up test/demo payroll data'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', 
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )
        parser.add_argument(
            '--all',
            action='store_true', 
            help='Delete all payroll data'
        )
        parser.add_argument(
            '--test-only',
            action='store_true',
            help='Delete only obvious test data (salary > 40000 or unrealistic values)'
        )
        
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        delete_all = options['all']
        test_only = options['test_only']
        
        self.stdout.write('🧹 Payroll Data Cleanup')
        self.stdout.write('=' * 40)
        
        if delete_all:
            self.cleanup_all_payroll(dry_run)
        elif test_only:
            self.cleanup_test_data_only(dry_run)
        else:
            self.cleanup_unrealistic_data(dry_run)
            
    def cleanup_all_payroll(self, dry_run):
        """Delete ALL payroll data"""
        salaries = Salary.objects.all()
        compensatory_days = CompensatoryDay.objects.all()
        
        self.stdout.write(f'📊 Found {salaries.count()} salary records')
        self.stdout.write(f'📊 Found {compensatory_days.count()} compensatory day records')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN: Would delete all payroll data'))
        else:
            compensatory_days.delete()
            salaries.delete()
            self.stdout.write(self.style.SUCCESS('✅ Deleted all payroll data'))
            
    def cleanup_test_data_only(self, dry_run):
        """Delete only obvious test data"""
        # Delete salaries with unrealistic values (likely test data)
        test_salaries = Salary.objects.filter(
            models.Q(base_salary__gt=40000) |  # Monthly salary > 40k ILS
            models.Q(hourly_rate__gt=200) |    # Hourly rate > 200 ILS
            models.Q(base_salary__lt=1000)     # Monthly salary < 1k ILS
        )
        
        self.stdout.write(f'📊 Found {test_salaries.count()} test salary records')
        
        if dry_run:
            for salary in test_salaries:
                self.stdout.write(f'  - Would delete: {salary.employee.get_full_name()} (Base: {salary.base_salary}, Hourly: {salary.hourly_rate})')
        else:
            deleted_count = test_salaries.count()
            test_salaries.delete()
            self.stdout.write(self.style.SUCCESS(f'✅ Deleted {deleted_count} test salary records'))
            
    def cleanup_unrealistic_data(self, dry_run):
        """Delete payroll data with unrealistic values"""
        # Find salaries with values that seem like test data
        unrealistic_salaries = Salary.objects.filter(
            models.Q(base_salary__gt=50000) |  # Monthly > 50k ILS (unrealistic for most positions)
            models.Q(hourly_rate__gt=500) |    # Hourly > 500 ILS (unrealistic)
            models.Q(base_salary=50000) |      # Exact 50k (likely hardcoded test value)
            models.Q(hourly_rate=80, base_salary=25000)  # Common test combination
        )
        
        self.stdout.write(f'📊 Found {unrealistic_salaries.count()} unrealistic salary records')
        
        if unrealistic_salaries.exists():
            self.stdout.write('Unrealistic salary records:')
            for salary in unrealistic_salaries:
                employee_name = salary.employee.get_full_name()
                self.stdout.write(f'  - {employee_name}: Base={salary.base_salary}, Hourly={salary.hourly_rate}')
                
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN: Would delete unrealistic salary data'))
        else:
            deleted_count = unrealistic_salaries.count()
            unrealistic_salaries.delete()
            self.stdout.write(self.style.SUCCESS(f'✅ Deleted {deleted_count} unrealistic salary records'))