# Generated manually on 2025-01-15
# Adds critical database indexes for performance optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('biometrics', '0001_initial'),
    ]

    operations = [
        # BiometricAttempt indexes (CRITICAL - rate limiting security)
        migrations.AddIndex(
            model_name='biometricattempt',
            index=models.Index(fields=['ip_address'], name='biometrics_attempt_ip_idx'),
        ),
        migrations.AddIndex(
            model_name='biometricattempt',
            index=models.Index(fields=['ip_address', 'blocked_until'], name='biometrics_attempt_ip_blocked_idx'),
        ),
        migrations.AddIndex(
            model_name='biometricattempt',
            index=models.Index(fields=['blocked_until'], name='biometrics_attempt_blocked_idx'),
        ),
        migrations.AddIndex(
            model_name='biometricattempt',
            index=models.Index(fields=['last_attempt'], name='biometrics_attempt_last_idx'),
        ),

        # BiometricProfile indexes (CRITICAL - N+1 query fix)
        migrations.AddIndex(
            model_name='biometricprofile',
            index=models.Index(fields=['employee'], name='biometrics_profile_employee_idx'),
        ),
        migrations.AddIndex(
            model_name='biometricprofile',
            index=models.Index(fields=['is_active'], name='biometrics_profile_active_idx'),
        ),
        migrations.AddIndex(
            model_name='biometricprofile',
            index=models.Index(fields=['-last_updated'], name='biometrics_profile_updated_idx'),
        ),
        migrations.AddIndex(
            model_name='biometricprofile',
            index=models.Index(fields=['created_at'], name='biometrics_profile_created_idx'),
        ),
    ]
