# Generated by Django 5.1.6 on 2025-03-15 14:48

import datetime
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payroll', '0001_initial'),
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='salary',
            name='bonus',
        ),
        migrations.RemoveField(
            model_name='salary',
            name='calculated_salary',
        ),
        migrations.RemoveField(
            model_name='salary',
            name='deductions',
        ),
        migrations.AddField(
            model_name='salary',
            name='calculation_type',
            field=models.CharField(choices=[('hourly', 'Hourly'), ('monthly', 'Monthly'), ('project', 'Project-based')], default='hourly', max_length=10),
        ),
        migrations.AddField(
            model_name='salary',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=datetime.datetime(2025, 3, 15, 14, 47, 31, 364097, tzinfo=datetime.timezone.utc)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='salary',
            name='project_completed',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='salary',
            name='project_end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='salary',
            name='project_start_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='salary',
            name='base_salary',
            field=models.DecimalField(decimal_places=2, help_text='Monthly rate or total project cost', max_digits=10, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name='salary',
            name='currency',
            field=models.CharField(choices=[('ILS', 'Israeli Shekel'), ('USD', 'US Dollar'), ('EUR', 'Euro')], default='ILS', max_length=3),
        ),
        migrations.AlterField(
            model_name='salary',
            name='employee',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='salary_info', to='users.employee'),
        ),
        migrations.AlterField(
            model_name='salary',
            name='hourly_rate',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Hourly rate', max_digits=6, validators=[django.core.validators.MinValueValidator(0)]),
            preserve_default=False,
        ),
        migrations.CreateModel(
            name='CompensatoryDay',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_earned', models.DateField()),
                ('reason', models.CharField(choices=[('shabbat', 'Shabbat work'), ('holiday', 'Holiday work')], max_length=50)),
                ('date_used', models.DateField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='compensatory_days', to='users.employee')),
            ],
            options={
                'verbose_name': 'Compensatory Day',
                'verbose_name_plural': 'Compensatory Days',
                'ordering': ['-date_earned'],
            },
        ),
    ]
