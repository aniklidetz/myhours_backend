import django_filters
from .models import WorkLog

class WorkLogFilter(django_filters.FilterSet):
    date = django_filters.DateFilter(field_name="check_in", lookup_expr="date")

    class Meta:
        model = WorkLog
        fields = []