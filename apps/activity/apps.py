from django.apps import AppConfig


class ActivityConfig(AppConfig):
    name = "apps.activity"
    verbose_name = "Activity log"

    def ready(self):
        from . import signals

        signals.connect()
