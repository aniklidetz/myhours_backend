import django_filters
from django.db.models import Q
from .models import WorkLog

class WorkLogFilter(django_filters.FilterSet):
    # Include shifts that started OR ended on the specified date (for night shifts)
    date = django_filters.DateFilter(method='filter_by_activity_date')
    employee = django_filters.NumberFilter(field_name='employee__id')
    date_from = django_filters.DateFilter(field_name='check_in__date', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='check_in__date', lookup_expr='lte')
    is_approved = django_filters.BooleanFilter()
    is_suspicious = django_filters.BooleanFilter()
    check_out__isnull = django_filters.BooleanFilter(field_name='check_out', lookup_expr='isnull')

    def filter_by_activity_date(self, queryset, name, value):
        """
        Filter work logs that have activity on the specified date.
        This includes:
        1. Shifts that started on this date
        2. Night shifts that started yesterday but ended today
        """
        if not value:
            return queryset
        
        from datetime import timedelta
        yesterday = value - timedelta(days=1)
        
        # Include logs where:
        # 1. Check-in happened on this date, OR
        # 2. Check-in happened yesterday AND check-out happened today (night shifts only)
        return queryset.filter(
            Q(check_in__date=value) | 
            Q(check_in__date=yesterday, check_out__date=value)
        )

    class Meta:
        model = WorkLog
        fields = ['employee', 'date', 'date_from', 'date_to', 'is_approved', 'is_suspicious', 'check_out__isnull']