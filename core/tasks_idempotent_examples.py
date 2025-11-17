"""
Examples of Celery tasks with idempotency protection

This file demonstrates how to apply idempotency decorators to existing tasks.
Copy these patterns to core/tasks.py for production use.
"""

from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

from core.idempotency import idempotent_daily_task, idempotent_once, idempotent_task

import logging

logger = logging.getLogger(__name__)

# Define transient errors
TRANSIENT_ERRORS = (Exception,)  # Simplified for example


# EXAMPLE 1: Daily cleanup task (should run once per day)
@shared_task(
    bind=True,
    autoretry_for=TRANSIENT_ERRORS,
    retry_backoff=True,
    max_retries=3,
    name="core.tasks.cleanup_old_logs_idempotent",
)
@idempotent_daily_task(ttl_hours=48)  # Can run once per day, key expires in 48h
def cleanup_old_logs_idempotent(self):
    """
    Clean up old log files - with idempotency protection.

    If task retries after partial completion, it won't delete files again.
    """
    logger.info("Starting cleanup of old logs (idempotent)")

    # Task logic here
    cleaned_files = 10  # Example result

    result = {
        "cleaned_files": cleaned_files,
        "completed_at": timezone.now().isoformat(),
    }

    logger.info(f"Cleanup completed: {result}")
    return result


# EXAMPLE 2: Report generation (should not create duplicates)
@shared_task(
    bind=True,
    autoretry_for=TRANSIENT_ERRORS,
    retry_backoff=True,
    max_retries=2,
    name="core.tasks.generate_reports_idempotent",
)
@idempotent_daily_task(ttl_hours=48)
def generate_reports_idempotent(self):
    """
    Generate daily reports - with idempotency protection.

    Prevents duplicate reports if task retries.
    """
    logger.info("Starting report generation (idempotent)")

    # Generate report
    report_data = {
        "date": timezone.now().date().isoformat(),
        "active_employees": 100,
        "work_sessions": 250,
    }

    logger.info(f"Report generated: {report_data}")
    return report_data


# EXAMPLE 3: Alert sending (critical - must not send duplicates)
@shared_task(
    bind=True,
    autoretry_for=TRANSIENT_ERRORS,
    max_retries=5,
    name="core.tasks.send_critical_alert_idempotent",
)
@idempotent_once(ttl_hours=24)  # Same alert can't be sent twice in 24h
def send_critical_alert_idempotent(self, alert_type, message, recipients=None):
    """
    Send critical alerts - with idempotency protection.

    CRITICAL: Prevents duplicate alert emails on retry.
    Uses alert_type + message as idempotency key.
    """
    if recipients is None:
        recipients = getattr(settings, "CELERY_ADMIN_EMAILS", ["admin@myhours.com"])

    subject = f"CRITICAL ALERT: {alert_type}"

    # In production, actually send email
    logger.critical(f"Sending alert: {alert_type} - {message}")

    # Simulated email send
    # send_mail(subject=subject, message=message, ...)

    result = {
        "alert_type": alert_type,
        "message": message,
        "sent_at": timezone.now().isoformat(),
        "recipients": recipients,
    }

    logger.critical(f"Critical alert sent: {alert_type}")
    return result


# EXAMPLE 4: Task with custom TTL and specific arguments
@shared_task(
    bind=True,
    autoretry_for=TRANSIENT_ERRORS,
    max_retries=2,
    name="core.tasks.process_employee_payroll_idempotent",
)
@idempotent_task(
    ttl_hours=72, date_based=False  # 3 days retention  # Based on employee_id + month
)
def process_employee_payroll_idempotent(self, employee_id, year, month):
    """
    Process payroll for specific employee and month.

    Idempotency key includes employee_id, year, month.
    Won't process same employee/month twice within 72 hours.
    """
    logger.info(f"Processing payroll for employee {employee_id}, {year}-{month:02d}")

    # Payroll calculation logic here
    result = {
        "employee_id": employee_id,
        "year": year,
        "month": month,
        "total_salary": 5000.00,
        "processed_at": timezone.now().isoformat(),
    }

    logger.info(f"Payroll processed: {result}")
    return result


# EXAMPLE 5: Security alert monitoring (should run once per hour)
@shared_task(
    bind=True,
    autoretry_for=TRANSIENT_ERRORS,
    retry_backoff=True,
    max_retries=3,
    name="core.tasks.monitor_security_alerts_idempotent",
)
@idempotent_task(
    ttl_hours=2,  # 2 hour retention
    date_based=True,  # Include current date/hour
)
def monitor_security_alerts_idempotent(self, max_unresolved=50):
    """
    Monitor security alerts - with idempotency protection.

    Task can run multiple times per day but won't send duplicate
    alert summaries within the TTL window.
    """
    logger.info("Starting security alert monitoring (idempotent)")

    # Check for unresolved alerts
    unresolved_count = 10  # Example
    critical_count = 2

    # Send summary if needed (only once within TTL)
    if critical_count > 0:
        # This will also be idempotent
        send_critical_alert_idempotent.delay(
            alert_type="Critical Security Alerts",
            message=f"{critical_count} critical alerts require attention",
        )

    result = {
        "unresolved_alerts": unresolved_count,
        "critical_alerts": critical_count,
        "timestamp": timezone.now().isoformat(),
    }

    logger.info(f"Security monitoring completed: {result}")
    return result


# EXAMPLE 6: Task that should fail on duplicate (strict mode)
@shared_task(
    bind=True,
    max_retries=1,
    name="core.tasks.strict_one_time_task",
)
@idempotent_task(
    ttl_hours=24, date_based=True, skip_on_duplicate=False  # Raise error on duplicate
)
def strict_one_time_task(self, important_data):
    """
    Task that must run exactly once - raises error on duplicate.

    Use skip_on_duplicate=False for tasks where duplicate execution
    would be catastrophic (e.g., financial transactions).
    """
    logger.info(f"Processing one-time task with data: {important_data}")

    # Critical operation here
    result = {"processed": True, "data": important_data}

    return result
