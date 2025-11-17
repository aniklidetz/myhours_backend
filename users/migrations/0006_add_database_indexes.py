# Generated manually on 2025-01-15
# Adds critical database indexes for performance optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0005_add_token_rotation_fields'),
    ]

    operations = [
        # TokenRefreshLog indexes
        migrations.AddIndex(
            model_name='tokenrefreshlog',
            index=models.Index(fields=['device_token'], name='users_token_device__idx'),
        ),
        migrations.AddIndex(
            model_name='tokenrefreshlog',
            index=models.Index(fields=['device_token', '-refreshed_at'], name='users_token_device_refresh_idx'),
        ),
        migrations.AddIndex(
            model_name='tokenrefreshlog',
            index=models.Index(fields=['-refreshed_at'], name='users_token_refresh_idx'),
        ),

        # BiometricSession indexes
        migrations.AddIndex(
            model_name='biometricsession',
            index=models.Index(fields=['device_token'], name='users_biosess_device_idx'),
        ),
        migrations.AddIndex(
            model_name='biometricsession',
            index=models.Index(fields=['device_token', 'is_active', 'expires_at'], name='users_biosess_device_active_idx'),
        ),
        migrations.AddIndex(
            model_name='biometricsession',
            index=models.Index(fields=['expires_at'], name='users_biosess_expires_idx'),
        ),
        migrations.AddIndex(
            model_name='biometricsession',
            index=models.Index(fields=['-started_at'], name='users_biosess_started_idx'),
        ),

        # Employee indexes (add missing ones)
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['user'], name='users_employee_user_idx'),
        ),
        migrations.AddIndex(
            model_name='employee',
            index=models.Index(fields=['-created_at'], name='users_employee_created_idx'),
        ),
    ]
