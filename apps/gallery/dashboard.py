from apps.dashboard.registry import Module, site

from .models import GalleryImage


@site.register(GalleryImage)
class GalleryImageModule(Module):
    icon = "ki-picture"
    description = "Photos on the gallery page."
    list_display = ["image", "title", "order", "is_active"]
    search_fields = ["title"]
    toggle_fields = ["is_active"]
