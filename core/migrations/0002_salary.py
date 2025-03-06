# Generated by Django 5.1.6 on 2025-02-28 21:14

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Salary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('base_salary', models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ('hourly_rate', models.DecimalField(blank=True, decimal_places=2, default=0.0, max_digits=10, null=True)),
                ('bonus', models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ('deductions', models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ('calculated_salary', models.DecimalField(decimal_places=2, default=0.0, max_digits=10)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('currency', models.CharField(choices=[('NIS', 'New Israeli Shekel'), ('USD', 'US Dollar'), ('EUR', 'Euro')], default='NIS', max_length=3)),
                ('employee', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='core.employee')),
            ],
        ),
    ]
