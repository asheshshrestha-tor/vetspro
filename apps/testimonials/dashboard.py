from apps.dashboard.registry import Module, site

from .models import Testimonial


@site.register(Testimonial)
class TestimonialModule(Module):
    icon = "ki-star"
    description = "Client reviews shown on the home page."
    list_display = ["photo", "name", "detail", "rating", "order", "is_active"]
    search_fields = ["name", "detail", "quote"]
    list_filter = ["is_active"]
    toggle_fields = ["is_active"]
