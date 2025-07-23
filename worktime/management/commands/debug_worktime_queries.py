from django.core.management.base import BaseCommand
from django.db import connection
from django.test.utils import override_settings
from worktime.models import WorkLog
from worktime.serializers import WorkLogSerializer
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Debug N+1 query issues in worktime API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--employee-id',
            type=int,
            help='Test with specific employee ID to simulate frontend filtering',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Limit number of records to test (default: 10)',
        )

    @override_settings(DEBUG=True)  # Enable query logging
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔍 Starting worktime N+1 query analysis...'))
        
        employee_id = options.get('employee_id')
        limit = options.get('limit')
        
        # Reset query count
        connection.queries_log.clear()
        initial_query_count = len(connection.queries)
        
        # Test 1: Unoptimized query (original issue)
        self.stdout.write('\n📊 Test 1: Unoptimized query (potential N+1)')
        connection.queries_log.clear()
        
        if employee_id:
            worklogs = WorkLog.objects.filter(employee_id=employee_id).order_by('-check_in')[:limit]
        else:
            worklogs = WorkLog.objects.all().order_by('-check_in')[:limit]
            
        # Force evaluation and serialization
        data = []
        for worklog in worklogs:
            # This simulates what happens in the serializer
            employee_name = worklog.employee.get_full_name()  # Potential N+1 here
            total_hours = worklog.get_total_hours()
            data.append({
                'id': worklog.id,
                'employee_name': employee_name,
                'total_hours': total_hours,
                'check_in': worklog.check_in,
                'check_out': worklog.check_out,
            })
        
        unoptimized_queries = len(connection.queries) - initial_query_count
        self.stdout.write(f'  📈 Records processed: {len(data)}')
        self.stdout.write(f'  🔍 Database queries: {unoptimized_queries}')
        if unoptimized_queries > len(data) + 1:
            self.stdout.write(self.style.ERROR(f'  ⚠️  POTENTIAL N+1 DETECTED! Expected ~{len(data) + 1} queries, got {unoptimized_queries}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'  ✅ Query count looks optimal'))
        
        # Test 2: Optimized query with select_related
        self.stdout.write('\n📊 Test 2: Optimized query with select_related')
        connection.queries_log.clear()
        initial_query_count = len(connection.queries)
        
        if employee_id:
            worklogs_optimized = WorkLog.objects.select_related('employee').filter(
                employee_id=employee_id
            ).order_by('-check_in')[:limit]
        else:
            worklogs_optimized = WorkLog.objects.select_related('employee').order_by('-check_in')[:limit]
            
        # Force evaluation and serialization
        data_optimized = []
        for worklog in worklogs_optimized:
            # This should NOT trigger additional queries
            employee_name = worklog.employee.get_full_name()
            total_hours = worklog.get_total_hours()
            data_optimized.append({
                'id': worklog.id,
                'employee_name': employee_name,
                'total_hours': total_hours,
                'check_in': worklog.check_in,
                'check_out': worklog.check_out,
            })
        
        optimized_queries = len(connection.queries) - initial_query_count
        self.stdout.write(f'  📈 Records processed: {len(data_optimized)}')
        self.stdout.write(f'  🔍 Database queries: {optimized_queries}')
        if optimized_queries <= 2:  # Should be 1-2 queries max
            self.stdout.write(self.style.SUCCESS(f'  ✅ Optimized query count is good'))
        else:
            self.stdout.write(self.style.WARNING(f'  ⚠️  Still more queries than expected'))
        
        # Test 3: Using the actual serializer with full optimization
        self.stdout.write('\n📊 Test 3: Using WorkLogSerializer with full optimization (production scenario)')
        connection.queries_log.clear()
        initial_query_count = len(connection.queries)
        
        if employee_id:
            worklogs_serializer = WorkLog.objects.select_related(
                'employee__user'  # Employee and linked User
            ).prefetch_related(
                'employee__salary_info',        # Salary information  
                'employee__invitation',         # Employee invitation
                'employee__biometric_profile'   # Biometric profile (OneToOneField)
            ).filter(
                employee_id=employee_id
            ).order_by('-check_in')[:limit]
        else:
            worklogs_serializer = WorkLog.objects.select_related(
                'employee__user'  # Employee and linked User
            ).prefetch_related(
                'employee__salary_info',        # Salary information  
                'employee__invitation',         # Employee invitation
                'employee__biometric_profile'   # Biometric profile (OneToOneField)
            ).order_by('-check_in')[:limit]
        
        # Use actual serializer
        serializer = WorkLogSerializer(worklogs_serializer, many=True)
        serialized_data = serializer.data  # Force evaluation
        
        serializer_queries = len(connection.queries) - initial_query_count
        self.stdout.write(f'  📈 Records processed: {len(serialized_data)}')
        self.stdout.write(f'  🔍 Database queries: {serializer_queries}')
        if serializer_queries <= 2:
            self.stdout.write(self.style.SUCCESS(f'  ✅ Serializer query count is optimal'))
        else:
            self.stdout.write(self.style.WARNING(f'  ⚠️  Serializer might have N+1 issues'))
        
        # Summary
        self.stdout.write('\n📋 SUMMARY:')
        self.stdout.write(f'  Unoptimized queries: {unoptimized_queries}')
        self.stdout.write(f'  Optimized queries: {optimized_queries}')
        self.stdout.write(f'  Serializer queries: {serializer_queries}')
        
        improvement = unoptimized_queries - optimized_queries
        if improvement > 0:
            self.stdout.write(self.style.SUCCESS(f'  🎉 Query reduction: {improvement} queries ({improvement/unoptimized_queries*100:.1f}% improvement)'))
        
        # Show actual queries if in verbose mode
        if options.get('verbosity', 1) > 1:
            self.stdout.write('\n🔍 Recent queries:')
            for i, query in enumerate(connection.queries[-10:], 1):
                self.stdout.write(f'  {i}. {query["sql"][:100]}...')
                self.stdout.write(f'     Time: {query["time"]}s')
        
        self.stdout.write(self.style.SUCCESS('\n✅ Worktime query analysis complete!'))