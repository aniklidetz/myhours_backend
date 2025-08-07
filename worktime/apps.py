from django.apps import AppConfig


class WorktimeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "worktime"

    def ready(self):
        try:
            import worktime.simple_signals  # noqa: F401
        except ImportError:
            # Handle missing signals module gracefully in CI
            pass
