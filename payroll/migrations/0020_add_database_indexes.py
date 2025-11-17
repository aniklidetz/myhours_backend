# Generated manually on 2025-01-15
# Adds critical database indexes for performance optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payroll', '0019_add_proportional_monthly_to_daily'),
    ]

    operations = [
        # Salary indexes (CRITICAL - payroll calculation bottleneck)
        migrations.AddIndex(
            model_name='salary',
            index=models.Index(fields=['employee', 'is_active'], name='payroll_salary_emp_active_idx'),
        ),
        migrations.AddIndex(
            model_name='salary',
            index=models.Index(fields=['employee'], name='payroll_salary_emp_idx'),
        ),
        migrations.AddIndex(
            model_name='salary',
            index=models.Index(fields=['is_active'], name='payroll_salary_active_idx'),
        ),
        migrations.AddIndex(
            model_name='salary',
            index=models.Index(fields=['-created_at'], name='payroll_salary_created_idx'),
        ),

        # CompensatoryDay indexes (HIGH priority)
        migrations.AddIndex(
            model_name='compensatoryday',
            index=models.Index(fields=['employee', 'date_used'], name='payroll_compday_emp_used_idx'),
        ),
        migrations.AddIndex(
            model_name='compensatoryday',
            index=models.Index(fields=['employee'], name='payroll_compday_emp_idx'),
        ),
        migrations.AddIndex(
            model_name='compensatoryday',
            index=models.Index(fields=['-date_earned'], name='payroll_compday_earned_idx'),
        ),
    ]
