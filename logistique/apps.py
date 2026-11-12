from django.apps import AppConfig


class LogistiqueConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "logistique"
    verbose_name = "Logistique"

    def ready(self):
        from . import realtime  # noqa: F401
