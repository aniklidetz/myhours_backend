"""
Simplified notification system - just push notifications for warnings
"""

import logging
from datetime import timedelta

from django.utils import timezone


logger = logging.getLogger(__name__)


class SimpleNotificationService:
    """Simple push notification service for work hour warnings"""

    @staticmethod
    def check_daily_hours(employee, work_log):
        """Check if employee is approaching daily limits and send push if needed"""

        # Skip notifications during tests
        import sys

        if "test" in sys.argv:
            return

        # Calculate today's total hours
        today = work_log.check_in.date()
        from worktime.models import WorkLog

        today_logs = WorkLog.objects.filter(
            employee=employee, check_in__date=today, check_out__isnull=False
        )

        total_hours = sum(log.get_total_hours() for log in today_logs)

        # Add current session if still checked in
        if not work_log.check_out:
            from decimal import Decimal

            current_hours = (timezone.now() - work_log.check_in).total_seconds() / 3600
            total_hours += Decimal(str(current_hours))

        # Send warnings at different thresholds
        if total_hours >= 11.5:
            SimpleNotificationService._send_push(
                employee,
                title="⚠️ Approaching Daily Limit",
                message=f"You have worked {total_hours:.1f} hours today. Consider ending your workday.",
            )
        elif total_hours >= 10:
            SimpleNotificationService._send_push(
                employee,
                title="Long Workday",
                message=f"You have worked {total_hours:.1f} hours. Don't forget to rest!",
            )
        elif total_hours >= 8 and work_log.check_out:
            # Notify about overtime only when checking out
            overtime = total_hours - 8
            SimpleNotificationService._send_push(
                employee,
                title="Overtime Hours",
                message=f"Today you worked {overtime:.1f} hours of overtime.",
            )

    @staticmethod
    def check_weekly_hours(employee):
        """Check weekly hours and notify if high"""

        # Skip notifications during tests
        import sys

        if "test" in sys.argv:
            return

        from worktime.models import WorkLog

        # Get current week start
        today = timezone.now().date()
        week_start = today - timedelta(days=today.weekday())

        weekly_logs = WorkLog.objects.filter(
            employee=employee,
            check_in__date__gte=week_start,
            check_in__date__lte=today,
            check_out__isnull=False,
        )

        total_hours = sum(log.get_total_hours() for log in weekly_logs)

        # Israeli labor law: maximum 60 hours per week with overtime approval
        if total_hours >= 60:
            SimpleNotificationService._send_push(
                employee,
                title="🚨 Critical Weekly Hours",
                message=f"You have worked {total_hours:.0f} hours this week. This exceeds recommended limits and may require manager approval.",
            )
        elif total_hours >= 55:
            SimpleNotificationService._send_push(
                employee,
                title="⚠️ High Weekly Workload",
                message=f"You have worked {total_hours:.0f} hours this week. Please maintain work-life balance.",
            )

    @staticmethod
    def notify_holiday_work(employee, holiday_name):
        """Notify about working on holiday"""

        # Skip notifications during tests
        import sys

        if "test" in sys.argv:
            return

        SimpleNotificationService._send_push(
            employee,
            title="Holiday Work",
            message=f"You are working on {holiday_name}. You are entitled to compensatory time off or premium pay.",
        )

    @staticmethod
    def _send_push(employee, title, message):
        """Send push notification (placeholder)"""
        # TODO: Integrate with real push service (Firebase, OneSignal, etc.)
        logger.info(
            "Push notification sent",
            extra={
                "employee_id": getattr(employee, "id", None),
                "user_id": getattr(employee, "user_id", None),
                "notification_type": "push",
            },
        )

        # For now, just log it safely
        from core.logging_utils import mask_name

        print(f"\n📱 PUSH NOTIFICATION")
        print(
            f"   To: {mask_name(employee.get_full_name()) if employee.get_full_name() else '[employee]'}"
        )
        print(f"   Title: {title}")
        print(f"   Message: {message}")

        # Here you would call your push notification service
        # Example:
        # firebase_token = employee.device_token
        # if firebase_token:
        #     send_firebase_notification(firebase_token, title, message)
