from django.db import models
from django.db.models import DurationField, ExpressionWrapper, F, Sum


class WorkLogQuerySet(models.QuerySet):
    def total_hours(self):
        """Calculate total hours worked using DurationField for SQLite compatibility"""
        duration = ExpressionWrapper(
            F("check_out") - F("check_in"),
            output_field=DurationField(),
        )
        return self.annotate(d=duration).aggregate(total=Sum("d"))["total"]


class WorkLogManager(models.Manager):
    def get_queryset(self):
        return WorkLogQuerySet(self.model, using=self._db)

    def total_hours(self):
        return self.get_queryset().total_hours()
