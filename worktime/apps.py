from django.apps import AppConfig


class WorktimeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'worktime'

    def ready(self):
        import worktime.simple_signals
