# Generated by Django 5.1.10 on 2025-07-23 12:48

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_biometricsession_devicetoken_employeeinvitation_and_more'),
        ('worktime', '0002_add_soft_delete_only'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='worklog',
            options={'ordering': ['-check_in'], 'verbose_name': 'Work Log', 'verbose_name_plural': 'Work Logs'},
        ),
        migrations.RemoveIndex(
            model_name='worklog',
            name='worktime_worklog_is_deleted_idx',
        ),
        migrations.RemoveIndex(
            model_name='worklog',
            name='worktime_worklog_emp_del_idx',
        ),
        migrations.AddField(
            model_name='worklog',
            name='is_approved',
            field=models.BooleanField(default=False, help_text='Whether this work log has been approved by manager'),
        ),
        migrations.AddField(
            model_name='worklog',
            name='notes',
            field=models.TextField(blank=True, help_text='Optional notes about this work session'),
        ),
        migrations.AddField(
            model_name='worklog',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name='worklog',
            name='check_in',
            field=models.DateTimeField(help_text='When the employee started work'),
        ),
        migrations.AlterField(
            model_name='worklog',
            name='check_out',
            field=models.DateTimeField(blank=True, help_text='When the employee finished work', null=True),
        ),
        migrations.AlterField(
            model_name='worklog',
            name='employee',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='work_logs', to='users.employee'),
        ),
        migrations.AlterField(
            model_name='worklog',
            name='location_check_in',
            field=models.CharField(blank=True, help_text='Location where check-in occurred', max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='worklog',
            name='location_check_out',
            field=models.CharField(blank=True, help_text='Location where check-out occurred', max_length=255, null=True),
        ),
        migrations.AddIndex(
            model_name='worklog',
            index=models.Index(fields=['employee', 'check_in'], name='worktime_wo_employe_ee1084_idx'),
        ),
        migrations.AddIndex(
            model_name='worklog',
            index=models.Index(fields=['check_in'], name='worktime_wo_check_i_643a20_idx'),
        ),
        migrations.AddIndex(
            model_name='worklog',
            index=models.Index(fields=['is_approved'], name='worktime_wo_is_appr_0ce77a_idx'),
        ),
    ]
