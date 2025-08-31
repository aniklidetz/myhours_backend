"""
Core Celery tasks for MyHours application
Demonstrates production-ready task patterns with retry strategies
"""

import glob
import logging
import os
from datetime import datetime, timedelta
from smtplib import SMTPException, SMTPServerDisconnected
from unittest.mock import patch  # Import patch at module level as requested

from celery import shared_task

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import OperationalError
from django.utils import timezone

logger = logging.getLogger(__name__)

# Define transient errors that should trigger automatic retries
TRANSIENT_ERRORS = (
    OperationalError,
    OSError,
    IOError,
    ConnectionError,
    SMTPException,
    SMTPServerDisconnected,
)


@shared_task(
    bind=True,
    autoretry_for=TRANSIENT_ERRORS,
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
    name="core.tasks.cleanup_old_logs",
)
def cleanup_old_logs(self):
    """
    Clean up old log files and database entries
    Runs daily on low priority queue
    """
    try:
        logger.info("Starting cleanup of old logs")

        # Cleanup old log files (keep last 30 days)
        log_dir = settings.BASE_DIR / "logs"
        cutoff_date = timezone.now() - timedelta(days=30)

        cleaned_files = 0
        for log_file in glob.glob(str(log_dir / "*.log*")):
            try:
                file_stat = os.stat(log_file)
                file_date = datetime.fromtimestamp(
                    file_stat.st_mtime, tz=timezone.now().tzinfo
                )

                if file_date < cutoff_date:
                    os.remove(log_file)
                    cleaned_files += 1
                    logger.info(f"Removed old log file: {log_file}")
            except (OSError, IOError) as e:
                logger.warning(f"Failed to remove log file {log_file}: {e}")

        # Cleanup old database sessions (keep last 7 days)
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM django_session 
                WHERE expire_date < %s
            """,
                [timezone.now() - timedelta(days=7)],
            )

            deleted_sessions = cursor.rowcount

        result = {
            "cleaned_files": cleaned_files,
            "deleted_sessions": deleted_sessions,
            "completed_at": timezone.now().isoformat(),
        }

        logger.info(f"Cleanup completed: {result}")
        return result

    except (OperationalError, OSError, IOError) as exc:
        logger.error(f"Cleanup task failed: {exc}")
        # autoretry_for will handle the retry automatically
        raise


@shared_task(
    bind=True,
    autoretry_for=TRANSIENT_ERRORS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
    default_retry_delay=300,  # 5 minutes
    name="core.tasks.generate_reports",
)
def generate_reports(self):
    """
    Generate daily/weekly reports
    Low priority background task
    """
    try:
        from users.models import Employee
        from worktime.models import WorkLog

        logger.info("Starting report generation")

        # Generate daily stats
        today = timezone.now().date()
        active_employees = Employee.objects.filter(is_active=True).count()

        # Count today's work sessions
        work_sessions = WorkLog.objects.filter(check_in__date=today).count()

        report_data = {
            "date": today.isoformat(),
            "active_employees": active_employees,
            "work_sessions": work_sessions,
            "generated_at": timezone.now().isoformat(),
        }

        # In production, you might save this to a ReportsModel or send via email
        logger.info(f"Report generated: {report_data}")

        return report_data

    except (OperationalError, OSError, ImportError) as exc:
        logger.error(f"Report generation failed: {exc}")
        # autoretry_for will handle the retry automatically
        raise


@shared_task(
    bind=True, max_retries=1, name="core.tasks.process_dead_letter", queue="failed"
)
def process_dead_letter(self, original_task_id, error_message, traceback_info):
    """
    Process tasks that have been routed to dead letter queue
    This task should not retry (max_retries=1)
    """
    try:
        logger.critical(
            f"Processing dead letter task: {original_task_id}",
            extra={
                "original_task_id": original_task_id,
                "error_message": error_message,
                "traceback": traceback_info,
            },
        )

        # Store in database for manual review
        # In production, you'd have a FailedTaskModel
        dead_letter_data = {
            "original_task_id": original_task_id,
            "error_message": error_message,
            "traceback": traceback_info,
            "processed_at": timezone.now().isoformat(),
        }

        # Send alert to administrators
        if hasattr(settings, "CELERY_ADMIN_EMAILS"):
            try:
                send_mail(
                    subject=f"Dead Letter Queue: Task {original_task_id} Failed",
                    message=f"""
Task ID: {original_task_id}
Error: {error_message}

Traceback:
{traceback_info}

This task has been moved to the dead letter queue for manual review.
                    """.strip(),
                    from_email=getattr(
                        settings, "DEFAULT_FROM_EMAIL", "noreply@myhours.com"
                    ),
                    recipient_list=settings.CELERY_ADMIN_EMAILS,
                    fail_silently=False,
                )
                logger.info(f"Dead letter alert sent for task {original_task_id}")
            except Exception as e:
                logger.error(f"Failed to send dead letter alert: {e}")

        return dead_letter_data

    except Exception as exc:
        # Critical: If dead letter processing fails, log but don't retry
        logger.critical(f"Dead letter processing failed for {original_task_id}: {exc}")
        return {"status": "failed", "error": str(exc)}


@shared_task(
    bind=True,
    autoretry_for=TRANSIENT_ERRORS,
    max_retries=5,
    default_retry_delay=30,  # Fast retry for critical tasks
    name="core.tasks.send_critical_alert",
)
def send_critical_alert(self, alert_type, message, recipients=None):
    """
    Send critical system alerts
    High priority task with aggressive retries
    """
    try:
        if recipients is None:
            recipients = getattr(settings, "CELERY_ADMIN_EMAILS", ["admin@myhours.com"])

        subject = f"CRITICAL ALERT: {alert_type}"

        send_mail(
            subject=subject,
            message=f"""
CRITICAL SYSTEM ALERT

Type: {alert_type}
Time: {timezone.now().isoformat()}
Message: {message}

This is an automated alert from the MyHours system.
            """.strip(),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@myhours.com"),
            recipient_list=recipients,
            fail_silently=False,
        )

        logger.critical(f"Critical alert sent: {alert_type} - {message}")

        return {
            "alert_type": alert_type,
            "message": message,
            "sent_at": timezone.now().isoformat(),
            "recipients": recipients,
        }

    except (SMTPException, OSError, ConnectionError) as exc:
        logger.error(f"Failed to send critical alert {alert_type}: {exc}")
        # Manual retry with exponential backoff
        retry_count = self.request.retries
        # Calculate exponential backoff: 30, 60, 120, 240, 480 seconds
        countdown = min(30 * (2**retry_count), 480)
        # Add jitter to prevent thundering herd
        import random

        countdown = countdown + random.randint(0, 10)

        raise self.retry(exc=exc, countdown=countdown)


@shared_task(
    bind=True,
    autoretry_for=TRANSIENT_ERRORS,
    retry_backoff=2,  # Exponential backoff: 2, 4, 8, 16...
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
    name="core.tasks.health_check",
)
def health_check(self):
    """
    System health check task
    Monitors critical system components
    """
    try:
        logger.info("Starting system health check")

        health_status = {
            "timestamp": timezone.now().isoformat(),
            "database": False,
            "cache": False,
            "mongo": False,
            "overall": False,
        }

        # Test database connection with explicit retry on failure
        try:
            from django.db import connection

            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                health_status["database"] = True
        except OperationalError as exc:
            logger.warning("DB health failed, scheduling retry", exc_info=True)
            # Explicit retry call that the test expects
            raise self.retry(exc=exc)

        # Test cache connection
        try:
            cache.set("health_check", "ok", 60)
            cache.get("health_check")
            health_status["cache"] = True
        except (OSError, ConnectionError) as e:
            logger.error(f"Cache health check failed: {e}")

        # Test MongoDB connection
        try:
            if hasattr(settings, "MONGO_CLIENT") and settings.MONGO_CLIENT:
                settings.MONGO_CLIENT.admin.command("ping")
                health_status["mongo"] = True
        except (OSError, ConnectionError) as e:
            logger.error(f"MongoDB health check failed: {e}")

        # Overall health
        health_status["overall"] = all(
            [
                health_status["database"],
                health_status["cache"],
                # MongoDB is optional, don't require it for overall health
            ]
        )

        if not health_status["overall"]:
            # Send alert if system is unhealthy
            send_critical_alert.delay(
                alert_type="System Health Check Failed",
                message=f"System health check failed: {health_status}",
            )

        logger.info(f"Health check completed: {health_status}")
        return health_status

    except Exception as exc:
        logger.exception("health_check failed", extra={"task": "health_check"})
        # Re-raise to trigger autoretry_for if it's a transient error
        raise


# === JWT TOKEN SECURITY CLEANUP TASKS ===


@shared_task(
    bind=True,
    autoretry_for=TRANSIENT_ERRORS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
    default_retry_delay=300,  # 5 minutes
    name="core.tasks.cleanup_expired_tokens",
)
def cleanup_expired_tokens(self, days_to_keep=30):
    """
    Clean up expired device tokens while preserving audit trail
    Runs daily to maintain database hygiene

    Priority: LOW (queue: 'low')
    """
    try:
        from users.token_models import DeviceToken

        logger.info("Starting expired token cleanup")

        # Clean expired tokens older than specified days
        cleaned_count = DeviceToken.cleanup_expired_tokens(days_to_keep=days_to_keep)

        result = {
            "status": "completed",
            "cleaned_tokens": cleaned_count,
            "days_to_keep": days_to_keep,
            "timestamp": timezone.now().isoformat(),
        }

        if cleaned_count > 0:
            logger.info(
                f"Cleaned {cleaned_count} expired tokens older than {days_to_keep} days"
            )
        else:
            logger.info("No expired tokens to clean")

        return result

    except (OperationalError, OSError, ImportError) as exc:
        logger.error(f"Expired token cleanup failed: {exc}")
        # autoretry_for will handle the retry automatically
        raise


@shared_task(
    bind=True,
    autoretry_for=TRANSIENT_ERRORS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
    default_retry_delay=300,
    name="core.tasks.cleanup_compromised_token_families",
)
def cleanup_compromised_token_families(self, hours_to_keep=72):
    """
    Clean up compromised token families after grace period
    Runs every 6 hours to maintain security hygiene

    Priority: NORMAL (queue: 'normal')
    """
    try:
        from users.token_models import DeviceToken

        logger.info("Starting compromised token family cleanup")

        # Clean compromised families older than specified hours
        cleaned_count = DeviceToken.cleanup_compromised_families(
            hours_to_keep=hours_to_keep
        )

        result = {
            "status": "completed",
            "cleaned_compromised": cleaned_count,
            "hours_to_keep": hours_to_keep,
            "timestamp": timezone.now().isoformat(),
        }

        if cleaned_count > 0:
            logger.warning(
                f"Cleaned {cleaned_count} compromised tokens older than {hours_to_keep} hours"
            )

            # Send security notification for compromised token cleanup
            send_critical_alert.delay(
                alert_type="Compromised Token Cleanup",
                message=f"Cleaned {cleaned_count} compromised token families. "
                f"Review security logs for potential threats.",
            )
        else:
            logger.info("No compromised token families to clean")

        return result

    except (OperationalError, OSError, ImportError) as exc:
        logger.error(f"Compromised token cleanup failed: {exc}")
        # autoretry_for will handle the retry automatically
        raise


@shared_task(
    bind=True,
    autoretry_for=TRANSIENT_ERRORS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    default_retry_delay=120,
    name="core.tasks.monitor_token_security_alerts",
)
def monitor_token_security_alerts(self, max_unresolved_alerts=50):
    """
    Monitor and report on unresolved security alerts
    Runs hourly to ensure security incidents are addressed

    Priority: HIGH (queue: 'high')
    """
    try:
        from django.db.models import Count, Q

        from users.token_models import TokenSecurityAlert

        logger.info("Starting token security alert monitoring")

        # Get unresolved alerts
        unresolved_alerts = TokenSecurityAlert.objects.filter(is_resolved=False)
        unresolved_count = unresolved_alerts.count()

        # Get critical unresolved alerts
        critical_alerts = unresolved_alerts.filter(severity="critical")
        critical_count = critical_alerts.count()

        # Get old unresolved alerts (> 24 hours)
        old_threshold = timezone.now() - timedelta(hours=24)
        old_alerts = unresolved_alerts.filter(created_at__lt=old_threshold)
        old_count = old_alerts.count()

        # Get alert type breakdown
        alert_breakdown = (
            unresolved_alerts.values("alert_type")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        result = {
            "status": "completed",
            "unresolved_alerts": unresolved_count,
            "critical_alerts": critical_count,
            "old_alerts": old_count,
            "alert_breakdown": list(alert_breakdown),
            "timestamp": timezone.now().isoformat(),
        }

        # Send alerts for concerning situations
        if critical_count > 0:
            send_critical_alert.delay(
                alert_type="Critical Security Alerts",
                message=f"{critical_count} critical security alerts require immediate attention. "
                f"Types: {[item['alert_type'] for item in alert_breakdown[:3]]}",
            )

        if unresolved_count > max_unresolved_alerts:
            send_critical_alert.delay(
                alert_type="High Volume Security Alerts",
                message=f"{unresolved_count} unresolved security alerts exceed threshold of {max_unresolved_alerts}. "
                f"Review and resolve alerts to maintain security posture.",
            )

        if old_count > 10:
            send_critical_alert.delay(
                alert_type="Stale Security Alerts",
                message=f"{old_count} security alerts are older than 24 hours without resolution. "
                f"Ensure security team is reviewing and addressing alerts promptly.",
            )

        logger.info(f"Security alert monitoring completed: {result}")
        return result

    except (OperationalError, OSError, ImportError) as exc:
        logger.error(f"Security alert monitoring failed: {exc}")
        # autoretry_for will handle the retry automatically
        raise


@shared_task(
    bind=True,
    autoretry_for=TRANSIENT_ERRORS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=1,
    default_retry_delay=60,
    name="core.tasks.generate_security_report",
)
def generate_security_report(self, days_back=7):
    """
    Generate weekly security report for token-related incidents
    Runs weekly to provide security insights

    Priority: LOW (queue: 'low')
    """
    try:
        from django.db.models import Count, Q

        from users.token_models import DeviceToken, TokenRotationLog, TokenSecurityAlert

        logger.info("Starting security report generation")

        # Date range for report
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days_back)

        # Security alerts in period
        alerts_in_period = TokenSecurityAlert.objects.filter(
            created_at__range=[start_date, end_date]
        )

        # Token rotations in period
        rotations_in_period = TokenRotationLog.objects.filter(
            rotated_at__range=[start_date, end_date]
        )

        # Active token families
        active_families = (
            DeviceToken.objects.filter(is_active=True, is_compromised=False)
            .values("rotation_family")
            .distinct()
            .count()
        )

        # Compromised families in period
        compromised_in_period = (
            DeviceToken.objects.filter(
                is_compromised=True, compromised_at__range=[start_date, end_date]
            )
            .values("rotation_family")
            .distinct()
            .count()
        )

        report = {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": days_back,
            },
            "security_alerts": {
                "total": alerts_in_period.count(),
                "by_type": list(
                    alerts_in_period.values("alert_type")
                    .annotate(count=Count("id"))
                    .order_by("-count")
                ),
                "by_severity": list(
                    alerts_in_period.values("severity")
                    .annotate(count=Count("id"))
                    .order_by("-count")
                ),
                "resolved": alerts_in_period.filter(is_resolved=True).count(),
            },
            "token_rotations": {
                "total": rotations_in_period.count(),
                "by_reason": list(
                    rotations_in_period.values("rotation_reason")
                    .annotate(count=Count("id"))
                    .order_by("-count")
                ),
                "unique_families": rotations_in_period.values("rotation_family")
                .distinct()
                .count(),
            },
            "token_families": {
                "active": active_families,
                "compromised_in_period": compromised_in_period,
                "compromise_rate": round(
                    (compromised_in_period / max(active_families, 1)) * 100, 2
                ),
            },
            "generated_at": timezone.now().isoformat(),
        }

        logger.info(
            f"Security report generated: {report['security_alerts']['total']} alerts, "
            f"{report['token_rotations']['total']} rotations, "
            f"{report['token_families']['compromised_in_period']} families compromised"
        )

        # Send report via email if there are security incidents
        if (
            report["security_alerts"]["total"] > 0
            or report["token_families"]["compromised_in_period"] > 0
        ):

            send_critical_alert.delay(
                alert_type="Weekly Security Report",
                message=f"Security Report ({days_back} days): "
                f"{report['security_alerts']['total']} alerts, "
                f"{report['token_families']['compromised_in_period']} families compromised. "
                f"Compromise rate: {report['token_families']['compromise_rate']}%",
            )

        return report

    except (OperationalError, OSError, ImportError) as exc:
        logger.error(f"Security report generation failed: {exc}")
        # autoretry_for will handle the retry automatically
        raise
