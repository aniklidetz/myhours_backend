"""
Simple signals for work time notifications and payroll recalculation
"""

import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import WorkLog

logger = logging.getLogger(__name__)


@receiver(post_save, sender=WorkLog)
def send_work_notifications(sender, instance, created, **kwargs):
    """Send simple notifications when work log is created or updated"""

    # Send notifications only if:
    # 1. New check-in (created=True) - to warn about daily/weekly limits
    # 2. Check-out added (not created, but check_out was just set) - to notify about overtime

    should_notify = False

    if created:
        # New check-in
        should_notify = True
    elif instance.check_out:
        # This is a check-out (instance has check_out time set)
        should_notify = True

    if should_notify:
        # Send simple notifications
        instance.send_simple_notifications()

        # If this is a check-out, trigger payroll calculation
        if instance.check_out:
            try:
                from payroll.services import EnhancedPayrollCalculationService

                # Calculate payroll for this work session
                year = instance.check_in.year
                month = instance.check_in.month

                payroll_service = EnhancedPayrollCalculationService(
                    instance.employee, year, month
                )
                payroll_service.calculate_daily_pay(instance)

            except ImportError:
                pass  # Payroll service not available
            except Exception as e:
                # Log the error but don't fail the check-out
                logger.error(
                    f"Failed to calculate payroll for WorkLog {instance.id}: {e}"
                )


@receiver(pre_save, sender=WorkLog)
def handle_worklog_changes(sender, instance, **kwargs):
    """Handle work log changes including soft delete operations"""

    # Check if this is an existing instance being updated
    if instance.pk:
        try:
            # Get the original instance from database
            original = WorkLog.objects.get(pk=instance.pk)

            # Check if this is a soft delete operation
            if not original.is_deleted and instance.is_deleted:
                logger.info(
                    f"WorkLog {instance.id} is being soft deleted - will trigger payroll recalculation"
                )

                # Store flag to trigger payroll recalculation in post_save
                instance._was_soft_deleted = True

            # Check if this is a restore operation
            elif original.is_deleted and not instance.is_deleted:
                logger.info(
                    f"WorkLog {instance.id} is being restored - will trigger payroll recalculation"
                )

                # Store flag to trigger payroll recalculation in post_save
                instance._was_restored = True

        except WorkLog.DoesNotExist:
            # Instance doesn't exist yet, skip
            pass


@receiver(post_save, sender=WorkLog)
def handle_payroll_recalculation(sender, instance, created, **kwargs):
    """Handle payroll recalculation for soft delete/restore operations"""

    # Check if this was a soft delete or restore operation
    if hasattr(instance, "_was_soft_deleted") or hasattr(instance, "_was_restored"):
        try:
            from payroll.services import EnhancedPayrollCalculationService

            # Recalculate payroll for the affected month
            year = instance.check_in.year
            month = instance.check_in.month

            logger.info(
                f"Recalculating payroll for employee {instance.employee.get_full_name()} "
                f"for {year}-{month:02d} due to WorkLog {instance.id} {'soft delete' if hasattr(instance, '_was_soft_deleted') else 'restore'}"
            )

            payroll_service = EnhancedPayrollCalculationService(
                instance.employee, year, month
            )
            result = payroll_service.calculate_monthly_salary_enhanced()

            logger.info(
                f"Payroll recalculation completed: total ₪{result['total_gross_pay']} for {result['total_hours']}h"
            )

            # Clean up flags
            if hasattr(instance, "_was_soft_deleted"):
                delattr(instance, "_was_soft_deleted")
            if hasattr(instance, "_was_restored"):
                delattr(instance, "_was_restored")

        except ImportError:
            logger.warning("Payroll service not available for recalculation")
        except Exception as e:
            logger.error(
                f"Failed to recalculate payroll after WorkLog {instance.id} change: {e}"
            )
