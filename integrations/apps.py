from django.apps import AppConfig
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


class IntegrationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations"

    def ready(self):
        """
        Called when Django starts. Schedule holiday synchronization for later.
        """
        # Import here to avoid circular imports
        import threading
        from django.db import connections

        def delayed_holiday_sync():
            """Run holiday sync after Django is fully ready"""
            try:
                # Wait for Django to be fully ready
                import time

                time.sleep(2)

                from datetime import date
                from .services.hebcal_service import HebcalService

                # Check if holidays need synchronization
                sync_key = "holidays_auto_sync_check"
                cache_timeout = 60 * 60 * 24 * 7  # 7 days

                if not cache.get(sync_key):
                    logger.info("Automatic holiday synchronization started")

                    # Sync current and next year
                    current_year = date.today().year
                    for year in [current_year, current_year + 1]:
                        try:
                            created, updated = HebcalService.sync_holidays_to_db(year)
                            logger.info(
                                f"Auto-synced holidays for {year}: {created} created, {updated} updated"
                            )
                        except Exception as e:
                            logger.error(f"Error auto-syncing holidays for {year}: {e}")

                    # Set cache flag to prevent re-sync for 7 days
                    cache.set(sync_key, True, cache_timeout)
                    logger.info(
                        "Holiday synchronization completed, next sync in 7 days"
                    )
                else:
                    logger.debug(
                        "Holiday synchronization skipped - already synced within 7 days"
                    )

            except Exception as e:
                logger.error(f"Error in automatic holiday synchronization: {e}")
            finally:
                # Close database connections in this thread
                connections.close_all()

        # Only run auto-sync if not in test mode
        import sys

        if (
            "test" not in sys.argv
            and "migrate" not in sys.argv
            and "makemigrations" not in sys.argv
            and "shell" not in sys.argv
        ):
            # Start sync in background thread to avoid database access warning
            thread = threading.Thread(target=delayed_holiday_sync, daemon=True)
            thread.start()
