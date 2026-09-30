from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class DashboardConfig(AppConfig):
    name = "apps.dashboard"
    verbose_name = "Dashboard"

    def ready(self):
        # Each app describes its own dashboard modules in a dashboard.py file.
        autodiscover_modules("dashboard")
