# Generated manually on 2025-01-15
# Adds critical database indexes for performance optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("biometrics", "0001_initial"),
    ]

    operations = [
        # BiometricAttempt indexes (CRITICAL - rate limiting security)
        migrations.AddIndex(
            model_name="biometricattempt",
            index=models.Index(fields=["ip_address"], name="bio_attempt_ip_idx"),
        ),
        migrations.AddIndex(
            model_name="biometricattempt",
            index=models.Index(
                fields=["ip_address", "blocked_until"],
                name="bio_attempt_ip_blocked_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="biometricattempt",
            index=models.Index(
                fields=["blocked_until"], name="bio_attempt_blocked_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="biometricattempt",
            index=models.Index(fields=["last_attempt"], name="bio_attempt_last_idx"),
        ),
        # BiometricProfile indexes (CRITICAL - N+1 query fix)
        migrations.AddIndex(
            model_name="biometricprofile",
            index=models.Index(fields=["employee"], name="bio_prof_emp_idx"),
        ),
        migrations.AddIndex(
            model_name="biometricprofile",
            index=models.Index(fields=["is_active"], name="bio_prof_active_idx"),
        ),
        migrations.AddIndex(
            model_name="biometricprofile",
            index=models.Index(fields=["-last_updated"], name="bio_prof_updated_idx"),
        ),
        migrations.AddIndex(
            model_name="biometricprofile",
            index=models.Index(fields=["created_at"], name="bio_prof_created_idx"),
        ),
    ]
