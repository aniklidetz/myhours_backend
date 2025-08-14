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

    # Skip if this WorkLog has special handling flags (avoid duplicate processing)
    if (hasattr(instance, "_was_soft_deleted") or 
        hasattr(instance, "_was_restored") or 
        hasattr(instance, "_times_modified")):
        # The enhanced recalculation signal will handle payroll
        logger.debug(f"Skipping notification signal - enhanced signal will handle WorkLog {instance.id}")
        return

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
                
                # Also update monthly summary for regular WorkLog operations
                payroll_service.calculate_monthly_salary_enhanced()
                
                logger.debug(f"Payroll and monthly summary calculated for WorkLog {instance.id} via notification signal")

            except ImportError:
                pass  # Payroll service not available
            except Exception as e:
                # Log the error but don't fail the check-out
                logger.error(
                    f"Failed to calculate payroll for WorkLog {instance.id}: {e}"
                )


@receiver(pre_save, sender=WorkLog)
def handle_worklog_changes(sender, instance, **kwargs):
    """Handle work log changes including soft delete operations and time modifications"""

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
                instance._was_soft_deleted = True
                instance._original_date = original.check_in.date()

            # Check if this is a restore operation
            elif original.is_deleted and not instance.is_deleted:
                logger.info(
                    f"WorkLog {instance.id} is being restored - will trigger payroll recalculation"
                )
                instance._was_restored = True
                instance._original_date = original.check_in.date()

            # Check if times were modified (and it's not deleted)
            elif not instance.is_deleted:
                time_changed = False
                affected_dates = set()

                # Check if check_in time changed (significant change = more than 1 minute)
                if original.check_in != instance.check_in:
                    time_diff = abs((original.check_in - instance.check_in).total_seconds())
                    if time_diff > 60:  # More than 1 minute change
                        time_changed = True
                        affected_dates.add(original.check_in.date())
                        affected_dates.add(instance.check_in.date())
                        logger.info(
                            f"WorkLog {instance.id} check_in changed from {original.check_in} to {instance.check_in} (Δ {time_diff:.0f}s)"
                        )

                # Check if check_out time changed (significant change = more than 1 minute)
                if original.check_out != instance.check_out:
                    if original.check_out and instance.check_out:
                        time_diff = abs((original.check_out - instance.check_out).total_seconds())
                        if time_diff > 60:  # More than 1 minute change
                            time_changed = True
                            affected_dates.add(original.check_out.date())
                            affected_dates.add(instance.check_out.date())
                            logger.info(
                                f"WorkLog {instance.id} check_out changed from {original.check_out} to {instance.check_out} (Δ {time_diff:.0f}s)"
                            )
                    elif original.check_out != instance.check_out:
                        # One is None, the other is not - significant change
                        time_changed = True
                        if original.check_out:
                            affected_dates.add(original.check_out.date())
                        if instance.check_out:
                            affected_dates.add(instance.check_out.date())
                        logger.info(
                            f"WorkLog {instance.id} check_out changed from {original.check_out} to {instance.check_out}"
                        )

                if time_changed:
                    logger.info(
                        f"WorkLog {instance.id} times modified - will trigger payroll recalculation for dates: {affected_dates}"
                    )
                    instance._times_modified = True
                    instance._affected_dates = list(affected_dates)

        except WorkLog.DoesNotExist:
            # Instance doesn't exist yet, skip
            pass


@receiver(post_save, sender=WorkLog)
def handle_payroll_recalculation(sender, instance, created, **kwargs):
    """Handle payroll recalculation for soft delete/restore operations and time modifications"""

    # Check if this was a soft delete, restore, or time modification
    if (hasattr(instance, "_was_soft_deleted") or 
        hasattr(instance, "_was_restored") or 
        hasattr(instance, "_times_modified")):
        
        try:
            from payroll.models import DailyPayrollCalculation
            from payroll.services import EnhancedPayrollCalculationService

            # Determine affected dates
            affected_dates = set()
            
            if hasattr(instance, "_original_date"):
                affected_dates.add(instance._original_date)
            if hasattr(instance, "_affected_dates"):
                affected_dates.update(instance._affected_dates)
            
            # Always include current date
            affected_dates.add(instance.check_in.date())

            # Get employee and year/month for service
            employee = instance.employee
            year = instance.check_in.year
            month = instance.check_in.month

            operation_type = "soft delete" if hasattr(instance, "_was_soft_deleted") else \
                           "restore" if hasattr(instance, "_was_restored") else "time modification"

            logger.info(
                f"Recalculating payroll for employee {employee.get_full_name()} "
                f"for {year}-{month:02d} due to WorkLog {instance.id} {operation_type}"
            )

            # Initialize payroll service
            payroll_service = EnhancedPayrollCalculationService(employee, year, month)

            # Handle specific WorkLog soft delete - remove its calculation immediately
            if hasattr(instance, "_was_soft_deleted"):
                try:
                    deleted_count, _ = DailyPayrollCalculation.objects.filter(
                        worklog=instance
                    ).delete()
                    if deleted_count > 0:
                        logger.info(f"Deleted {deleted_count} payroll calculation(s) for soft-deleted WorkLog {instance.id}")
                except Exception as e:
                    logger.warning(f"Could not delete payroll calculation for WorkLog {instance.id}: {e}")

            # For each affected date, recalculate or clean up
            for affected_date in affected_dates:
                # Get all active worklogs for this date in one query
                date_worklogs = list(WorkLog.objects.filter(
                    employee=employee,
                    check_in__date=affected_date,
                    is_deleted=False
                ))

                if date_worklogs:
                    # Recalculate payroll for this specific date
                    logger.info(f"Recalculating payroll for {affected_date} - has {len(date_worklogs)} active WorkLogs")
                    
                    # Calculate daily pay for each worklog
                    for worklog in date_worklogs:
                        if worklog.check_out:  # Only calculate if worklog is complete
                            payroll_service.calculate_daily_pay(worklog)

                else:
                    # No active WorkLogs for this date - remove all payroll calculations for this date
                    logger.info(f"No active WorkLogs for {affected_date} - removing payroll calculations")
                    
                    # Delete all calculations for this employee and date (shift-based)
                    deleted_count, _ = DailyPayrollCalculation.objects.filter(
                        employee=employee,
                        work_date=affected_date
                    ).delete()
                    
                    if deleted_count > 0:
                        logger.info(f"Deleted {deleted_count} orphaned payroll calculation(s) for {affected_date}")
                    else:
                        logger.info(f"No payroll calculations found for {affected_date} - nothing to clean up")

            # Only recalculate monthly summary if we processed any dates
            if affected_dates:
                result = payroll_service.calculate_monthly_salary_enhanced()
                logger.info(
                    f"Payroll recalculation completed: total ₪{result['total_gross_pay']} for {result['total_hours']}h"
                )

            # Clean up flags
            for flag in ["_was_soft_deleted", "_was_restored", "_times_modified", "_original_date", "_affected_dates"]:
                if hasattr(instance, flag):
                    delattr(instance, flag)

        except ImportError:
            logger.warning("Payroll service not available for recalculation")
        except Exception as e:
            logger.error(
                f"Failed to recalculate payroll after WorkLog {instance.id} change: {e}"
            )
