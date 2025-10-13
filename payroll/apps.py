from django.apps import AppConfig


class PayrollConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "payroll"

    def ready(self):
        """Initialize payroll calculation strategies when app is ready"""
        from payroll.services.factory import register_default_strategies

        register_default_strategies()
