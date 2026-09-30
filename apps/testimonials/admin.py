from django.contrib import admin

from .models import Testimonial


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ("name", "detail", "rating", "order", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("name", "quote")
