from apps.dashboard.registry import Module, site

from .models import Service


@site.register(Service)
class ServiceModule(Module):
    icon = "ki-heart-circle"
    description = "The services listed on the website."
    list_display = ["image", "title", "summary", "is_featured", "order", "is_active"]
    search_fields = ["title", "summary", "description"]
    list_filter = ["is_featured", "is_active"]
    toggle_fields = ["is_featured", "is_active"]
