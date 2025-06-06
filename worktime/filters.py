import django_filters
from .models import WorkLog

class WorkLogFilter(django_filters.FilterSet):
    date = django_filters.DateFilter(field_name="check_in", lookup_expr="date")
    employee = django_filters.NumberFilter(field_name='employee__id')
    date_from = django_filters.DateFilter(field_name='check_in__date', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='check_in__date', lookup_expr='lte')
    is_approved = django_filters.BooleanFilter()
    is_suspicious = django_filters.BooleanFilter()

    class Meta:
        model = WorkLog
        fields = ['employee', 'date', 'date_from', 'date_to', 'is_approved', 'is_suspicious']