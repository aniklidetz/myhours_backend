# Add only soft delete fields
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
        ('worktime', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='worklog',
            name='is_deleted',
            field=models.BooleanField(default=False, help_text='Soft delete flag - records are marked as deleted instead of being removed'),
        ),
        migrations.AddField(
            model_name='worklog',
            name='deleted_at',
            field=models.DateTimeField(blank=True, help_text='When this record was soft deleted', null=True),
        ),
        migrations.AddField(
            model_name='worklog',
            name='deleted_by',
            field=models.ForeignKey(blank=True, help_text='Who deleted this record', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='deleted_work_logs', to='users.employee'),
        ),
        # Add indexes for better performance
        migrations.AddIndex(
            model_name='worklog',
            index=models.Index(fields=['is_deleted'], name='worktime_worklog_is_deleted_idx'),
        ),
        migrations.AddIndex(
            model_name='worklog',
            index=models.Index(fields=['employee', 'is_deleted'], name='worktime_worklog_emp_del_idx'),
        ),
    ]